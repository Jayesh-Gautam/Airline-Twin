"""Check the 1K run in MongoDB against the answers published on the dataset page.

  python run_pipeline.py --data data/1k
  python tests/verify_1k.py            # exit code 0 = all numbers match
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config as C  # noqa: E402
from pipeline.mongo_store import get_db  # noqa: E402

YEAR_REVENUE = {2022: 28507.00, 2023: 47906.80, 2024: 134907.80, 2025: 136803.40}
CABIN_AVG_FARE = {"First": 1949.51, "Business": 915.78, "Premium Economy": 374.52, "Economy": 164.65}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo-uri", default=C.MONGO_URI)
    ap.add_argument("--db", default=C.MONGO_DB)
    a = ap.parse_args()
    db = get_db(a.mongo_uri, a.db)
    failures = 0

    def check(label, got, want):
        nonlocal failures
        ok = got is not None and abs(got - want) < 0.01
        failures += not ok
        print(f"  [{'OK' if ok else 'FAIL'}] {label:<28} got={got}  expected={want}")

    print("Fare revenue by departure year (flight_ops):")
    got = {d["_id"]: d["rev"] for d in db.flight_ops.aggregate(
        [{"$group": {"_id": {"$year": "$departure_time"}, "rev": {"$sum": "$fare_revenue"}}}])}
    for year, want in YEAR_REVENUE.items():
        check(str(year), round(got[year], 2) if year in got else None, want)

    print("Average fare by cabin (ticket_flights -> cabins):")
    got = {d["cabin"]: d["avg"] for d in db.ticket_flights.aggregate([
        {"$group": {"_id": "$cabin_id", "avg": {"$avg": "$fare"}}},
        {"$lookup": {"from": "cabins", "localField": "_id", "foreignField": "_id", "as": "c"}},
        {"$unwind": "$c"}, {"$project": {"cabin": "$c.name", "avg": 1}}])}
    for cabin, want in CABIN_AVG_FARE.items():
        check(cabin, round(got[cabin], 2) if cabin in got else None, want)

    print("PASS" if not failures else f"FAIL: {failures} mismatches")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
