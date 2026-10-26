"""Stage 2 - build the 'digital twin' flight_ops table and synthetic records.

flight_ops = one row per departure (flight_instance) combining real source
fields (route, airline, aircraft, times, passengers, fares, delays, crew)
with synthetic estimates (fuel, crew cost, airport fees) from config.py.
Every synthetic column is named *_est and the row carries is_estimate=True.
"""
from itertools import chain

from pyspark.sql import functions as F

import config as C


def _map(d):
    return F.create_map(*chain.from_iterable((F.lit(k), F.lit(v)) for k, v in d.items()))


def build_flight_ops(t):
    ap = t["airports"].select("id", "iata_code", "name")
    dep = ap.select(F.col("id").alias("departure_airport_id"),
                    F.col("iata_code").alias("origin"), F.col("name").alias("origin_name"))
    arr = ap.select(F.col("id").alias("arrival_airport_id"),
                    F.col("iata_code").alias("destination"), F.col("name").alias("destination_name"))

    flights = (t["flights"]
               .join(F.broadcast(dep), "departure_airport_id")
               .join(F.broadcast(arr), "arrival_airport_id")
               .join(F.broadcast(t["airlines"].select(F.col("id").alias("airline_id"),
                                                      F.col("name").alias("airline"),
                                                      F.col("iata_code").alias("airline_code"))),
                     "airline_id")
               .select(F.col("id").alias("flight_id"), "flight_number", "airline_id", "airline",
                       "airline_code", "origin", "destination", "origin_name", "destination_name"))

    aircraft = (t["aircrafts"].join(F.broadcast(t["aircraft_models"]
                                                .withColumnRenamed("id", "model_id")), "model_id")
                .select(F.col("id").alias("aircraft_id"), "registration_number",
                        "model_number", "manufacturer", "capacity"))

    pax = (t["ticket_flights"].groupBy("flight_instance_id")
           .agg(F.count("*").alias("passengers"),
                F.sum("fare").cast("double").alias("fare_revenue"),
                F.sum(F.when(F.col("cabin_id") <= 2, 1).otherwise(0)).alias("premium_passengers")))

    delays = t["flight_delays"].groupBy("flight_instance_id").agg(
        F.sum("duration_minutes").alias("delay_minutes"),
        F.coalesce(F.first("delay_reason", ignorenulls=True), F.lit("Unknown")).alias("delay_reason"))

    crew = (t["flight_crews"].groupBy("flight_instance_id")
            .agg(F.count("*").alias("crew_count"),
                 F.sum(F.coalesce(_map(C.CREW_RATE_PER_HR)[F.col("role_assigned")], F.lit(40)))
                 .alias("_crew_rate_per_hr")))

    fi = t["flight_instances"].withColumnRenamed("id", "flight_instance_id")
    block_h = F.when(F.col("times_valid"),
                     (F.unix_timestamp("arrival_time") - F.unix_timestamp("departure_time")) / 3600)
    burn = F.coalesce(_map(C.FUEL_BURN_KG_PER_HR)[F.col("model_number")],
                      F.lit(C.DEFAULT_FUEL_BURN_KG_PER_HR))

    ops = (fi.join(flights, "flight_id")
           .join(F.broadcast(aircraft), "aircraft_id")
           .join(pax, "flight_instance_id", "left")
           .join(delays, "flight_instance_id", "left")
           .join(crew, "flight_instance_id", "left")
           .withColumn("route", F.concat_ws("-", "origin", "destination"))
           .withColumn("block_hours", F.round(block_h, 2))
           .withColumn("passengers", F.coalesce("passengers", F.lit(0)))
           .withColumn("premium_passengers", F.coalesce("premium_passengers", F.lit(0)))
           .withColumn("fare_revenue", F.round(F.coalesce("fare_revenue", F.lit(0.0)), 2))
           .withColumn("delay_minutes", F.coalesce("delay_minutes", F.lit(0)))
           .withColumn("is_delayed", F.col("delay_minutes") >= 15)
           .withColumn("crew_count", F.coalesce("crew_count", F.lit(0)))
           .withColumn("load_factor", F.round(F.col("passengers") / F.col("capacity"), 4))
           # The source sells ~100 tickets per departure whatever the aircraft size, so
           # small aircraft can exceed 100%. Passenger counts stay real; flag, don't cap.
           .withColumn("over_capacity", F.col("passengers") > F.col("capacity"))
           .withColumn("dep_date", F.to_date("departure_time"))
           .withColumn("year_month", F.date_format("departure_time", "yyyy-MM"))
           # ---- synthetic estimates (documented in config.py) ----
           .withColumn("fuel_kg_est", F.round(burn * F.col("block_hours") + C.TAXI_FUEL_KG, 1))
           .withColumn("fuel_cost_est", F.round(F.col("fuel_kg_est") * C.FUEL_PRICE_PER_KG, 2))
           .withColumn("crew_cost_est", F.round(F.coalesce("_crew_rate_per_hr", F.lit(0))
                                                * F.col("block_hours"), 2))
           .withColumn("airport_fee_est", F.round(F.lit(C.AIRPORT_FEE_BASE)
                                                  + F.col("capacity") * C.AIRPORT_FEE_PER_SEAT, 2))
           .withColumn("ownership_overhead_est", F.round(F.lit(C.OWNERSHIP_OVERHEAD_PER_SEAT_HOUR)
                                                         * F.col("capacity") * F.col("block_hours"), 2))
           .withColumn("operating_cost_est", F.round(F.col("fuel_cost_est") + F.col("crew_cost_est")
                                                     + F.col("airport_fee_est")
                                                     + F.coalesce("ownership_overhead_est", F.lit(0)), 2))
           .withColumn("operating_profit_est", F.round(F.col("fare_revenue")
                                                       - F.col("operating_cost_est"), 2))
           .withColumn("is_estimate", F.lit(True))
           .drop("_crew_rate_per_hr", "times_valid"))
    return ops.localCheckpoint(eager=True)


def generate_maintenance(spark, t):
    """Synthetic maintenance events: each aircraft x each month of the data
    range gets events with the probabilities in config.MAINTENANCE_TYPES.
    Uses a seeded hash rather than rand() so output is identical every run,
    regardless of partitioning."""
    fi = t["flight_instances"]
    bounds = fi.agg(F.min("departure_time").alias("lo"), F.max("departure_time").alias("hi")).first()
    if bounds.lo is None:
        return spark.createDataFrame([], "aircraft_id long")
    months = spark.sql(
        f"SELECT explode(sequence(trunc(to_date('{bounds.lo.date()}'),'MM'), "
        f"to_date('{bounds.hi.date()}'), interval 1 month)) AS month")
    ac = (t["aircrafts"].join(t["aircraft_models"].withColumnRenamed("id", "model_id"), "model_id")
          .select(F.col("id").alias("aircraft_id"), "registration_number", "model_number", "capacity"))
    types = spark.createDataFrame(
        [(k, float(p), float(b), float(c), int(h)) for k, (p, b, c, h) in C.MAINTENANCE_TYPES.items()],
        "maintenance_type string, prob double, base_cost double, cost_per_seat double, downtime_hours int")
    grid = ac.crossJoin(F.broadcast(months)).crossJoin(F.broadcast(types))
    u = (F.abs(F.xxhash64("aircraft_id", "month", "maintenance_type", F.lit(C.SEED))) % 1_000_000) / 1e6
    day = (F.abs(F.xxhash64("aircraft_id", "month", F.lit(C.SEED + 1))) % 28).cast("int")
    return (grid.where(u < F.col("prob"))
            .withColumn("event_date", F.date_add("month", day))
            .withColumn("year_month", F.date_format("event_date", "yyyy-MM"))
            .withColumn("cost_est", F.round(F.col("base_cost") + F.col("cost_per_seat") * F.col("capacity")
                                            * (0.8 + 0.4 * u / F.col("prob")), 2))
            .withColumn("is_synthetic", F.lit(True))
            .select(F.monotonically_increasing_id().alias("id"), "aircraft_id", "registration_number",
                    "model_number", "maintenance_type", "event_date", "year_month",
                    "downtime_hours", "cost_est", "is_synthetic")
            .localCheckpoint(eager=True))


def build_payroll(t):
    """Synthetic monthly payroll: role-based salary for every crew member."""
    sal = _map(C.CREW_MONTHLY_SALARY)
    return (t["crews"].select("id", "first_name", "last_name", "role")
            .withColumn("monthly_salary_est", F.coalesce(sal[F.col("role")], F.lit(4000)))
            .withColumn("is_synthetic", F.lit(True)).cache())
