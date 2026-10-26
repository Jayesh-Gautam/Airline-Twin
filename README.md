# Virtual Airline Digital Twin — Big Data Analytics with PySpark and MongoDB

A batch big-data pipeline over a 5-year, 6-airline operations database
(2.4 million rows in the 18 loaded tables at the 1M size; 2.9M across all 32). **PySpark** ingests and cleans the raw
data, builds a per-departure "digital twin" record, adds estimated operating
costs, and runs 15 analytical jobs. **MongoDB** stores the cleaned data, the
twin records and every result, and answers aggregation queries on them.

```
 CSV files (18 tables)
      │
      ▼
 ┌─────────────── PySpark ───────────────┐
 │ 1. Ingest + clean   (pipeline/clean.py)│  dedupe, typo repair, date parsing,
 │                                        │  outliers, orphan keys, business rules
 │ 2. Enrich           (pipeline/enrich.py)│ flight_ops twin + fuel/crew/fees/
 │                                        │  overhead estimates, maintenance, payroll
 │ 3. Analytics        (pipeline/analytics.py) DataFrame API + Spark SQL + windows
 └────────────────────────────────────────┘
      │  PyMongo bulk inserts (pipeline/mongo_store.py)
      ▼
 ┌─────────────── MongoDB (db: airline_twin) ───────────────┐
 │ 18 cleaned tables · flight_ops · maintenance_events ·      │
 │ payroll · a_* analytics results · data_quality_report ·    │
 │ pipeline_runs                                              │
 └────────────────────────────────────────────────────────────┘
      │
      ▼
 mongo_queries.py — aggregation pipelines ($group, $lookup, $project), index use
```

## 1. Setup (one time)

You need **Python 3.10–3.12**, **Java 17** and **MongoDB Community Server**.

1. Java 17: install Temurin 17 (adoptium.net, or `winget install EclipseAdoptium.Temurin.17.JDK`), then check that `java -version` prints 17. If a terminal was opened before the install, `spark_session.py` also looks in `C:\Program Files\Eclipse Adoptium` for it.
2. MongoDB: install MongoDB Community Server and leave it running as a
   service on `localhost:27017`. MongoDB Compass is useful for screenshots.
3. Python packages (PySpark is pinned to 3.5, the version the code was built and tested on):
   ```
   python -m venv .venv
   .venv\Scripts\activate                 # Windows; on macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   pip install -r requirements-dev.txt    # only for tests, charts and the answer-key report
   ```

**On Windows**, Spark prints a warning about `winutils.exe` / `HADOOP_HOME`.
You can ignore it, because this project never makes Spark write files.
Everything goes to MongoDB through PyMongo, and CSV results are written by
Python.

## 2. Get the data

The source is the [airline sample database](https://databasesample.com/datasets/airline-sample-database),
CC0 public domain: 6 fictional airlines, 40 real airports, 2021–2025.

```
python download_data.py 1k              # smoke test (10 departures, 19K rows)
python download_data.py 1m              # main run (~49 MB download, 124 MB unzipped)
python download_data.py 100k --dirty    # cleaning demo: 306K rows with planted faults
```

No internet at demo time? Run `python make_sample_data.py`. It writes
`data/sample` and `data/sample-dirty` with the same tables and columns.

## 3. Run

```
python run_pipeline.py --data data/1k --db airline_1k   # smoke test, about 1 min
python tests/verify_1k.py --db airline_1k                  # checks the published 1K answers
python run_pipeline.py --data data/1m             # main run, about 3 min 13 s (see timings below)
python mongo_queries.py                           # MongoDB aggregation demo
python run_pipeline.py --data data/100k-dirty --db airline_dirty
python mongo_queries.py --db airline_dirty
python answer_key_report.py                       # planted vs fixed -> output/100k-dirty/cleaning_vs_answer_key.csv
python docs/make_charts.py                        # PNG charts in docs/charts/ (presentation only)
python -m pytest tests -q                         # 8 tests on generated sample data + mongomock (about 5 min)
```

Useful flags:
- `--no-mongo` runs Spark only and writes CSVs.
- `--skip-raw-tables` stores only flight_ops and the results, which is faster.
- `--driver-memory 4g`: use it if you have 16 GB RAM.

Every result is also written to `output/<run>/*.csv`, and the timings and
KPIs go to `output/<run>/run_summary.json`. Re-running is idempotent: each
collection is dropped and rewritten, so nothing is duplicated.

**Measured on the real data** (Windows 11, Ryzen 7 7840HS 8 cores, 15 GB RAM, 4 GB driver):

| Run | Clean | Enrich | Analytics | MongoDB load | Total |
|---|---|---|---|---|---|
| 1M (2.44M rows, 18 tables) | 90.6 s | 21.1 s | 9.7 s | 71.4 s | **192.8 s** |
| 100K dirty (248K rows) | 67.7 s | 19.3 s | 6.6 s | 9.1 s | 102.8 s |

The 1M run needs no more than the default memory settings. Real results, KPIs and charts are in
[docs/RESULTS.md](docs/RESULTS.md); live shell commands for the viva are in
[docs/mongodb_shell_demo.md](docs/mongodb_shell_demo.md).

On the clean data every data-quality counter is 0 (no false positives), and the 1K run reproduces the
dataset page's published answers exactly (`tests/verify_1k.py`).

## 3b. Web dashboard and airline simulation

```
python dashboard/app.py          # then open http://127.0.0.1:5000
```

A Flask app (`dashboard/app.py`) serves one page that reads MongoDB through a small JSON API. It needs only the
pipeline run above and works offline (Chart.js is bundled in `dashboard/static`).

- **Simulation tab:** replays the real 2021–2025 departures against a simulated clock. Play/pause, five speeds
  (1 hour/sec up to 1 month/sec), a date picker and a slider. It shows the day of the week, the date and the
  time, a flight board (scheduled / in the air / landed, with delays), running fare revenue and estimated
  profit, revenue by airline and a moving marker on the cumulative revenue curve.
  Link to a moment directly: `http://127.0.0.1:5000/#2024-05-11T16:00`.
- **Other tabs:** Overview, Routes (filter by airline), Delays, Fleet & cabins, Data quality (clean vs dirty,
  planted vs fixed), MongoDB (the aggregation pipelines behind the numbers, with timings, plus the index proof).
- **Spark's part:** `pipeline/analytics.py` builds `a_sim_daily` (one row per calendar day with running totals
  and a true 7-day moving average via window functions) and `a_sim_daily_airline`; MongoDB serves them with
  indexes on the date. The day's flights come from `flight_ops` through the `departure_time` index.
- The replay is real data; costs and profit are the usual estimates, labelled on screen.
- `python dashboard/app.py --db airline_twin --dirty-db airline_dirty --port 5000` changes the databases or port.

## 3c. Dashboard: airline operations simulator (FastAPI + Next.js)

> A simulation and analytics project, **not a real flight-control system**. The airlines are fictional.

```
.\start.bat                       # starts the API (:8000) and the web app (:3000), opens the browser
```
Manual start: `.venv\Scripts\python -m uvicorn backend.main:app --port 8000` and, in `web/`, `npm install` once, then
`npm run dev`. API docs: http://127.0.0.1:8000/docs. Needs the pipeline run once (it creates `sim_params`).

**How Big Data drives the simulator.** `pipeline/sim_params.py` is a PySpark job (called by `run_pipeline.py`)
that turns the history into simulator parameters, stored in MongoDB `sim_params`:
departures per weekday per airline and route, load-factor mean and spread, passengers, cabin mix, average fare per
cabin, delay probability per route (shrunk toward the origin airport's rate with 20 pseudo-departures), delay-minute
deciles and delay reasons per origin airport, maintenance rates by type, and where each aircraft last landed.
Spark computes great-circle distances from `backend/data/airport_coords.json` (OurAirports, public domain).

**The engine** (`backend/sim/engine.py`) is a discrete-event simulator. Each day it builds a schedule per aircraft
from the airline's real routes, weighted by historical weekday frequencies, respecting aircraft range, a 45-minute
(75 for wide-bodies) turnaround, where the aircraft is, and maintenance windows. Flights go Scheduled → Boarding →
Departed → In Flight → Landed, or Delayed / Cancelled. Delays use the historical odds and minutes (× the scenario
multiplier) and propagate to the aircraft's next leg; a grounded aircraft gets a tail swap, a delay or a
cancellation. Passengers are sampled from the route's load-factor distribution × demand; revenue is booked at
departure, costs accrue during the flight (config.py rates). Delays add holding fuel, crew overtime and passenger
compensation; cancellations lose revenue and keep crew and aircraft costs. Every random draw is a hash of
(seed, flight, purpose): the same seed and scenario give the same result, and tick size never changes the outcome
(13 unit tests in `tests/test_sim.py`). State lives in MongoDB: `simulation_state`, `sim_flights`, `sim_aircraft`,
`sim_maintenance`, `flight_events`, `sim_daily_pnl`. Reset clears only those.

Two things the source data cannot support, handled openly:
- Its block times and fares do not depend on distance (correlation −0.008 for both): a 41 km hop "takes" 5.5 h like
  a 13,000 km flight. The simulator uses physical block times (great-circle distance ÷ cruise speed + taxi) and keeps
  the historical revenue per block-hour per route and cabin, so its economics match the Spark P&L (about +12% margin
  at baseline; roughly one airline-day in five loses money).
- Each fictional network lists mostly one-way routes, so return legs are added ("mirrored", labelled "return").

**Real-life mode** (switch at the top of the Scenario sheet; off by default). When on, conditions change randomly
every day as they do in reality: bad-weather windows at individual airports (snow and fog more often in winter),
occasional ATC strikes that raise delay odds across a country for a day, demand that follows the season with daily
noise and occasional multi-day surges or slumps, a fuel price that random-walks around the slider value, and
unexpected technical faults (AOG) that take an aircraft out for 6–36 h mid-day, forcing tail swaps, delays or
cancellations. Everything is drawn from the seed and the date, so a run is still reproducible; the sliders apply on
top. Over a simulated year this gives about +8% margin (vs +11% with fixed conditions), with a weak winter quarter
and a strong summer. Rates are in config.py (`LIVE_*`, illustrative). The top bar shows today's conditions.

**Pages:** Live Operations (KPIs, live profit, flight table, event feed), Flight Map (simulated positions on
OpenStreetMap with an offline world-outline fallback), Daily P&L (loss days and *why*: causes ranked by money impact
that add up exactly to the day's result; break-even load factor per route), Routes & Fleet (simulated vs
historical), Historical Analytics (the Spark results). An airline selector filters every page.

| Real data | Simulated | Estimated (config.py) |
|---|---|---|
| Airlines, airports, routes, fleet, aircraft start positions | Each day's schedule, aircraft assignment, flight times and positions | Fuel, crew, airport fees, ownership/overhead |
| Load-factor distribution, cabin mix, fares per cabin | Passengers per flight (sampled), delays, cancellations, tail swaps | Delay costs: holding fuel, overtime, compensation |
| Delay odds, minutes and reasons; maintenance rates | Maintenance events (drawn from historical rates) | Maintenance cost; therefore all profit figures |

**Note for this Windows machine:** its Application Control policy blocks native `.node` binaries, so Next.js runs
with webpack and its WASM compiler, and Tailwind with its WASM engine. Tailwind's WASM file scanner cannot read
Windows paths, so `web/tailwind-wasm-sources.cjs` feeds it the class names; on a normal machine nothing changes.

## 4. What is real and what is estimated

| Real (from the source data) | Estimated / synthetic (config.py) |
|---|---|
| Airlines, airports, routes, aircraft and models, capacity | Fuel burn per model (kg/h) + taxi fuel, fuel price |
| Departure/arrival times, delays and reasons | Crew cost per block hour by role, monthly salaries |
| Crew and crew assignments | Airport/landing fee per departure |
| Bookings, tickets, fares by cabin, promotions | Aircraft ownership/overhead per seat-hour |
| Payments, refunds | Maintenance events, costs and downtime (seeded, reproducible) |

All estimate fields end in `_est`, and synthetic rows carry `is_estimate` or
`is_synthetic`. The airlines are fictional, and no figure describes a real
airline. The fares and currency come from the dataset, which doesn't name a
currency.

**Profit formula:** operating profit = fare revenue − (fuel + crew + airport
fee + ownership/overhead) per departure. At airline level, maintenance is
also subtracted. Promotions and refunds are reported separately (the
`a_promotions` and `a_payments_and_refunds` collections), so nothing is
counted twice.

## 5. Data cleaning (Big Data quality stage)

| Fault in raw data | How Spark fixes it |
|---|---|
| Exact duplicate rows (the dirty copy appends them under **new ids**) | window `row_number()` over every column except `id`; lowest id kept |
| Near duplicates (same business key, one value differs) | window `row_number()` per business key (e.g. `ticket_number`) and per id; keep the most complete row |
| Typos, wrong case, stray spaces in categories | `levenshtein()` to the nearest allowed value (distance ≤ 2) |
| Mixed date formats | `coalesce` over 20 `to_timestamp` patterns (including ISO with `Z`, day-first `dd/MM/yyyy`, and `Oct 14, 2021 10:04`) |
| Negative or 10× outliers | per-cabin IQR fence (`percentile_approx`) for fares; business rules for prices and payments |
| Missing fares | median of the same cabin on the same departure |
| Orphaned foreign keys | `left_semi` join to the parent; reference-only keys set to NULL instead of cascading |
| Rule breaks (arrival 1–10 h after departure; ticket = sum of fares; payment = tickets − promotion; refund ≤ payment) | recomputed or flagged |

Counts per table go to `data_quality_report`, and totals go to `pipeline_runs`.
The site publishes how many faults it planted, and `answer_key_report.py` compares them with what the
pipeline fixed (on the 100K dirty copy: all 2,392 in-scope exact duplicates removed, all 1,383 reformatted
dates parsed, 0 unparsed). The answer key covers 32 tables and we load 18, so the report also re-measures each
fault type on our 18 tables; gaps are explained in [docs/RESULTS.md](docs/RESULTS.md).

## 6. MongoDB design

- **flight_ops** (`_id` = flight_instance_id) is the digital-twin document:
  route, airline, aircraft, times, passengers, revenue, load factor, delay,
  crew count and every cost estimate, denormalised into one document.
  Indexes: `departure_time`, `route`, `airline`, `aircraft_id`, `year_month`,
  `is_delayed`, and the compounds `(airline, year_month)` and `(route, year_month)`.
- **Source tables** (flat, `_id` = source id) keep referential links, with
  indexes on every foreign key, so `$lookup` works.
- **maintenance_events**, **payroll**: synthetic.
- **a_\***: one collection per analytics job.
- **data_quality_report**, **pipeline_runs**: lineage and audit of each run.

## 7. Analytics jobs (pipeline/analytics.py)

| Collection | What it shows | Spark technique |
|---|---|---|
| a_kpi_summary | totals: departures, passengers, revenue, cost, delay rate | Spark SQL |
| a_monthly_trend | monthly revenue/cost/profit, cumulative revenue, MoM growth, 3-month moving average | window SUM, LAG, AVG over frame |
| a_route_profitability | route P&L, rank within airline, share of airline revenue | window RANK, SUM over partition |
| a_airline_pnl | airline P&L including maintenance, cost per passenger | Spark SQL CTEs + joins |
| a_delays_by_reason / _airport / _aircraft_model | delay counts, p90 minutes, worst airports | PERCENTILE_APPROX, DENSE_RANK |
| a_aircraft_utilization | block hours, downtime, rank within model | joins + ROW_NUMBER |
| a_fuel_efficiency | kg per seat-hour, fuel cost per passenger by model | aggregation |
| a_cabin_fares | fare distribution and revenue share by cabin | SQL window share |
| a_booking_lead_time | how far ahead people book | CTE + DATEDIFF buckets |
| a_payments_and_refunds, a_promotions | payment mix, refund rate, discounts given | joins |
| a_airport_traffic | departures + arrivals per airport | full outer join + DENSE_RANK |
| a_crew_utilization | duties and block hours by role | 4-way join |

## 8. Demo script (about 5 minutes)

1. Show the dataset page and the raw CSV sizes.
2. `python run_pipeline.py --data data/100k-dirty --db airline_dirty` and walk
   through the data-quality summary as it prints.
3. Show the `python run_pipeline.py --data data/1m` timings (about 3 min 13 s; run it before
   class), and `python answer_key_report.py` for planted vs fixed faults.
4. In Compass: open one `flight_ops` document and explain the twin record,
   then `data_quality_report` and `a_route_profitability`.
5. `python mongo_queries.py`: aggregation results and the index-backed query plan.

## 9. Likely viva questions

- **Why Spark for ~3M rows?** The cleaning needs full-table operations:
  global dedup, window functions per id, joins across 18 tables, and
  quantiles per group. Spark runs these in parallel, out of core, and the
  same code would run unchanged on a cluster for 100× the data.
- **Why MongoDB?** flight_ops is a wide, denormalised document read as a
  whole, which suits a document store. Analytics outputs have different
  shapes per job, and the aggregation framework covers ad-hoc questions.
- **Why not the MongoDB Spark Connector?** It needs a JAR matched exactly to
  the Spark and Scala versions, which is the most common failure on laptops.
  PyMongo bulk inserts, streamed partition by partition with
  `toLocalIterator`, are reliable and show the same flow.
- **Why `localCheckpoint()`?** Cleaning builds very long query plans. The
  checkpoint saves the result and cuts the lineage. Without it Spark ran out
  of memory just printing the plan.
- **Are the costs real?** No. They are documented, illustrative assumptions
  in `config.py`, and every such field is suffixed `_est`.

## 10. Limitations and future work

- Batch only. A real-time version would stream events through Kafka into
  Spark Structured Streaming.
- Cost parameters are illustrative. Real fuel burn depends on distance, load
  and weather, and airport coordinates (for great-circle distance) are not in
  the source.
- Orphaned rows are removed or nulled rather than recovered, and removing a bad departure also removes its tickets.
- The source sells about 100 tickets per departure whatever the aircraft size, so load factor exceeds 100% on
  994 of 10,000 departures (flagged `over_capacity`, not capped). 1,339 departures have no crew rows.
- `OWNERSHIP_OVERHEAD_PER_SEAT_HOUR` (config.py) was calibrated to 9 so the network earns about 3% after
  maintenance (12 gave about -9%). Every cost, profit and margin is an estimate.
- Possible additions: a delay prediction model with Spark MLlib trained on
  the historical delays, feeding the simulator instead of per-route rates.
