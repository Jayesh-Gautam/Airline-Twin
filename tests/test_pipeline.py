import csv
import datetime as dt
import os
import sys

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

import config as C
from pipeline import clean, enrich


def write_csv(folder, name, rows):
    with open(os.path.join(folder, f"{name}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


# ------------------------------------------------------------------ cleaning units
def test_category_typo_repair(spark):
    df = spark.createDataFrame(
        [("captain",), ("CAPTAIN",), ("  captian ",), ("first_ofcer",), ("purser",), ("zzzzzzzz",)], "v string")
    out = [r.r for r in df.select(clean.repair_category(F.col("v"),
           ["captain", "first_officer", "purser", "flight_attendant"]).alias("r")).collect()]
    assert out == ["captain", "captain", "captain", "first_officer", "purser", None]


def test_mixed_date_formats_parse(spark):
    values = ["2024-05-06 17:48:44", "2024-05-06T17:48:44", "06/05/2024 17:48", "2024/05/06",
              "06-05-2024", "06.05.2024", "06 May 2024", "May 06, 2024", "20240506"]
    df = spark.createDataFrame([(v,) for v in values], "v string")
    # format inside Spark (UTC) so the check doesn't depend on the machine's timezone
    parsed = [r.t for r in df.select(F.date_format(clean.parse_ts(F.col("v")), "yyyy-MM-dd HH:mm:ss")
                                     .alias("t")).collect()]
    assert None not in parsed, dict(zip(values, parsed))
    assert all(p.startswith("2024-05-06") for p in parsed)
    assert parsed[0] == "2024-05-06 17:48:44"
    assert parsed[1] == "2024-05-06 17:48:44"
    # formats seen in the real dirty copy
    extra = spark.createDataFrame([("Oct 14, 2021 10:04",), ("Oct 4, 2021 10:04",), ("2022-10-04T21:47:02Z",),
                                   ("15/09/2022 06:02",)], "v string")
    got = [r.t for r in extra.select(F.date_format(clean.parse_ts(F.col("v")), "yyyy-MM-dd HH:mm")
                                     .alias("t")).collect()]
    assert got == ["2021-10-14 10:04", "2021-10-04 10:04", "2022-10-04 21:47", "2022-09-15 06:02"]


def test_exact_and_near_duplicates_removed(spark, tmp_path):
    write_csv(str(tmp_path), "countries", [
        {"id": 1, "iso_code": "US", "name": "United States"},
        {"id": 1, "iso_code": "US", "name": "United States"},   # exact duplicate
        {"id": 2, "iso_code": "GB", "name": "United Kingdom"},
        {"id": 2, "iso_code": "GB", "name": ""},                # near duplicate, less complete
    ])
    df, stats = clean.clean_table(spark, str(tmp_path), "countries", {})
    assert stats["exact_duplicates"] == 1
    assert stats["near_duplicates"] == 1
    rows = {r.id: r.name for r in df.collect()}
    assert rows == {1: "United States", 2: "United Kingdom"}   # complete version kept


def test_orphan_rows_removed(spark, tmp_path):
    d = str(tmp_path)
    write_csv(d, "countries", [{"id": 1, "iso_code": "US", "name": "United States"}])
    write_csv(d, "airlines", [{"id": 1, "country_id": 1, "iata_code": "N7", "name": "Northwind"}])
    write_csv(d, "aircraft_models", [{"id": 1, "capacity": 180, "manufacturer": "Airbus", "model_number": "A320neo"}])
    write_csv(d, "aircrafts", [
        {"id": 1, "airline_id": 1, "model_id": 1, "registration_number": "N1", "status": "in_service"},
        {"id": 2, "airline_id": 99, "model_id": 1, "registration_number": "N2", "status": "in_service"},  # orphan
        {"id": 3, "airline_id": 1, "model_id": 77, "registration_number": "N3", "status": "in_service"},  # orphan
    ])
    cleaned = {}
    for t in ["countries", "airlines", "aircraft_models"]:
        cleaned[t], _ = clean.clean_table(spark, d, t, cleaned)
    df, stats = clean.clean_table(spark, d, "aircrafts", cleaned)
    assert stats["orphan_rows_removed"] == 2
    assert [r.id for r in df.collect()] == [1]


# ------------------------------------------------------------------ business rules / enrich
def test_ticket_price_equals_sum_of_fares(cleaned_dirty):
    t, _, stats = cleaned_dirty
    sums = t["ticket_flights"].groupBy("ticket_id").agg(F.sum("fare").alias("s"))
    bad = (t["tickets"].join(sums, t["tickets"].id == sums.ticket_id)
           .where(F.abs(F.col("total_price") - F.col("s")) > 0.005).count())
    assert bad == 0
    assert t["ticket_flights"].where("fare IS NULL").count() == 0


def test_dirty_data_has_faults_and_clean_data_has_none(cleaned_dirty, cleaned_clean):
    _, dirty_report, _ = cleaned_dirty
    _, clean_report, clean_rules = cleaned_clean
    assert sum(r["exact_duplicates"] for r in dirty_report) > 0
    assert sum(r["near_duplicates"] for r in dirty_report) > 0
    assert sum(r["category_values_repaired"] for r in dirty_report) > 0
    assert sum(r["orphan_rows_removed"] for r in dirty_report) > 0
    assert sum(r["unparsed_dates"] for r in dirty_report) == 0
    for k in ["exact_duplicates", "near_duplicates", "category_values_repaired", "outliers_nulled",
              "orphan_rows_removed", "unparsed_dates"]:
        assert sum(r[k] for r in clean_report) == 0, k
    assert clean_rules["payments_repaired"] == 0 and clean_rules["ticket_prices_recomputed"] == 0


def test_fuel_cost_formula(cleaned_clean):
    t = cleaned_clean[0]
    ops = enrich.build_flight_ops(t)
    rows = ops.where("block_hours IS NOT NULL").limit(50).collect()
    assert rows
    for r in rows:
        burn = C.FUEL_BURN_KG_PER_HR.get(r.model_number, C.DEFAULT_FUEL_BURN_KG_PER_HR)
        fuel_kg = round(burn * r.block_hours + C.TAXI_FUEL_KG, 1)
        assert r.fuel_kg_est == pytest.approx(fuel_kg, abs=0.11)
        assert r.fuel_cost_est == pytest.approx(r.fuel_kg_est * C.FUEL_PRICE_PER_KG, abs=0.011)
        assert r.operating_profit_est == pytest.approx(r.fare_revenue - r.operating_cost_est, abs=0.011)
        assert r.is_estimate is True
        assert 0 <= r.load_factor <= 1


# ------------------------------------------------------------------ end to end (mongomock)
def run_main(monkeypatch, data, db, out):
    import run_pipeline
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--data", data, "--db", db,
                                      "--mongo-uri", "mongomock://test", "--driver-memory", "2g"])
    monkeypatch.setattr(C, "OUTPUT_ROOT", str(out))
    monkeypatch.setattr(SparkSession, "stop", lambda self: None)   # keep the shared session alive
    run_pipeline.main()


def snapshot(db):
    return {n: db[n].count_documents({}) for n in db.list_collection_names()}


def test_pipeline_completes_and_is_idempotent(spark, sample_dirs, tmp_path, monkeypatch):
    pytest.importorskip("mongomock")
    from pipeline.mongo_store import get_db
    run_main(monkeypatch, sample_dirs[0], "idem", tmp_path)
    db = get_db("mongomock://test", "idem")
    first = snapshot(db)

    # completes: all 18 source tables, flight_ops, synthetic data, 15 analytics, audit
    for name in ["flight_ops", "maintenance_events", "payroll", "data_quality_report", "pipeline_runs",
                 "a_kpi_summary", "a_route_profitability", "a_monthly_trend", "tickets", "ticket_flights"]:
        assert first.get(name, 0) > 0, name
    assert len([n for n in first if n.startswith("a_")]) == 17
    assert os.path.exists(tmp_path / "sample" / "run_summary.json")
    assert first["flight_ops"] == len(db.flight_ops.distinct("_id"))

    run_main(monkeypatch, sample_dirs[0], "idem", tmp_path)   # second run
    assert snapshot(db) == first                              # nothing duplicated
