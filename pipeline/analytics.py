"""Stage 3 - PySpark analytics (DataFrame API + Spark SQL + window functions).

Each function returns a small aggregated DataFrame; run_pipeline.py saves
every result to MongoDB (collection 'a_<name>') and to output/<run>/<name>.csv.
"""
from pyspark.sql import Window
from pyspark.sql import functions as F


def register_views(spark, t, ops, maint, payroll):
    for name, df in t.items():
        df.createOrReplaceTempView(name)
    ops.createOrReplaceTempView("flight_ops")
    maint.createOrReplaceTempView("maintenance_events")
    payroll.createOrReplaceTempView("payroll")


def kpi_summary(spark):
    return spark.sql("""
        SELECT COUNT(*)                                   AS departures,
               COUNT(DISTINCT route)                      AS routes,
               COUNT(DISTINCT aircraft_id)                AS aircraft_used,
               SUM(passengers)                            AS passenger_segments,
               ROUND(AVG(load_factor), 4)                 AS avg_load_factor,
               SUM(CAST(over_capacity AS INT))            AS over_capacity_departures,
               ROUND(SUM(fare_revenue), 2)                AS fare_revenue,
               ROUND(SUM(operating_cost_est), 2)          AS operating_cost_est,
               ROUND(SUM(operating_profit_est), 2)        AS operating_profit_est,
               ROUND(AVG(CAST(is_delayed AS INT)), 4)     AS delay_rate,
               ROUND(SUM(fuel_kg_est) / 1000, 1)          AS fuel_tonnes_est,
               MIN(dep_date) AS first_departure, MAX(dep_date) AS last_departure
        FROM flight_ops""")


def monthly_trend(ops):
    """Monthly revenue/cost/profit with running totals (window SUM)
    and month-on-month growth (window LAG)."""
    m = (ops.groupBy("year_month")
         .agg(F.count("*").alias("departures"), F.sum("passengers").alias("passengers"),
              F.round(F.sum("fare_revenue"), 2).alias("fare_revenue"),
              F.round(F.sum("operating_cost_est"), 2).alias("operating_cost_est"),
              F.round(F.sum("operating_profit_est"), 2).alias("operating_profit_est"),
              F.round(F.avg("load_factor"), 4).alias("avg_load_factor")))
    w = Window.orderBy("year_month")
    run = w.rowsBetween(Window.unboundedPreceding, Window.currentRow)
    prev = F.lag("fare_revenue").over(w)
    return (m.withColumn("cumulative_revenue", F.round(F.sum("fare_revenue").over(run), 2))
            .withColumn("revenue_mom_growth", F.round((F.col("fare_revenue") - prev) / prev, 4))
            .withColumn("revenue_3m_moving_avg",
                        F.round(F.avg("fare_revenue").over(w.rowsBetween(-2, 0)), 2))
            .orderBy("year_month"))


def route_profitability(ops):
    """Route P&L, ranked within each airline (window RANK) and share of the
    airline's revenue (window SUM over partition)."""
    r = (ops.groupBy("airline", "route", "origin", "destination")
         .agg(F.count("*").alias("departures"), F.sum("passengers").alias("passengers"),
              F.round(F.avg("load_factor"), 4).alias("avg_load_factor"),
              F.round(F.sum("fare_revenue"), 2).alias("revenue"),
              F.round(F.sum("fuel_cost_est"), 2).alias("fuel_cost_est"),
              F.round(F.sum("crew_cost_est"), 2).alias("crew_cost_est"),
              F.round(F.sum("airport_fee_est"), 2).alias("airport_fee_est"),
              F.round(F.sum("ownership_overhead_est"), 2).alias("ownership_overhead_est"),
              F.round(F.sum("operating_profit_est"), 2).alias("profit_est")))
    w = Window.partitionBy("airline")
    return (r.withColumn("margin_est", F.round(F.col("profit_est") / F.col("revenue"), 4))
            .withColumn("rank_in_airline", F.rank().over(w.orderBy(F.desc("profit_est"))))
            .withColumn("share_of_airline_revenue",
                        F.round(F.col("revenue") / F.sum("revenue").over(w), 4))
            .orderBy("airline", "rank_in_airline"))


def airline_pnl(spark):
    """Airline-level simplified P&L. Revenue = fares (gross). Promotions and
    refunds are shown separately so nothing is double counted."""
    return spark.sql("""
        WITH ops AS (
            SELECT airline_id, airline, COUNT(*) departures, SUM(passengers) passengers,
                   SUM(fare_revenue) fare_revenue, SUM(fuel_cost_est) fuel,
                   SUM(crew_cost_est) crew,
                   SUM(airport_fee_est + COALESCE(ownership_overhead_est, 0)) fees,
                   SUM(airport_fee_est) airport_fees, SUM(ownership_overhead_est) overhead
            FROM flight_ops GROUP BY airline_id, airline),
        mx AS (
            SELECT a.airline_id, SUM(m.cost_est) maintenance
            FROM maintenance_events m JOIN aircrafts a ON a.id = m.aircraft_id
            GROUP BY a.airline_id)
        SELECT o.airline, o.departures, o.passengers,
               ROUND(o.fare_revenue, 2)                         AS fare_revenue,
               ROUND(o.fuel, 2)                                 AS fuel_cost_est,
               ROUND(o.crew, 2)                                 AS crew_cost_est,
               ROUND(o.airport_fees, 2)                         AS airport_fee_est,
               ROUND(o.overhead, 2)                             AS ownership_overhead_est,
               ROUND(COALESCE(mx.maintenance, 0), 2)            AS maintenance_cost_est,
               ROUND(o.fare_revenue - o.fuel - o.crew - o.fees
                     - COALESCE(mx.maintenance, 0), 2)          AS operating_profit_est,
               ROUND((o.fare_revenue - o.fuel - o.crew - o.fees
                     - COALESCE(mx.maintenance, 0)) / o.fare_revenue, 4) AS margin_est,
               ROUND((o.fuel + o.crew + o.fees + COALESCE(mx.maintenance, 0))
                     / NULLIF(o.passengers, 0), 2)              AS cost_per_passenger_est
        FROM ops o LEFT JOIN mx ON mx.airline_id = o.airline_id
        ORDER BY operating_profit_est DESC""")


def delay_analysis(spark):
    by_reason = spark.sql("""
        SELECT delay_reason, COUNT(*) AS delays,
               ROUND(AVG(delay_minutes), 1) AS avg_minutes,
               PERCENTILE_APPROX(delay_minutes, 0.9) AS p90_minutes,
               ROUND(COUNT(*) / SUM(COUNT(*)) OVER (), 4) AS share
        FROM flight_ops WHERE is_delayed GROUP BY delay_reason ORDER BY delays DESC""")
    by_airport = spark.sql("""
        SELECT origin AS airport, COUNT(*) AS departures,
               SUM(CAST(is_delayed AS INT)) AS delayed,
               ROUND(AVG(CAST(is_delayed AS INT)), 4) AS delay_rate,
               ROUND(AVG(CASE WHEN is_delayed THEN delay_minutes END), 1) AS avg_delay_minutes,
               DENSE_RANK() OVER (ORDER BY AVG(CAST(is_delayed AS INT)) DESC) AS worst_rank
        FROM flight_ops GROUP BY origin HAVING COUNT(*) >= 1 ORDER BY worst_rank""")
    by_model = spark.sql("""
        SELECT model_number, COUNT(*) AS departures,
               ROUND(AVG(CAST(is_delayed AS INT)), 4) AS delay_rate,
               ROUND(AVG(delay_minutes), 1) AS avg_delay_minutes_all_flights
        FROM flight_ops GROUP BY model_number ORDER BY delay_rate DESC""")
    return by_reason, by_airport, by_model


def aircraft_utilization(ops, maint):
    """Block hours per aircraft, downtime from maintenance, and a rank of
    utilisation within each aircraft model."""
    u = (ops.groupBy("aircraft_id", "registration_number", "model_number", "airline")
         .agg(F.count("*").alias("departures"),
              F.round(F.sum("block_hours"), 1).alias("block_hours"),
              F.countDistinct("year_month").alias("active_months")))
    d = maint.groupBy("aircraft_id").agg(F.sum("downtime_hours").alias("maintenance_downtime_hours"),
                                         F.round(F.sum("cost_est"), 2).alias("maintenance_cost_est"),
                                         F.count("*").alias("maintenance_events"))
    w = Window.partitionBy("model_number").orderBy(F.desc("block_hours"))
    return (u.join(d, "aircraft_id", "left").fillna(0, ["maintenance_downtime_hours",
                                                        "maintenance_cost_est", "maintenance_events"])
            .withColumn("block_hours_per_active_month",
                        F.round(F.col("block_hours") / F.col("active_months"), 2))
            .withColumn("rank_in_model", F.row_number().over(w))
            .orderBy(F.desc("block_hours")))


def fuel_efficiency(ops):
    return (ops.where("block_hours IS NOT NULL")
            .groupBy("model_number", "capacity")
            .agg(F.count("*").alias("departures"),
                 F.round(F.sum("fuel_kg_est") / 1000, 2).alias("fuel_tonnes_est"),
                 F.round(F.sum("fuel_cost_est"), 2).alias("fuel_cost_est"),
                 F.round(F.sum("fuel_kg_est") / F.sum(F.col("block_hours") * F.col("capacity")), 3)
                 .alias("kg_per_seat_hour_est"),
                 F.round(F.sum("fuel_cost_est") / F.sum("passengers"), 2).alias("fuel_cost_per_passenger_est"),
                 F.round(F.avg("load_factor"), 4).alias("avg_load_factor"))
            .orderBy("kg_per_seat_hour_est"))


def cabin_fares(spark):
    return spark.sql("""
        SELECT c.name AS cabin, COUNT(*) AS segments,
               ROUND(AVG(tf.fare), 2) AS avg_fare,
               PERCENTILE_APPROX(tf.fare, 0.5) AS median_fare,
               MIN(tf.fare) AS min_fare, MAX(tf.fare) AS max_fare,
               ROUND(SUM(tf.fare), 2) AS revenue,
               ROUND(SUM(tf.fare) / SUM(SUM(tf.fare)) OVER (), 4) AS revenue_share,
               SUM(CAST(tf.fare_imputed AS INT)) AS fares_imputed
        FROM ticket_flights tf JOIN cabins c ON c.id = tf.cabin_id
        GROUP BY c.id, c.name ORDER BY c.id""")


def booking_behaviour(spark):
    lead = spark.sql("""
        WITH first_dep AS (
            SELECT t.booking_id, MIN(fi.departure_time) AS first_departure
            FROM tickets t JOIN ticket_flights tf ON tf.ticket_id = t.id
            JOIN flight_instances fi ON fi.id = tf.flight_instance_id
            GROUP BY t.booking_id),
        lt AS (
            SELECT DATEDIFF(f.first_departure, b.booking_date) AS days
            FROM bookings b JOIN first_dep f ON f.booking_id = b.id
            WHERE b.booking_date IS NOT NULL)
        SELECT CASE WHEN days < 7 THEN '1: under a week'
                    WHEN days < 30 THEN '2: 1-4 weeks'
                    WHEN days < 60 THEN '3: 1-2 months'
                    ELSE '4: 2+ months' END AS lead_time,
               COUNT(*) AS bookings, ROUND(AVG(days), 1) AS avg_days
        FROM lt WHERE days >= 0 GROUP BY 1 ORDER BY 1""")
    payments = spark.sql("""
        SELECT p.payment_method, COUNT(*) AS payments,
               ROUND(SUM(p.amount), 2) AS amount,
               COUNT(r.id) AS refunds,
               ROUND(COALESCE(SUM(r.amount), 0), 2) AS refunded,
               ROUND(COUNT(r.id) / COUNT(*), 4) AS refund_rate
        FROM payments p LEFT JOIN refunds r ON r.payment_id = p.id
        WHERE p.payment_method IS NOT NULL
        GROUP BY p.payment_method ORDER BY payments DESC""")
    promos = spark.sql("""
        SELECT pr.code AS promotion, pr.discount_percentage, COUNT(DISTINCT b.id) AS bookings,
               ROUND(SUM(t.total_price), 2) AS ticket_value,
               ROUND(SUM(t.total_price) * pr.discount_percentage / 100, 2) AS discount_given
        FROM bookings b JOIN promotions pr ON pr.id = b.promotion_id
        JOIN tickets t ON t.booking_id = b.id
        GROUP BY pr.code, pr.discount_percentage ORDER BY bookings DESC""")
    return lead, payments, promos


def airport_traffic(ops):
    dep = ops.groupBy(F.col("origin").alias("airport"), F.col("origin_name").alias("name")) \
        .agg(F.count("*").alias("departures"), F.sum("passengers").alias("pax_out"))
    arr = ops.groupBy(F.col("destination").alias("airport")) \
        .agg(F.count("*").alias("arrivals"), F.sum("passengers").alias("pax_in"))
    return (dep.join(arr, "airport", "full").fillna(0)
            .withColumn("total_movements", F.col("departures") + F.col("arrivals"))
            .withColumn("rank", F.dense_rank().over(Window.orderBy(F.desc("total_movements"))))
            .orderBy("rank"))


def crew_utilization(spark):
    return spark.sql("""
        SELECT COALESCE(c.role, 'unknown') AS role, COUNT(DISTINCT c.id) AS crew_members,
               COUNT(fc.id) AS duties,
               ROUND(COUNT(fc.id) / COUNT(DISTINCT c.id), 2) AS duties_per_member,
               ROUND(SUM(fo.block_hours), 1) AS block_hours,
               ROUND(AVG(p.monthly_salary_est), 0) AS monthly_salary_est
        FROM crews c
        LEFT JOIN flight_crews fc ON fc.crew_id = c.id
        LEFT JOIN flight_ops fo ON fo.flight_instance_id = fc.flight_instance_id
        LEFT JOIN payroll p ON p.id = c.id
        GROUP BY COALESCE(c.role, 'unknown') ORDER BY duties DESC""")


def sim_daily(spark, ops):
    """One row per calendar day (days without flights included) for the
    dashboard's simulation: daily totals plus running totals (window SUM) and a
    true 7-day moving average (window AVG over the last 7 rows)."""
    b = ops.agg(F.min("dep_date").alias("lo"), F.max("dep_date").alias("hi")).first()
    days = spark.sql(f"SELECT explode(sequence(to_date('{b.lo}'), to_date('{b.hi}'), interval 1 day)) AS dep_date")
    d = (ops.groupBy("dep_date")
         .agg(F.count("*").alias("departures"), F.sum("passengers").alias("passengers"),
              F.sum("fare_revenue").alias("revenue"),
              F.sum("operating_cost_est").alias("operating_cost_est"),
              F.sum("operating_profit_est").alias("operating_profit_est"),
              F.sum(F.col("is_delayed").cast("int")).alias("delayed")))
    w = Window.orderBy("dep_date")
    return (days.join(d, "dep_date", "left")
            .fillna(0, ["departures", "passengers", "revenue", "operating_cost_est",
                        "operating_profit_est", "delayed"])
            .withColumn("cumulative_revenue", F.round(F.sum("revenue").over(
                w.rowsBetween(Window.unboundedPreceding, 0)), 2))
            .withColumn("cumulative_profit_est", F.round(F.sum("operating_profit_est").over(
                w.rowsBetween(Window.unboundedPreceding, 0)), 2))
            .withColumn("revenue_7d_avg", F.round(F.avg("revenue").over(w.rowsBetween(-6, 0)), 2))
            .withColumn("day_of_week", F.date_format("dep_date", "EEEE"))
            .withColumn("date", F.date_format("dep_date", "yyyy-MM-dd"))
            .withColumn("revenue", F.round("revenue", 2))
            .withColumn("operating_cost_est", F.round("operating_cost_est", 2))
            .withColumn("operating_profit_est", F.round("operating_profit_est", 2))
            .select("date", "day_of_week", "departures", "passengers", "revenue", "operating_cost_est",
                    "operating_profit_est", "delayed", "cumulative_revenue", "cumulative_profit_est",
                    "revenue_7d_avg")
            .orderBy("date"))


def sim_daily_airline(ops):
    return (ops.groupBy(F.date_format("dep_date", "yyyy-MM-dd").alias("date"), "airline")
            .agg(F.count("*").alias("departures"), F.sum("passengers").alias("passengers"),
                 F.round(F.sum("fare_revenue"), 2).alias("revenue"),
                 F.round(F.sum("operating_profit_est"), 2).alias("operating_profit_est"),
                 F.sum(F.col("is_delayed").cast("int")).alias("delayed"))
            .orderBy("date", "airline"))


def run_all(spark, t, ops, maint, payroll):
    register_views(spark, t, ops, maint, payroll)
    d_reason, d_airport, d_model = delay_analysis(spark)
    lead, pay, promos = booking_behaviour(spark)
    return {
        "kpi_summary": kpi_summary(spark),
        "monthly_trend": monthly_trend(ops),
        "route_profitability": route_profitability(ops),
        "airline_pnl": airline_pnl(spark),
        "delays_by_reason": d_reason,
        "delays_by_airport": d_airport,
        "delays_by_aircraft_model": d_model,
        "aircraft_utilization": aircraft_utilization(ops, maint),
        "fuel_efficiency": fuel_efficiency(ops),
        "cabin_fares": cabin_fares(spark),
        "booking_lead_time": lead,
        "payments_and_refunds": pay,
        "promotions": promos,
        "airport_traffic": airport_traffic(ops),
        "crew_utilization": crew_utilization(spark),
        "sim_daily": sim_daily(spark, ops),
        "sim_daily_airline": sim_daily_airline(ops),
    }
