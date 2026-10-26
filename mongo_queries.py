"""MongoDB side of the project: aggregation pipelines run directly on the
collections written by run_pipeline.py (flight_ops = one document per
departure, the 'digital twin' record).

  python mongo_queries.py
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
from pipeline.mongo_store import get_db  # noqa: E402

QUERIES = {
    "Top 10 routes by estimated operating profit": ("flight_ops", [
        {"$group": {"_id": "$route", "departures": {"$sum": 1},
                    "revenue": {"$sum": "$fare_revenue"},
                    "profit_est": {"$sum": "$operating_profit_est"}}},
        {"$sort": {"profit_est": -1}}, {"$limit": 10}]),

    "Delay rate by airline": ("flight_ops", [
        {"$group": {"_id": "$airline", "departures": {"$sum": 1},
                    "delayed": {"$sum": {"$cond": ["$is_delayed", 1, 0]}},
                    "avg_delay_min": {"$avg": "$delay_minutes"}}},
        {"$project": {"departures": 1, "delayed": 1, "avg_delay_min": "$avg_delay_min",
                      "delay_rate": {"$divide": ["$delayed", "$departures"]}}},
        {"$sort": {"delay_rate": -1}}]),

    "Yearly revenue and estimated profit": ("flight_ops", [
        {"$group": {"_id": {"$year": "$departure_time"}, "departures": {"$sum": 1},
                    "passengers": {"$sum": "$passengers"},
                    "revenue": {"$sum": "$fare_revenue"},
                    "profit_est": {"$sum": "$operating_profit_est"}}},
        {"$sort": {"_id": 1}}]),

    "Fullest 5 departures (load factor)": ("flight_ops", [
        {"$sort": {"load_factor": -1}}, {"$limit": 5},
        {"$project": {"_id": 0, "flight_number": 1, "route": 1, "departure_time": 1,
                      "model_number": 1, "passengers": 1, "capacity": 1, "load_factor": 1}}]),

    "Aircraft with most maintenance downtime ($lookup into aircrafts)": ("maintenance_events", [
        {"$group": {"_id": "$aircraft_id", "events": {"$sum": 1},
                    "downtime_hours": {"$sum": "$downtime_hours"}, "cost_est": {"$sum": "$cost_est"}}},
        {"$sort": {"downtime_hours": -1}}, {"$limit": 5},
        {"$lookup": {"from": "aircrafts", "localField": "_id", "foreignField": "_id", "as": "ac"}},
        {"$unwind": "$ac"},
        {"$project": {"registration": "$ac.registration_number", "events": 1,
                      "downtime_hours": 1, "cost_est": 1}}]),

    "Revenue by cabin ($lookup ticket_flights -> cabins)": ("ticket_flights", [
        {"$group": {"_id": "$cabin_id", "segments": {"$sum": 1}, "revenue": {"$sum": "$fare"}}},
        {"$lookup": {"from": "cabins", "localField": "_id", "foreignField": "_id", "as": "c"}},
        {"$unwind": "$c"},
        {"$project": {"cabin": "$c.name", "segments": 1, "revenue": 1}},
        {"$sort": {"revenue": -1}}]),
}


def fmt(v):
    return f"{v:,.2f}" if isinstance(v, float) else str(v)


def run(db):
    for title, (coll, pipeline) in QUERIES.items():
        print(f"\n### {title}   [db.{coll}.aggregate]")
        for doc in db[coll].aggregate(pipeline):
            print("  " + "  ".join(f"{k}={fmt(v)}" for k, v in doc.items()))

    print("\n### Index use: departures of one route in one month")
    one = db.flight_ops.find_one({}, {"route": 1, "year_month": 1})
    if one:
        q = {"route": one["route"], "year_month": one["year_month"]}
        print(f"  query={q}  matches={db.flight_ops.count_documents(q)}")
        try:
            plan = db.flight_ops.find(q).explain()["queryPlanner"]["winningPlan"]
            stage = plan.get("inputStage", plan)
            print(f"  winning plan: {plan.get('stage')} <- {stage.get('stage')} "
                  f"index={stage.get('indexName', '-')}")
        except Exception:
            print("  (explain() not available on this MongoDB backend)")

    print("\n### Collections")
    for name in sorted(db.list_collection_names()):
        print(f"  {name:<28} {db[name].estimated_document_count():>10,} docs")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo-uri", default=C.MONGO_URI)
    ap.add_argument("--db", default=C.MONGO_DB)
    a = ap.parse_args()
    run(get_db(a.mongo_uri, a.db))
