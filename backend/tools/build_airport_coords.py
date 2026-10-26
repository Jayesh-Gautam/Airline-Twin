"""Build backend/data/airport_coords.json for the airports present in MongoDB.

Coordinates come from the public-domain OurAirports dataset:
  https://davidmegginson.github.io/ourairports-data/airports.csv

  python backend/tools/build_airport_coords.py path/to/airports.csv
"""
import csv
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
import config as C  # noqa: E402
from pymongo import MongoClient  # noqa: E402


def main(csv_path):
    wanted = {a["iata_code"]: a["name"] for a in MongoClient(C.MONGO_URI)[C.MONGO_DB].airports.find()}
    found = {}
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            code = r["iata_code"].strip()
            if code in wanted and (code not in found or r["type"] == "large_airport"):
                found[code] = {"iata": code, "name": wanted[code], "lat": round(float(r["latitude_deg"]), 5),
                               "lon": round(float(r["longitude_deg"]), 5), "country": r["iso_country"],
                               "city": r["municipality"]}
    missing = sorted(set(wanted) - set(found))
    out = {"source": "OurAirports (public domain), https://ourairports.com/data/ - airports.csv",
           "note": "Coordinates of the real airports with these IATA codes; the airlines using them are fictional.",
           "airports": [found[k] for k in sorted(found)]}
    path = os.path.join(ROOT, "backend", "data", "airport_coords.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"wrote {len(found)} airports to {path}; missing: {missing or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1])
