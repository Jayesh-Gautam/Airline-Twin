"""/history/* - the results PySpark computed from the historical data
(a_* collections and flight_ops), optionally filtered by airline id."""
from fastapi import APIRouter

DIRTY_DB = "airline_dirty"


def router(get_db, parse_airline):
    r = APIRouter(prefix="/history", tags=["history (PySpark results)"])

    def name_of(db, aid):
        a = db.airlines.find_one({"_id": aid}) if aid is not None else None
        return a["name"] if a else None

    def match(aid):
        return [{"$match": {"airline_id": aid}}] if aid is not None else []

    @r.get("/summary")
    def summary(airline: str = None):
        db, aid = get_db(), parse_airline(airline)
        k = list(db.flight_ops.aggregate(match(aid) + [{"$group": {
            "_id": None, "departures": {"$sum": 1}, "passengers": {"$sum": "$passengers"},
            "fare_revenue": {"$sum": "$fare_revenue"}, "operating_profit_est": {"$sum": "$operating_profit_est"},
            "delayed": {"$sum": {"$cond": ["$is_delayed", 1, 0]}}, "avg_load_factor": {"$avg": "$load_factor"},
            "routes": {"$addToSet": "$route"}, "first": {"$min": "$departure_time"}, "last": {"$max": "$departure_time"}}}]))
        k = k[0] if k else {}
        run = db.pipeline_runs.find_one({}, {"_id": 0, "timings_s": 1, "data_quality": 1, "spark_version": 1}) or {}
        return {"departures": k.get("departures", 0), "passengers": k.get("passengers", 0),
                "fare_revenue": round(k.get("fare_revenue", 0), 2),
                "operating_profit_est": round(k.get("operating_profit_est", 0), 2),
                "delay_rate": round(k["delayed"] / k["departures"], 4) if k.get("departures") else None,
                "avg_load_factor": round(k.get("avg_load_factor") or 0, 4), "routes": len(k.get("routes", [])),
                "first": k.get("first"), "last": k.get("last"), "pipeline": run}

    @r.get("/monthly")
    def monthly(airline: str = None):
        db, aid = get_db(), parse_airline(airline)
        rows = db.flight_ops.aggregate(match(aid) + [
            {"$group": {"_id": "$year_month", "departures": {"$sum": 1}, "passengers": {"$sum": "$passengers"},
                        "fare_revenue": {"$sum": "$fare_revenue"}, "operating_cost_est": {"$sum": "$operating_cost_est"},
                        "operating_profit_est": {"$sum": "$operating_profit_est"}}},
            {"$sort": {"_id": 1}}])
        return [{"year_month": x.pop("_id"), **{k: round(v, 2) if isinstance(v, float) else v for k, v in x.items()}}
                for x in rows]

    @r.get("/routes")
    def routes(airline: str = None):
        db, aid = get_db(), parse_airline(airline)
        q = {"airline": name_of(db, aid)} if aid is not None else {}
        return list(db.a_route_profitability.find(q, {"_id": 0}).sort("profit_est", -1))

    @r.get("/airline-pnl")
    def airline_pnl():
        return list(get_db().a_airline_pnl.find({}, {"_id": 0}))

    @r.get("/delays")
    def delays(airline: str = None):
        db, aid = get_db(), parse_airline(airline)
        by_reason = list(db.flight_ops.aggregate(match(aid) + [
            {"$match": {"is_delayed": True}},
            {"$group": {"_id": "$delay_reason", "delays": {"$sum": 1}, "avg_minutes": {"$avg": "$delay_minutes"}}},
            {"$sort": {"delays": -1}}]))
        by_airport = list(db.flight_ops.aggregate(match(aid) + [
            {"$group": {"_id": "$origin", "departures": {"$sum": 1}, "delayed": {"$sum": {"$cond": ["$is_delayed", 1, 0]}}}},
            {"$match": {"departures": {"$gte": 20}}},
            {"$project": {"departures": 1, "delayed": 1, "delay_rate": {"$divide": ["$delayed", "$departures"]}}},
            {"$sort": {"delay_rate": -1}}, {"$limit": 10}]))
        return {"by_reason": [{"reason": x["_id"], "delays": x["delays"], "avg_minutes": round(x["avg_minutes"], 1)}
                              for x in by_reason],
                "by_airport": [{"airport": x["_id"], "departures": x["departures"], "delayed": x["delayed"],
                                "delay_rate": round(x["delay_rate"], 4)} for x in by_airport]}

    @r.get("/fuel")
    def fuel(airline: str = None):
        db, aid = get_db(), parse_airline(airline)
        rows = db.flight_ops.aggregate(match(aid) + [
            {"$group": {"_id": {"model": "$model_number", "capacity": "$capacity"}, "departures": {"$sum": 1},
                        "fuel_kg": {"$sum": "$fuel_kg_est"}, "fuel_cost": {"$sum": "$fuel_cost_est"},
                        "seat_hours": {"$sum": {"$multiply": ["$block_hours", "$capacity"]}},
                        "passengers": {"$sum": "$passengers"}}}])
        out = [{"model": x["_id"]["model"], "capacity": x["_id"]["capacity"], "departures": x["departures"],
                "kg_per_seat_hour_est": round(x["fuel_kg"] / x["seat_hours"], 2),
                "fuel_cost_per_passenger_est": round(x["fuel_cost"] / x["passengers"], 2) if x["passengers"] else None}
               for x in rows]
        return sorted(out, key=lambda x: x["kg_per_seat_hour_est"])

    @r.get("/utilization")
    def utilization(airline: str = None):
        db, aid = get_db(), parse_airline(airline)
        q = {"airline": name_of(db, aid)} if aid is not None else {}
        return list(db.a_aircraft_utilization.find(q, {"_id": 0}).sort("block_hours", -1))

    @r.get("/cabins")
    def cabins():
        return list(get_db().a_cabin_fares.find({}, {"_id": 0}))

    @r.get("/quality")
    def quality():
        db = get_db()
        out = {}
        for label, d in (("clean", db), ("dirty", db.client[DIRTY_DB])):
            run = d.pipeline_runs.find_one({}, {"_id": 0, "run": 1, "data_quality": 1, "timings_s": 1})
            out[label] = {"run": run, "tables": list(d.data_quality_report.find({}, {"_id": 0}))} if run else None
        return out

    return r
