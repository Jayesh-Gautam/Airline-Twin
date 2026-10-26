"""Stage 3b - simulator parameters, computed with Spark from the historical data.

The operations simulator (backend/sim) is driven by these numbers, not by
made-up constants. One MongoDB collection, "sim_params", holds documents of
five kinds (field "kind"):

  global    network-wide fallbacks: delay odds, delay-minute quantiles, delay
            reasons, fares by cabin, mean flown distance, maintenance rates
  airline   departures per weekday and a weekday activity factor, hub, load factor
  route     per airline + origin/destination: departures (total and per weekday),
            load-factor mean/spread, passengers, cabin mix, average fare per
            cabin, delay probability (shrunk toward the origin airport), the
            historical block time, and the great-circle distance
  airport   per origin: delay probability, delay-minute quantiles, delay reasons
  aircraft  where each aircraft last landed (its starting position) and status
"""
import json
import os

from pyspark.sql import Window
from pyspark.sql import functions as F

COORDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", "data", "airport_coords.json")
QS = [i / 10 for i in range(11)]          # delay-minute deciles
SHRINK = 20                               # pseudo-departures for the delay-rate shrinkage
CABINS = {1: "First", 2: "Business", 3: "Premium Economy", 4: "Economy"}


def _haversine(lat1, lon1, lat2, lon2):
    p1, p2 = F.radians(lat1), F.radians(lat2)
    dp, dl = p2 - p1, F.radians(lon2) - F.radians(lon1)
    a = F.pow(F.sin(dp / 2), 2) + F.cos(p1) * F.cos(p2) * F.pow(F.sin(dl / 2), 2)
    return F.lit(2 * 6371.0) * F.asin(F.sqrt(a))


def _rows(df):
    return [r.asDict(recursive=True) for r in df.collect()]


def build(spark, t, ops, maint):
    """Return the list of sim_params documents."""
    with open(COORDS, encoding="utf-8") as f:
        coords = spark.createDataFrame([(a["iata"], float(a["lat"]), float(a["lon"]))
                                        for a in json.load(f)["airports"]], "iata string, lat double, lon double")
    o = coords.select(F.col("iata").alias("origin"), F.col("lat").alias("olat"), F.col("lon").alias("olon"))
    d = coords.select(F.col("iata").alias("destination"), F.col("lat").alias("dlat"), F.col("lon").alias("dlon"))
    # weekday 0 = Monday ... 6 = Sunday
    x = (ops.withColumn("wd", (F.dayofweek("dep_date") + 5) % 7)
         .join(F.broadcast(o), "origin").join(F.broadcast(d), "destination")
         .withColumn("km", _haversine("olat", "olon", "dlat", "dlon"))
         .withColumn("delayed", F.col("is_delayed").cast("int"))).cache()

    # ---- global
    g = x.agg(F.count("*").alias("departures"), F.avg("delayed").alias("delay_prob"),
              F.avg("km").alias("mean_km"), F.avg("block_hours").alias("hist_block_mean"),
              F.avg("load_factor").alias("lf_mean"), F.stddev("load_factor").alias("lf_sd"),
              F.avg("passengers").alias("pax_mean")).first().asDict()
    g["delay_minutes_q"] = x.where("is_delayed").agg(
        F.percentile_approx("delay_minutes", QS, 10000)).first()[0]
    reasons = _rows(x.where("is_delayed").groupBy("delay_reason").count())
    tot = sum(r["count"] for r in reasons)
    g["delay_reasons"] = {r["delay_reason"]: round(r["count"] / tot, 4) for r in reasons}
    tf = t["ticket_flights"].select("flight_instance_id", "cabin_id", F.col("fare").cast("double").alias("fare"))
    fares = _rows(tf.groupBy("cabin_id").agg(F.avg("fare").alias("fare"), F.count("*").alias("n")))
    n_all = sum(r["n"] for r in fares)
    g["fare_by_cabin"] = {CABINS[r["cabin_id"]]: round(r["fare"], 2) for r in fares}
    g["cabin_share"] = {CABINS[r["cabin_id"]]: round(r["n"] / n_all, 4) for r in fares}
    # maintenance rate = events per aircraft-month, by type (from maintenance_events)
    n_ac, months = t["aircrafts"].count(), maint.select("year_month").distinct().count()
    g["maintenance"] = {r["maintenance_type"]: {"per_aircraft_month": round(r["n"] / (n_ac * months), 5),
                                                "downtime_hours": r["downtime"], "avg_cost": round(r["cost"], 2)}
                        for r in _rows(maint.groupBy("maintenance_type").agg(
                            F.count("*").alias("n"), F.avg("downtime_hours").alias("downtime"),
                            F.avg("cost_est").alias("cost")))}
    docs = [{"_id": "global", "kind": "global", **{k: (round(v, 4) if isinstance(v, float) else v)
                                                   for k, v in g.items()}}]

    # ---- airport (origin): delay probability shrunk toward the network rate
    p0 = g["delay_prob"]
    ap = (x.groupBy("origin").agg(F.count("*").alias("departures"), F.sum("delayed").alias("delayed"))
          .withColumn("delay_prob", (F.col("delayed") + F.lit(SHRINK * p0)) / (F.col("departures") + SHRINK)))
    apq = (x.where("is_delayed").groupBy("origin")
           .agg(F.percentile_approx("delay_minutes", QS, 1000).alias("delay_minutes_q"), F.count("*").alias("nd")))
    apr = (x.where("is_delayed").groupBy("origin", "delay_reason").count()
           .groupBy("origin").agg(F.map_from_entries(F.collect_list(F.struct("delay_reason", "count"))).alias("reasons")))
    for r in _rows(ap.join(apq, "origin", "left").join(apr, "origin", "left")):
        rs = r.pop("reasons") or {}
        n = sum(rs.values())
        docs.append({"_id": f"airport:{r['origin']}", "kind": "airport", "iata": r["origin"],
                     "departures": r["departures"], "delayed": r["delayed"],
                     "delay_prob": round(r["delay_prob"], 4),
                     # too few delays at this airport -> use the network distribution
                     "delay_minutes_q": r["delay_minutes_q"] if (r["nd"] or 0) >= 10 else g["delay_minutes_q"],
                     "delay_reasons": {k: round(v / n, 4) for k, v in rs.items()} if n >= 10 else g["delay_reasons"]})
    ap_prob = {d_["iata"]: d_["delay_prob"] for d_ in docs if d_["kind"] == "airport"}

    # ---- route (airline + origin + destination)
    keys = ["airline_id", "airline", "origin", "destination"]
    wd = x.groupBy(*keys).pivot("wd", list(range(7))).count().fillna(0)
    rt = x.groupBy(*keys).agg(
        F.count("*").alias("departures"), F.sum("delayed").alias("delayed"),
        F.avg("load_factor").alias("lf_mean"), F.stddev("load_factor").alias("lf_sd"),
        F.avg("passengers").alias("pax_mean"), F.stddev("passengers").alias("pax_sd"),
        F.avg("block_hours").alias("hist_block_mean"), F.stddev("block_hours").alias("hist_block_sd"),
        F.first("km").alias("distance_km"), F.collect_set("flight_number").alias("flight_numbers"))
    cab = (tf.join(x.select(F.col("flight_instance_id"), *keys), "flight_instance_id")
           .groupBy(*keys, "cabin_id").agg(F.count("*").alias("n"), F.avg("fare").alias("fare")))
    w = Window.partitionBy(*keys)
    cab = (cab.withColumn("share", F.col("n") / F.sum("n").over(w))
           .groupBy(*keys).agg(F.collect_list(F.struct("cabin_id", "share", "fare")).alias("cabins")))
    for r in _rows(rt.join(wd, keys).join(cab, keys, "left")):
        pa = ap_prob.get(r["origin"], p0)
        docs.append({
            "_id": f"route:{r['airline_id']}:{r['origin']}-{r['destination']}", "kind": "route",
            "airline_id": r["airline_id"], "airline": r["airline"], "origin": r["origin"],
            "destination": r["destination"], "route": f"{r['origin']}-{r['destination']}",
            "flight_numbers": sorted(r["flight_numbers"]), "departures": r["departures"],
            "departures_by_weekday": [r[str(i)] for i in range(7)],
            "lf_mean": round(r["lf_mean"], 4), "lf_sd": round(r["lf_sd"] or 0.0, 4),
            "pax_mean": round(r["pax_mean"], 1), "pax_sd": round(r["pax_sd"] or 0.0, 1),
            "cabin_share": {CABINS[c["cabin_id"]]: round(c["share"], 4) for c in r["cabins"] or []},
            "fare_by_cabin": {CABINS[c["cabin_id"]]: round(c["fare"], 2) for c in r["cabins"] or []},
            "delay_prob": round((r["delayed"] + SHRINK * pa) / (r["departures"] + SHRINK), 4),
            "hist_block_mean": round(r["hist_block_mean"], 2), "hist_block_sd": round(r["hist_block_sd"] or 0.0, 2),
            "distance_km": round(r["distance_km"], 1)})

    # ---- airline: weekday pattern, hub, fleet
    awd = _rows(x.groupBy("airline_id", "airline").pivot("wd", list(range(7))).count().fillna(0))
    hub = x.groupBy("airline_id", "origin").count().withColumn(
        "rn", F.row_number().over(Window.partitionBy("airline_id").orderBy(F.desc("count"), "origin")))
    hubs = {r["airline_id"]: r["origin"] for r in _rows(hub.where("rn = 1"))}
    lf = {r["airline_id"]: r for r in _rows(x.groupBy("airline_id").agg(
        F.avg("load_factor").alias("lf_mean"), F.avg("delayed").alias("delay_rate")))}
    for r in awd:
        by = [r[str(i)] for i in range(7)]
        mean = sum(by) / 7
        docs.append({"_id": f"airline:{r['airline_id']}", "kind": "airline", "airline_id": r["airline_id"],
                     "airline": r["airline"], "hub": hubs[r["airline_id"]], "departures_by_weekday": by,
                     "weekday_factor": [round(v / mean, 4) for v in by],
                     "lf_mean": round(lf[r["airline_id"]]["lf_mean"], 4),
                     "delay_rate": round(lf[r["airline_id"]]["delay_rate"], 4)})

    # ---- aircraft: last historical arrival airport = where the simulation starts it
    last = (x.withColumn("rn", F.row_number().over(
        Window.partitionBy("aircraft_id").orderBy(F.desc("arrival_time"))))
        .where("rn = 1").select("aircraft_id", F.col("destination").alias("location"),
                                F.date_format("arrival_time", "yyyy-MM-dd'T'HH:mm:ss").alias("last_arrival")))
    ac = (t["aircrafts"].join(t["aircraft_models"].withColumnRenamed("id", "model_id"), "model_id")
          .join(last, t["aircrafts"].id == last.aircraft_id, "left"))
    for r in _rows(ac):
        docs.append({"_id": f"aircraft:{r['id']}", "kind": "aircraft", "aircraft_id": r["id"],
                     "airline_id": r["airline_id"], "registration": r["registration_number"],
                     "model": r["model_number"], "capacity": r["capacity"], "status": r["status"],
                     "location": r["location"] or hubs.get(r["airline_id"]),
                     "last_arrival": r["last_arrival"]})
    x.unpersist()
    return docs
