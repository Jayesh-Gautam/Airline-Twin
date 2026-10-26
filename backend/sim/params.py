"""Simulator inputs: the Spark-computed sim_params plus airport coordinates,
airline names/codes and the fleet. Kept in one plain object so tests can build
it from fixtures without MongoDB."""
import json
import os
from dataclasses import dataclass, field

from . import geo

COORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "airport_coords.json")


class ParamsMissing(RuntimeError):
    pass


@dataclass
class Params:
    glob: dict
    airlines: dict            # airline_id -> {airline, code, hub, weekday_factor, ...}
    routes: dict              # airline_id -> [route doc]
    airports: dict            # iata -> {delay_prob, delay_minutes_q, delay_reasons}
    aircraft: list            # [{aircraft_id, airline_id, registration, model, capacity, status, location}]
    coords: dict              # iata -> {lat, lon, name}
    routes_from: dict = field(default_factory=dict)   # (airline_id, origin) -> [route]

    def __post_init__(self):
        # Airlines fly return legs. When the history only has A->B for an airline,
        # add B->A as a "mirrored" route with the same demand, fares and cabin mix
        # (delay odds come from its own origin airport).
        for aid, rs in self.routes.items():
            have = {(r["origin"], r["destination"]) for r in rs}
            for r in list(rs):
                if (r["destination"], r["origin"]) in have:
                    continue
                m = dict(r, _id=r["_id"] + ":mirror", origin=r["destination"], destination=r["origin"],
                         route=f"{r['destination']}-{r['origin']}", mirrored=True,
                         flight_numbers=[_return_number(n) for n in r.get("flight_numbers", [])])
                ap = self.airports.get(m["origin"])
                if ap:
                    m["delay_prob"] = ap["delay_prob"]
                rs.append(m)
                have.add((m["origin"], m["destination"]))
        for aid, rs in self.routes.items():
            for r in rs:
                if not r.get("distance_km"):
                    a, b = self.coords[r["origin"]], self.coords[r["destination"]]
                    r["distance_km"] = geo.distance_km(a["lat"], a["lon"], b["lat"], b["lon"])
                self.routes_from.setdefault((aid, r["origin"]), []).append(r)
        for v in self.routes_from.values():
            v.sort(key=lambda r: r["destination"])

    def distance(self, a, b):
        x, y = self.coords[a], self.coords[b]
        return geo.distance_km(x["lat"], x["lon"], y["lat"], y["lon"])


def _return_number(n):
    """Return legs conventionally use the next flight number (0971 -> 0972)."""
    return str(int(n) + 1).zfill(len(n)) if n.isdigit() else n + "R"


def load_coords(path=COORDS_FILE):
    with open(path, encoding="utf-8") as f:
        return {a["iata"]: a for a in json.load(f)["airports"]}


def from_docs(docs, airline_rows, coords):
    """docs: the sim_params collection; airline_rows: [{_id, name, iata_code}]."""
    by = {}
    for d in docs:
        by.setdefault(d["kind"], []).append(d)
    if "global" not in by or "route" not in by:
        raise ParamsMissing("sim_params is empty - run `python run_pipeline.py --data data/1m` first")
    codes = {a["_id"]: a for a in airline_rows}
    airlines = {}
    for a in by.get("airline", []):
        row = codes.get(a["airline_id"], {})
        airlines[a["airline_id"]] = {**a, "code": row.get("iata_code", str(a["airline_id"]))}
    routes = {}
    for r in by["route"]:
        routes.setdefault(r["airline_id"], []).append(r)
    return Params(glob=by["global"][0], airlines=airlines, routes=routes,
                  airports={a["iata"]: a for a in by.get("airport", [])},
                  aircraft=sorted(by.get("aircraft", []), key=lambda a: a["aircraft_id"]), coords=coords)


def load(db):
    docs = list(db.sim_params.find())
    return from_docs(docs, list(db.airlines.find()), load_coords())
