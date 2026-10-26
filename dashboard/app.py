"""Web dashboard + airline simulation, served by Flask from MongoDB.

  python dashboard/app.py            # http://127.0.0.1:5000
  python dashboard/app.py --db airline_twin --dirty-db airline_dirty --port 5000

Every number comes from the collections written by run_pipeline.py. The
simulation replays the real departures day by day; costs/profit stay estimates.
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
import time

from flask import Flask, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
import config as C  # noqa: E402
from mongo_queries import QUERIES  # noqa: E402
from pipeline.mongo_store import get_db  # noqa: E402

app = Flask(__name__, static_folder=os.path.join(HERE, "static"), static_url_path="/static")
CFG = {"uri": C.MONGO_URI, "db": C.MONGO_DB, "dirty_db": "airline_dirty"}
_clients = {}


def db(name=None):
    name = name or CFG["db"]
    if name not in _clients:
        _clients[name] = get_db(CFG["uri"], name)
    return _clients[name]


def _default(o):
    if isinstance(o, dt.datetime):
        return o.strftime("%Y-%m-%dT%H:%M:%SZ")   # stored as naive UTC
    if isinstance(o, dt.date):
        return o.isoformat()
    raise TypeError(type(o))


app.json.default = _default
app.json.sort_keys = False


def rows(coll, query=None, proj=None, sort=None, limit=0, database=None):
    cur = db(database)[coll].find(query or {}, {"_id": 0, **(proj or {})})
    if sort:
        cur = cur.sort(sort)
    if limit:
        cur = cur.limit(limit)
    return list(cur)


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/overview")
def overview():
    d = db()
    run = d.pipeline_runs.find_one({}, {"_id": 0}) or {}
    return jsonify(kpi=(rows("a_kpi_summary") or [{}])[0],
                   monthly=rows("a_monthly_trend", sort=[("year_month", 1)]),
                   airlines=rows("a_airline_pnl"),
                   timings=run.get("timings_s", {}), quality=run.get("data_quality", {}),
                   spark_version=run.get("spark_version"),
                   counts={n: d[n].estimated_document_count() for n in
                           ["flight_ops", "tickets", "ticket_flights", "bookings", "payments"]})


@app.get("/api/sim/series")
def sim_series():
    return jsonify(rows("a_sim_daily", sort=[("date", 1)]))


@app.get("/api/sim/day")
def sim_day():
    date = request.args.get("date", "")
    try:
        day = dt.datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return jsonify(error="date must be YYYY-MM-DD"), 400
    # flights that left up to 10 h before midnight can still be in the air at 00:00
    lo, hi = day - dt.timedelta(hours=10), day + dt.timedelta(days=1)
    fields = {k: 1 for k in ["flight_number", "airline", "origin", "destination", "route", "model_number",
                             "departure_time", "arrival_time", "delay_minutes", "delay_reason", "is_delayed",
                             "passengers", "capacity", "load_factor", "fare_revenue", "operating_profit_est"]}
    flights = list(db().flight_ops.find({"departure_time": {"$gte": lo, "$lt": hi}}, {"_id": 1, **fields})
                   .sort("departure_time", 1))
    for f in flights:
        f["id"] = f.pop("_id")
    return jsonify(date=date, daily=(rows("a_sim_daily", {"date": date}) or [None])[0],
                   airlines=rows("a_sim_daily_airline", {"date": date}, sort=[("revenue", -1)]),
                   flights=flights)


@app.get("/api/routes")
def routes():
    q = {"airline": request.args["airline"]} if request.args.get("airline") else {}
    r = rows("a_route_profitability", q, sort=[("profit_est", -1)])
    return jsonify(airlines=sorted({x["airline"] for x in rows("a_route_profitability")}),
                   top=r[:10], bottom=r[-10:][::-1], count=len(r))


@app.get("/api/delays")
def delays():
    return jsonify(by_reason=rows("a_delays_by_reason"),
                   by_airport=rows("a_delays_by_airport", sort=[("worst_rank", 1)], limit=10),
                   by_model=rows("a_delays_by_aircraft_model"))


@app.get("/api/fleet")
def fleet():
    return jsonify(fuel=rows("a_fuel_efficiency"), cabins=rows("a_cabin_fares", sort=[("cabin", 1)]),
                   utilization=rows("a_aircraft_utilization", sort=[("block_hours", -1)], limit=10),
                   lead_time=rows("a_booking_lead_time"), payments=rows("a_payments_and_refunds"),
                   airports=rows("a_airport_traffic", sort=[("rank", 1)], limit=10))


@app.get("/api/quality")
def quality():
    out = {}
    for label, name in (("clean", CFG["db"]), ("dirty", CFG["dirty_db"])):
        try:
            run = db(name).pipeline_runs.find_one({}, {"_id": 0}) or {}
            out[label] = {"run": run.get("run"), "summary": run.get("data_quality", {}),
                          "tables": rows("data_quality_report", database=name)}
        except Exception:
            out[label] = None
    key = os.path.join(ROOT, "output", "100k-dirty", "cleaning_vs_answer_key.csv")
    out["answer_key"] = list(csv.DictReader(open(key, encoding="utf-8"))) if os.path.exists(key) else []
    return jsonify(out)


@app.get("/api/explorer")
def explorer():
    items = []
    for title, (coll, pipeline) in QUERIES.items():
        t0 = time.time()
        res = list(db()[coll].aggregate(pipeline))
        items.append({"title": title, "collection": coll, "pipeline": json.dumps(pipeline, indent=1),
                      "ms": round((time.time() - t0) * 1000), "result": res[:12]})
    one = db().flight_ops.find_one({}, {"route": 1, "year_month": 1})
    q = {"route": one["route"], "year_month": one["year_month"]}
    ex = db().command({"explain": {"find": "flight_ops", "filter": q}, "verbosity": "executionStats"})
    stage = ex["queryPlanner"]["winningPlan"]
    stage = stage.get("inputStage", stage)
    return jsonify(queries=items, index={
        "query": q, "stage": stage.get("stage"), "index": stage.get("indexName"),
        "docs_examined": ex["executionStats"]["totalDocsExamined"],
        "collection_size": db().flight_ops.estimated_document_count()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo-uri", default=C.MONGO_URI)
    ap.add_argument("--db", default=C.MONGO_DB)
    ap.add_argument("--dirty-db", default="airline_dirty")
    ap.add_argument("--port", type=int, default=5000)
    a = ap.parse_args()
    CFG.update(uri=a.mongo_uri, db=a.db, dirty_db=a.dirty_db)
    db()  # fail fast if MongoDB is down
    print(f"Dashboard: http://127.0.0.1:{a.port}   (MongoDB {a.mongo_uri} / {a.db})")
    app.run(host="127.0.0.1", port=a.port, debug=False)
