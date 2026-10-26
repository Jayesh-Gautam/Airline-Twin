"""Stage 4 - persist Spark DataFrames to MongoDB with PyMongo.

Rows stream from Spark to the driver partition by partition
(toLocalIterator) and are bulk-inserted in batches, so the full dataset is
never held in memory at once. This avoids the MongoDB Spark Connector,
whose JAR/version setup is the most common failure point on student laptops.

Each collection is dropped and rewritten on every run, so re-running the
pipeline is idempotent (no duplicated records).
"""
import datetime as dt
from decimal import Decimal

from pyspark.sql import functions as F
from pyspark.sql.types import DateType, DecimalType, TimestampType

# collection -> list of index specs (field or compound list)
INDEXES = {
    "flight_ops": ["departure_time", "route", "airline", "aircraft_id", "year_month",
                   [("airline", 1), ("year_month", 1)], [("route", 1), ("year_month", 1)],
                   "is_delayed"],
    "flights": ["airline_id", [("departure_airport_id", 1), ("arrival_airport_id", 1)]],
    "flight_instances": ["flight_id", "aircraft_id", "departure_time"],
    "ticket_flights": ["ticket_id", "flight_instance_id"],
    "tickets": ["booking_id", "passenger_id"],
    "payments": ["booking_id"],
    "refunds": ["payment_id"],
    "flight_crews": ["crew_id", "flight_instance_id"],
    "flight_delays": ["flight_instance_id"],
    "maintenance_events": ["aircraft_id", "event_date"],
    "a_sim_daily": ["date"],
    "sim_params": ["kind", [("kind", 1), ("airline_id", 1)]],
    "a_sim_daily_airline": ["date", [("date", 1), ("airline", 1)]],
    "aircrafts": ["airline_id"],
}


_MOCK = None


def get_db(uri, db_name):
    global _MOCK
    if uri.startswith("mongomock"):
        import mongomock  # test mode only (in-memory, same process)
        _MOCK = _MOCK or mongomock.MongoClient()
        client = _MOCK
    else:
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")  # fail fast with a clear error
    return client[db_name]


def _prepare(df):
    """Make every column BSON-friendly. Timestamps go out as strings and are
    parsed in Python, so no timezone shift happens on the way to MongoDB."""
    cols, ts_cols, date_cols = [], [], []
    for f in df.schema.fields:
        if isinstance(f.dataType, TimestampType):
            cols.append(F.date_format(f.name, "yyyy-MM-dd HH:mm:ss").alias(f.name)); ts_cols.append(f.name)
        elif isinstance(f.dataType, DateType):
            cols.append(F.date_format(f.name, "yyyy-MM-dd").alias(f.name)); date_cols.append(f.name)
        elif isinstance(f.dataType, DecimalType):
            cols.append(F.col(f.name).cast("double").alias(f.name))
        else:
            cols.append(F.col(f.name))
    return df.select(*cols), ts_cols, date_cols


def _to_doc(row, ts_cols, date_cols, id_col):
    d = row.asDict(recursive=True)
    for c in ts_cols:
        if d[c] is not None:
            d[c] = dt.datetime.strptime(d[c], "%Y-%m-%d %H:%M:%S")
    for c in date_cols:
        if d[c] is not None:
            d[c] = dt.datetime.strptime(d[c], "%Y-%m-%d")
    for k, v in d.items():
        if isinstance(v, Decimal):
            d[k] = float(v)
    if id_col and d.get(id_col) is not None:
        d["_id"] = d.pop(id_col) if id_col == "id" else d[id_col]
    return d


def write_df(db, name, df, id_col="id", batch=10_000):
    coll = db[name]
    coll.drop()
    prepared, ts_cols, date_cols = _prepare(df)
    if id_col and id_col not in prepared.columns:
        id_col = None
    buf, n = [], 0
    for row in prepared.toLocalIterator():
        buf.append(_to_doc(row, ts_cols, date_cols, id_col))
        if len(buf) >= batch:
            coll.insert_many(buf, ordered=False); n += len(buf); buf = []
    if buf:
        coll.insert_many(buf, ordered=False); n += len(buf)
    for spec in INDEXES.get(name, []):
        coll.create_index(spec)
    return n


def write_docs(db, name, docs):
    coll = db[name]
    coll.drop()
    if docs:
        coll.insert_many([dict(d) for d in docs])
    for spec in INDEXES.get(name, []):
        coll.create_index(spec)
    return len(docs)
