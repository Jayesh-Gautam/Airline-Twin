# MongoDB shell demo (viva)

Open a shell with `mongosh` and type these in order. They all run against the database written by the 1M run.

> **Verified in `mongosh`** against this machine's `airline_twin` database (MongoDB server 9.0.2). Fields
> ending in `_est` are estimates, and `is_estimate: true` marks the document as such.

```js
use airline_twin
```

## 1. How many collections, and how big?

```js
db.getCollectionNames().length
db.flight_ops.countDocuments({})
db.ticket_flights.countDocuments({})
```
Expected: `40` collections (18 cleaned tables, `flight_ops`, `maintenance_events`, `payroll`, 17 `a_*` analytics
collections including the two simulation tables `a_sim_daily` and `a_sim_daily_airline`, `data_quality_report`, `pipeline_runs`), `10000` departures, `1000000` ticket segments.

## 2. One digital-twin document

```js
db.flight_ops.findOne({ route: "JFK-LAX", year_month: "2024-05" })
```
Expected (shortened): one departure with everything denormalised: route, airline, aircraft, times, real passengers
and revenue, and the cost estimates.
```js
{ _id: 4773, flight_number: '0971', airline: 'Pacific Lantern', route: 'JFK-LAX',
  model_number: 'A350-900', capacity: 315, passengers: 105, load_factor: 0.3333,
  departure_time: ISODate('2024-05-11T08:30:03.000Z'), block_hours: 6.11, delay_minutes: 0, is_delayed: false,
  fare_revenue: 29239.6,                                  // real
  fuel_cost_est: 28510.4, crew_cost_est: 580.45, airport_fee_est: 1087.5,
  ownership_overhead_est: 17321.85, operating_cost_est: 47500.2,
  operating_profit_est: -18260.6, is_estimate: true }     // estimates
```

## 3. Aggregation: airline profit in 2025

```js
db.flight_ops.aggregate([
  { $match: { year_month: /^2025/ } },
  { $group: { _id: "$airline", departures: { $sum: 1 }, revenue: { $sum: "$fare_revenue" },
              profit_est: { $sum: "$operating_profit_est" } } },
  { $sort: { profit_est: -1 } }
])
```
Expected:
```
Atlantic Crown       395 departures  revenue 12,687,244.2  profit_est 3,000,098.61
Pacific Lantern      631             21,016,150.6          2,365,256.33
Northwind Air        295             9,074,522.8           1,866,465.29
Bosphorus Wings      466             14,229,453.8          1,230,559.48
Blue Harbor Airlines 480             15,298,361.6          708,283.85
Rhine Sky            501             15,371,114.2          171,940.18
```
(These are flight-level profits before maintenance, which is why they differ from the airline P&L collection.)

## 4. Aggregation with `$lookup`: revenue per cabin

```js
db.ticket_flights.aggregate([
  { $group: { _id: "$cabin_id", revenue: { $sum: "$fare" } } },
  { $lookup: { from: "cabins", localField: "_id", foreignField: "_id", as: "c" } },
  { $unwind: "$c" },
  { $project: { _id: 0, cabin: "$c.name", revenue: 1 } },
  { $sort: { revenue: -1 } }
])
```
Expected: Economy 124,272,659 · Business 90,286,567.8 · First 58,553,968 · Premium Economy 43,261,708.8
(1,000,000 documents grouped in a few seconds).

## 5. Pre-computed Spark result stored in MongoDB

```js
db.a_delays_by_reason.find({}, { _id: 0 })
```
Expected: Weather 302 delays (30.2%), Air traffic control 237, Late inbound aircraft 237, Technical 128, Crew 96,
each with `avg_minutes` (about 110) and `p90_minutes` (about 250).

## 6. Index use with `explain()`

```js
db.flight_ops.find({ route: "JFK-LAX", year_month: "2024-05" }).explain("executionStats")
```
Expected (key lines):
```js
winningPlan: { stage: 'FETCH',
  inputStage: { stage: 'IXSCAN', indexName: 'route_1_year_month_1',
                indexBounds: { route: [ '["JFK-LAX", "JFK-LAX"]' ], year_month: [ '["2024-05", "2024-05"]' ] } } }
executionStats: { nReturned: 10, totalKeysExamined: 10, totalDocsExamined: 10 }
```
Now the contrast, a field with no index:
```js
db.flight_ops.find({ fuel_cost_est: { $gt: 1 } }).explain("executionStats").executionStats
```
Expected: `COLLSCAN` with `totalDocsExamined: 10000`. The indexed query reads 10 documents, the unindexed one
reads all 10,000.

## 7. List the indexes

```js
db.flight_ops.getIndexes().map(i => i.name)
```
Expected: `_id_`, `departure_time_1`, `route_1`, `airline_1`, `aircraft_id_1`, `year_month_1`,
`airline_1_year_month_1`, `route_1_year_month_1`, `is_delayed_1`.

## 8. Pipeline audit trail (lineage)

```js
db.pipeline_runs.findOne({}, { _id: 0, run: 1, timings_s: 1 })
db.getSiblingDB("airline_dirty").data_quality_report.find(
  { table: { $in: ["bookings", "tickets"] } }, { _id: 0, table: 1, rows_raw: 1, rows_clean: 1, exact_duplicates: 1 })
```
Expected: run `1m` with timings `ingest_and_clean: 90.6, enrich: 21.1, analytics: 9.7, mongodb_store: 71.4`; then
for the dirty copy bookings 35,707 → 35,094 rows and tickets 71,319 → 69,984 rows (the duplicate and orphan rows
that were removed). Run the dirty pipeline first (`python run_pipeline.py --data data/100k-dirty --db airline_dirty`)
for the second command.
