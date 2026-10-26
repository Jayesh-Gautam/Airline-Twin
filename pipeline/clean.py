"""Stage 1 - ingest the source CSVs and clean them with PySpark.

Works on both the clean files and the published "dirty" copy, which has
missing values, typos, wrong case, stray spaces, 10x/negative outliers,
exact and near duplicate rows, mixed date formats, out-of-order dates and
orphaned foreign keys. On clean data every fix is simply a no-op, and the
data-quality report shows zeros.
"""
import glob
import os

from pyspark.sql import Window
from pyspark.sql import functions as F

# Table specs. Types: int, dec, ts, date, str.
#   fks          (column, parent table)  -> orphans removed, NULL FK dropped
#   soft_fks     (column, parent table)  -> orphan key set to NULL, row kept
#                (used where losing the row would cascade, e.g. one airport
#                 with a bad city_id would otherwise remove all its flights)
#   categorical  column -> allowed values -> typos repaired by edit distance
#   outliers     (column, group column or None) -> IQR fence + negatives
#   key          business key: rows sharing it are duplicates even when their ids differ
#                (the dirty copy appends duplicates under NEW sequential ids)
#   negatives    columns where only negative values are treated as invalid
#                (their 10x outliers are caught by business rules instead)
SPECS = {
    "countries": {"cols": {"id": "int", "iso_code": "str", "name": "str"}, "key": ["iso_code"]},
    "cities": {"cols": {"id": "int", "country_id": "int", "name": "str"}, "key": ["country_id", "name"],
               "soft_fks": [("country_id", "countries")]},
    "airports": {"cols": {"id": "int", "city_id": "int", "iata_code": "str",
                          "icao_code": "str", "name": "str"},
                 "key": ["iata_code"], "soft_fks": [("city_id", "cities")]},
    "airlines": {"cols": {"id": "int", "country_id": "int", "iata_code": "str", "name": "str"}, "key": ["iata_code"],
                 "soft_fks": [("country_id", "countries")]},
    "aircraft_models": {"cols": {"id": "int", "capacity": "int", "manufacturer": "str",
                                 "model_number": "str"}, "key": ["model_number"]},
    "aircrafts": {"cols": {"id": "int", "airline_id": "int", "model_id": "int",
                           "registration_number": "str", "status": "str"},
                  "key": ["registration_number"], "fks": [("airline_id", "airlines"), ("model_id", "aircraft_models")],
                  "categorical": {"status": ["in_service", "maintenance"]}},
    "cabins": {"cols": {"id": "int", "class_code": "str", "name": "str"}, "key": ["class_code"]},
    "promotions": {"cols": {"id": "int", "code": "str", "discount_percentage": "int",
                            "start_date": "date", "end_date": "date"}, "key": ["code"]},
    "crews": {"cols": {"id": "int", "first_name": "str", "last_name": "str",
                       "license_number": "str", "role": "str"},
              "key": ["license_number"], "categorical": {"role": ["captain", "first_officer", "purser", "flight_attendant"]}},
    "flights": {"cols": {"id": "int", "airline_id": "int", "departure_airport_id": "int",
                         "arrival_airport_id": "int", "flight_number": "str"},
                "key": ["airline_id", "flight_number"], "fks": [("airline_id", "airlines"), ("departure_airport_id", "airports"),
                        ("arrival_airport_id", "airports")]},
    "flight_instances": {"cols": {"id": "int", "flight_id": "int", "aircraft_id": "int",
                                  "departure_time": "ts", "arrival_time": "ts", "status": "str"},
                         "key": ["flight_id", "departure_time"], "fks": [("flight_id", "flights"), ("aircraft_id", "aircrafts")],
                         "lower": ["status"]},
    "flight_delays": {"cols": {"id": "int", "flight_instance_id": "int", "delay_reason": "str",
                               "duration_minutes": "int"},
                      "key": ["flight_instance_id"], "fks": [("flight_instance_id", "flight_instances")],
                      "categorical": {"delay_reason": ["Weather", "Air traffic control",
                                                       "Late inbound aircraft", "Technical", "Crew"]},
                      "outliers": [("duration_minutes", None)]},
    "flight_crews": {"cols": {"id": "int", "crew_id": "int", "flight_instance_id": "int",
                              "role_assigned": "str"},
                     "key": ["crew_id", "flight_instance_id"], "fks": [("crew_id", "crews"), ("flight_instance_id", "flight_instances")],
                     "categorical": {"role_assigned": ["captain", "first_officer", "purser", "cabin"]}},
    "bookings": {"cols": {"id": "int", "user_id": "int", "promotion_id": "int",
                          "booking_reference": "str", "booking_date": "ts", "status": "str"},
                 "key": ["booking_reference"], "soft_fks": [("promotion_id", "promotions")], "lower": ["status"]},
    "tickets": {"cols": {"id": "int", "booking_id": "int", "passenger_id": "int",
                         "ticket_number": "str", "total_price": "dec"},
                "key": ["ticket_number"], "fks": [("booking_id", "bookings")],
                "negatives": ["total_price"]},
    "ticket_flights": {"cols": {"id": "int", "ticket_id": "int", "flight_instance_id": "int",
                                "seat_id": "int", "cabin_id": "int", "fare": "dec"},
                       "key": ["flight_instance_id", "seat_id"], "fks": [("ticket_id", "tickets"), ("flight_instance_id", "flight_instances"),
                               ("cabin_id", "cabins")],
                       "outliers": [("fare", "cabin_id")]},
    "payments": {"cols": {"id": "int", "booking_id": "int", "amount": "dec",
                          "payment_date": "ts", "payment_method": "str",
                          "transaction_status": "str"},
                 "key": ["booking_id"], "fks": [("booking_id", "bookings")],
                 "categorical": {"payment_method": ["card", "paypal", "apple_pay", "bank_transfer"]},
                 "lower": ["transaction_status"],
                 "negatives": ["amount"]},
    "refunds": {"cols": {"id": "int", "payment_id": "int", "amount": "dec",
                         "refund_date": "ts", "reason": "str"},
                "key": ["payment_id"], "fks": [("payment_id", "payments")],
                "categorical": {"reason": ["Schedule change", "Cancelled by customer",
                                           "Duplicate booking", "Medical", "Downgrade"]},
                "negatives": ["amount"]},
}
TABLE_ORDER = list(SPECS)  # parents always come before children

DATE_FORMATS = [
    "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd HH:mm:ss.SSSSSS",
    "yyyy-MM-dd HH:mm", "yyyy-MM-dd'T'HH:mm:ss'Z'", "yyyy-MM-dd", "yyyy/MM/dd HH:mm:ss", "yyyy/MM/dd",
    "dd/MM/yyyy HH:mm:ss", "dd/MM/yyyy HH:mm", "dd/MM/yyyy", "MM/dd/yyyy",
    "dd-MM-yyyy HH:mm:ss", "dd-MM-yyyy", "dd.MM.yyyy", "dd MMM yyyy",
    "MMM d, yyyy HH:mm", "MMM d, yyyy HH:mm:ss", "MMM d, yyyy",
    "yyyyMMdd",
]


def find_csv(data_dir, table):
    hits = glob.glob(os.path.join(data_dir, "**", f"{table}.csv"), recursive=True)
    if not hits:
        raise FileNotFoundError(f"{table}.csv not found under {data_dir}")
    return hits[0]


def parse_ts(c):
    c = F.trim(c)
    return F.coalesce(c.cast("timestamp"), *[F.to_timestamp(c, f) for f in DATE_FORMATS])


def repair_category(c, allowed):
    """Map a dirty categorical value to the nearest allowed value
    (case/space-insensitive, Levenshtein distance <= 2), else NULL."""
    norm = F.lower(F.trim(c))
    dists = [F.levenshtein(norm, F.lit(v.lower())) for v in allowed]
    best = F.least(*dists) if len(dists) > 1 else dists[0]
    pick = F.coalesce(*[F.when(d == best, F.lit(v)) for d, v in zip(dists, allowed)])
    return F.when(best <= 2, pick)


def _typed(df, spec):
    out = []
    for col, typ in spec["cols"].items():
        raw = F.trim(F.col(col)) if col in df.columns else F.lit(None).cast("string")
        if typ == "int":
            v = raw.cast("double").cast("long")
        elif typ == "dec":
            v = raw.cast("decimal(14,2)")
        elif typ == "ts":
            v = parse_ts(raw)
        elif typ == "date":
            v = F.to_date(parse_ts(raw))
        else:
            v = F.when(raw != "", raw)
        out.append(v.alias(col))
    return df.select(*out)


def clean_table(spark, data_dir, table, cleaned):
    spec = SPECS[table]
    raw = spark.read.csv(find_csv(data_dir, table), header=True, inferSchema=False).cache()
    stats = {"table": table, "rows_raw": raw.count()}

    # 1. exact duplicate rows: identical in every column except the id (duplicates are
    #    appended under new ids); the lowest id survives
    value_cols = [c for c in raw.columns if c != "id"]
    w_exact = Window.partitionBy(*value_cols).orderBy(F.col("id").cast("double"))
    dedup = (raw.withColumn("_rn", F.row_number().over(w_exact)).where("_rn = 1").drop("_rn").cache()
             if value_cols else raw.dropDuplicates().cache())
    stats["exact_duplicates"] = stats["rows_raw"] - dedup.count()

    # 2. types + string/date normalisation
    df = _typed(dedup, spec)
    stats["unparsed_dates"] = 0
    for col, typ in spec["cols"].items():
        if typ in ("ts", "date") and col in dedup.columns:
            stats["unparsed_dates"] += (
                dedup.where(F.trim(F.col(col)) != "")
                .select(parse_ts(F.col(col)).alias("v")).where("v IS NULL").count())
    for col in spec.get("lower", []):
        df = df.withColumn(col, F.lower(F.col(col)))

    # 3. categorical typo repair
    fixed = 0
    for col, allowed in spec.get("categorical", {}).items():
        before = F.col(col)
        df = df.withColumn(f"_{col}_fixed", repair_category(before, allowed))
        fixed += df.where(F.col(col).isNotNull() & ~F.col(col).isin(allowed)).count()
        df = df.withColumn(col, F.col(f"_{col}_fixed")).drop(f"_{col}_fixed")
    stats["category_values_repaired"] = fixed
    df = df.cache()

    # 4. near duplicates: same primary key, one value different -> keep the
    #    most complete version of the row
    #    (same id, or same business key under a different id)
    nulls = sum(F.col(c).isNull().cast("int") for c in spec["cols"])
    w = Window.partitionBy("id").orderBy(nulls.asc())
    before = df.count()
    df = (df.where(F.col("id").isNotNull())
          .withColumn("_rn", F.row_number().over(w)).where("_rn = 1").drop("_rn"))
    key = spec.get("key")
    if key:
        kexpr = [F.lower(F.col(k)) if spec["cols"][k] == "str" else F.col(k) for k in key]
        complete = F.lit(True)
        for k in key:
            complete = complete & F.col(k).isNotNull()
        wk = Window.partitionBy(*kexpr).orderBy(nulls.asc(), F.col("id").asc())
        # rows with a missing key part cannot be matched, so they are kept
        df = (df.withColumn("_rn", F.row_number().over(wk))
              .where(~complete | (F.col("_rn") == 1)).drop("_rn"))
    stats["near_duplicates"] = before - df.count()

    # 5. outliers: negatives and values beyond Q3 + 3*IQR (optionally per group)
    out_n = 0
    for col, group in spec.get("outliers", []):
        g = F.col(group) if group else F.lit(1)
        fences = (df.where(F.col(col) >= 0).groupBy(g.alias("_g"))
                  .agg(F.percentile_approx(col, [0.25, 0.75], 1000).alias("_q")))
        df = df.join(F.broadcast(fences), g == F.col("_g"), "left")
        upper = F.col("_q")[1] + 3 * (F.col("_q")[1] - F.col("_q")[0])
        bad = (F.col(col) < 0) | (F.col(col) > upper)
        out_n += df.where(bad).count()
        df = df.withColumn(col, F.when(bad, None).otherwise(F.col(col))).drop("_g", "_q")
    for col in spec.get("negatives", []):
        out_n += df.where(F.col(col) < 0).count()
        df = df.withColumn(col, F.when(F.col(col) < 0, None).otherwise(F.col(col)))
    stats["outliers_nulled"] = out_n

    # 6. referential integrity: drop NULL / orphaned foreign keys
    before = df.count()
    for fk, parent in spec.get("fks", []):
        df = df.where(F.col(fk).isNotNull()).join(
            cleaned[parent].select(F.col("id").alias(fk)), fk, "left_semi")
    stats["orphan_rows_removed"] = before - df.count()
    soft = 0
    for fk, parent in spec.get("soft_fks", []):
        ok = cleaned[parent].select(F.col("id").alias("_pk"), F.lit(True).alias("_ok"))
        df = df.join(F.broadcast(ok), F.col(fk) == F.col("_pk"), "left")
        soft += df.where(F.col(fk).isNotNull() & F.col("_ok").isNull()).count()
        df = df.withColumn(fk, F.when(F.col("_ok"), F.col(fk))).drop("_pk", "_ok")
    stats["orphan_keys_nulled"] = soft

    # localCheckpoint materialises the result and cuts the query lineage, so
    # later joins don't re-plan (or re-run) every cleaning step.
    df = df.localCheckpoint(eager=True)
    stats["rows_clean"] = df.count()
    raw.unpersist(); dedup.unpersist()
    stats["null_values_remaining"] = df.select(
        sum(F.col(c).isNull().cast("int") for c in spec["cols"]).alias("n")
    ).agg(F.sum("n")).first()[0] or 0
    return df, stats


def repair_business_rules(t):
    """Rules the source data is documented to keep; re-impose them after cleaning."""
    stats = {}
    # fare missing -> median fare of the same cabin on the same departure, else cabin median
    tf = t["ticket_flights"]
    med_inst = tf.groupBy("flight_instance_id", "cabin_id").agg(
        F.percentile_approx("fare", 0.5).alias("_m1"))
    med_cab = tf.groupBy("cabin_id").agg(F.percentile_approx("fare", 0.5).alias("_m2"))
    stats["fares_imputed"] = tf.where("fare IS NULL").count()
    tf = (tf.join(med_inst, ["flight_instance_id", "cabin_id"], "left")
          .join(F.broadcast(med_cab), "cabin_id", "left")
          .withColumn("fare_imputed", F.col("fare").isNull())
          .withColumn("fare", F.coalesce("fare", "_m1", "_m2").cast("decimal(14,2)"))
          .drop("_m1", "_m2"))
    t["ticket_flights"] = tf.localCheckpoint(eager=True)

    # ticket price = sum of its fares
    sums = tf.groupBy(F.col("ticket_id").alias("id")).agg(
        F.sum("fare").cast("decimal(14,2)").alias("_s"))
    tk = t["tickets"].join(sums, "id", "left")
    stats["ticket_prices_recomputed"] = tk.where(
        F.col("_s").isNotNull() & (F.col("total_price").isNull() | (F.col("total_price") != F.col("_s")))).count()
    t["tickets"] = tk.withColumn("total_price", F.coalesce("_s", "total_price")).drop("_s").localCheckpoint(eager=True)

    # payment = sum of the booking's tickets less its promotion; a payment that
    # is missing or off by more than 1% (e.g. a 10x outlier) is reset to that value
    expected = (t["tickets"].groupBy("booking_id").agg(F.sum("total_price").alias("_tix"))
                .join(t["bookings"].select(F.col("id").alias("booking_id"), "promotion_id"), "booking_id")
                .join(F.broadcast(t["promotions"].select(F.col("id").alias("promotion_id"),
                                                         "discount_percentage")), "promotion_id", "left")
                .select("booking_id", F.round(F.col("_tix") * (100 - F.coalesce("discount_percentage", F.lit(0)))
                                              / 100, 2).cast("decimal(14,2)").alias("_exp")))
    pm = t["payments"].join(expected, "booking_id", "left")
    off = F.col("_exp").isNotNull() & (F.col("amount").isNull()
                                       | (F.abs(F.col("amount") - F.col("_exp")) > F.col("_exp") * 0.01 + 0.01))
    stats["payments_repaired"] = pm.where(off).count()
    t["payments"] = (pm.withColumn("amount_repaired", off)
                     .withColumn("amount", F.when(off, F.col("_exp")).otherwise(F.col("amount")))
                     .drop("_exp").localCheckpoint(eager=True))

    # arrival must be 1-10 h after departure; otherwise the times are unusable
    fi = t["flight_instances"]
    hrs = (F.unix_timestamp("arrival_time") - F.unix_timestamp("departure_time")) / 3600
    bad = ~hrs.between(1, 10) | hrs.isNull()
    stats["flight_times_invalid"] = fi.where(bad).count()
    t["flight_instances"] = fi.withColumn("times_valid", F.coalesce(~bad, F.lit(False))).localCheckpoint(eager=True)

    # refund never more than its payment, never before it
    rf = t["refunds"].join(
        t["payments"].select(F.col("id").alias("payment_id"), F.col("amount").alias("_pa"),
                             F.col("payment_date").alias("_pd")), "payment_id", "left")
    badr = (F.col("amount") > F.col("_pa")) | (F.col("refund_date") <= F.col("_pd"))
    stats["refunds_rule_violations_flagged"] = rf.where(badr).count()
    t["refunds"] = rf.withColumn("rule_violation", F.coalesce(badr, F.lit(False))).drop("_pa", "_pd").localCheckpoint(eager=True)
    return stats


def clean_all(spark, data_dir, log=print):
    cleaned, report = {}, []
    for table in TABLE_ORDER:
        df, stats = clean_table(spark, data_dir, table, cleaned)
        cleaned[table] = df
        report.append(stats)
        log(f"  {table:<18} raw={stats['rows_raw']:>9,}  clean={stats['rows_clean']:>9,}")
    rule_stats = repair_business_rules(cleaned)
    return cleaned, report, rule_stats
