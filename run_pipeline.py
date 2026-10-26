"""End-to-end pipeline: CSV -> PySpark clean -> enrich -> analytics -> MongoDB.

Examples
  python run_pipeline.py --data data/1m                 # real 1M dataset (2.9M rows)
  python run_pipeline.py --data data/100k-dirty         # cleaning demo on the dirty copy
  python run_pipeline.py --data data/sample --no-mongo  # quick check without MongoDB
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as C  # noqa: E402
from spark_session import get_spark  # noqa: E402
from pipeline import analytics, clean, enrich, sim_params  # noqa: E402

# Cleaned source tables also stored in MongoDB (the operational store).
STORE_TABLES = ["countries", "cities", "airports", "airlines", "aircraft_models", "aircrafts",
                "cabins", "promotions", "crews", "flights", "flight_instances", "flight_delays",
                "flight_crews", "bookings", "tickets", "ticket_flights", "payments", "refunds"]


def save_csv(path, rows):
    if not rows:
        open(path, "w").close(); return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


def jsonable(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if hasattr(v, "is_finite"):  # Decimal
        return float(v)
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="folder containing the extracted CSV files")
    ap.add_argument("--mongo-uri", default=C.MONGO_URI)
    ap.add_argument("--db", default=C.MONGO_DB)
    ap.add_argument("--no-mongo", action="store_true", help="skip MongoDB, write CSV results only")
    ap.add_argument("--skip-raw-tables", action="store_true",
                    help="store only flight_ops + analytics in MongoDB (faster)")
    ap.add_argument("--driver-memory", default="3g")
    args = ap.parse_args()

    run_name = os.path.basename(os.path.normpath(args.data))
    out_dir = os.path.join(C.OUTPUT_ROOT, run_name)
    os.makedirs(out_dir, exist_ok=True)
    timings, t0 = {}, time.time()

    def step(name):
        now = time.time(); timings[name] = round(now - step.last, 1); step.last = now
        print(f"[{timings[name]:>6.1f}s] {name}")
    step.last = t0

    db = None
    if not args.no_mongo:
        from pipeline.mongo_store import get_db
        db = get_db(args.mongo_uri, args.db)
        print(f"MongoDB connected: {args.mongo_uri} / {args.db}")

    spark = get_spark(driver_memory=args.driver_memory)
    print(f"Spark {spark.version}, {spark.sparkContext.defaultParallelism} cores, data={args.data}")

    print("\n== 1. Ingest + clean (PySpark) ==")
    t, dq_report, rule_stats = clean.clean_all(spark, args.data)
    step("ingest_and_clean")

    print("\n== 2. Enrich: flight_ops digital twin + synthetic records ==")
    ops = enrich.build_flight_ops(t)
    maint = enrich.generate_maintenance(spark, t)
    payroll = enrich.build_payroll(t)
    print(f"  flight_ops={ops.count():,}  maintenance_events={maint.count():,}  payroll={payroll.count():,}")
    step("enrich")

    print("\n== 3. Analytics (PySpark DataFrame API + Spark SQL) ==")
    results = analytics.run_all(spark, t, ops, maint, payroll)
    collected = {}
    for name, df in results.items():
        rows = [{k: jsonable(v) for k, v in r.asDict().items()} for r in df.collect()]
        collected[name] = rows
        save_csv(os.path.join(out_dir, f"{name}.csv"), rows)
        print(f"  {name:<26} {len(rows):>5} rows")
    step("analytics")

    print("\n== 3b. Simulator parameters (PySpark) ==")
    params = sim_params.build(spark, t, ops, maint)
    with open(os.path.join(out_dir, "sim_params.json"), "w") as f:
        json.dump(params, f, indent=1, default=str)
    kinds = {}
    for p in params:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    print("  " + "  ".join(f"{k}={v}" for k, v in kinds.items()))
    step("sim_params")

    total_raw = sum(r["rows_raw"] for r in dq_report)
    total_clean = sum(r["rows_clean"] for r in dq_report)
    dq_summary = {"run": run_name, "rows_raw": total_raw, "rows_clean": total_clean,
                  **{k: sum(r.get(k, 0) for r in dq_report) for k in
                     ["exact_duplicates", "near_duplicates", "category_values_repaired",
                      "outliers_nulled", "orphan_rows_removed", "orphan_keys_nulled"]},
                  "unparsed_dates": sum(r["unparsed_dates"] for r in dq_report),
                  **rule_stats}
    save_csv(os.path.join(out_dir, "data_quality_by_table.csv"), dq_report)

    if db is not None:
        print("\n== 4. Store in MongoDB ==")
        from pipeline import mongo_store as M
        if not args.skip_raw_tables:
            for name in STORE_TABLES:
                n = M.write_df(db, name, t[name])
                print(f"  {name:<20} {n:>9,} docs")
        print(f"  flight_ops           {M.write_df(db, 'flight_ops', ops, id_col='flight_instance_id'):>9,} docs")
        print(f"  maintenance_events   {M.write_df(db, 'maintenance_events', maint):>9,} docs")
        print(f"  payroll              {M.write_df(db, 'payroll', payroll):>9,} docs")
        for name, rows in collected.items():
            M.write_docs(db, f"a_{name}", rows)
        M.write_docs(db, "data_quality_report", dq_report)
        M.write_docs(db, "sim_params", params)
        step("mongodb_store")
        M.write_docs(db, "pipeline_runs", [{
            "run": run_name, "finished_at": dt.datetime.now(dt.timezone.utc), "spark_version": spark.version,
            "timings_s": timings, "data_quality": dq_summary,
            "assumptions": {"fuel_burn_kg_per_hr": C.FUEL_BURN_KG_PER_HR,
                            "fuel_price_per_kg": C.FUEL_PRICE_PER_KG,
                            "crew_rate_per_hr": C.CREW_RATE_PER_HR,
                            "airport_fee": [C.AIRPORT_FEE_BASE, C.AIRPORT_FEE_PER_SEAT]}}])

    timings["total"] = round(time.time() - t0, 1)
    with open(os.path.join(out_dir, "run_summary.json"), "w") as f:
        json.dump({"timings_s": timings, "data_quality": dq_summary,
                   "kpi": collected["kpi_summary"][0] if collected["kpi_summary"] else {}},
                  f, indent=2, default=str)

    print("\n== Data quality summary ==")
    for k, v in dq_summary.items():
        print(f"  {k:<32} {v:,}" if isinstance(v, int) else f"  {k:<32} {v}")
    print("\n== KPIs (fares real; costs are illustrative estimates) ==")
    for k, v in (collected["kpi_summary"][0] if collected["kpi_summary"] else {}).items():
        print(f"  {k:<24} {v}")
    print(f"\nDone in {timings['total']}s. CSV results in {out_dir}/")
    spark.stop()


if __name__ == "__main__":
    main()
