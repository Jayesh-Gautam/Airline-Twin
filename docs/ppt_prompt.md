Create a 16-slide presentation for a college Big Data Analytics project presentation and viva. The audience is my professor and classmates. Make it clear, professional and minimal: dark background (near-black #0b0b0c), white text, one blue accent (#38bdf8), green only for profit and red only for loss. Use large numbers, short bullet points (max 5 per slide, max 12 words each), simple diagrams, and add speaker notes (3–5 sentences) to every slide. Use ONLY the facts and numbers below — do not invent any figures. The airlines are fictional; always label cost and profit figures as "estimates".

PROJECT TITLE: "Airline Digital Twin — Big Data Analytics and Operations Simulation with PySpark and MongoDB"
Subtitle: Batch Big Data pipeline + live airline operations simulator (simulation and analytics project, not a real flight-control system)

---------------------------------------------------------------
SLIDE 1 — Title
Title, subtitle, my name / roll number / course (leave placeholders), tech logos row: Python, PySpark, MongoDB, FastAPI, Next.js.

SLIDE 2 — Problem and goal
- Airlines generate millions of booking, ticket and flight records.
- Goal: clean the raw data at scale, analyse it, and turn it into a "digital twin" of the airline.
- Questions answered: Which routes make money? Why are flights delayed? Which days lose money and why?
- Extra: a live simulator driven by parameters learned from the historical data.

SLIDE 3 — Dataset
- Source: Airline Sample Database from databasesample.com, CC0 public domain licence.
- 6 fictional airlines, 40 real airports, 2021–2025, 32 tables.
- "1M" size used: about 2.9 million rows in total; the pipeline loads the 18 core tables = 2,436,874 rows.
- Biggest tables: ticket_flights 1,000,000 · tickets 700,000 · bookings 350,000 · payments 350,000 · flight_crews 20,000 · flight_instances 10,000.
- Also used: the "100K dirty" copy (248,267 rows in our 18 tables) with faults planted by the dataset authors, to prove the cleaning stage.
Visual: a small entity diagram: airlines → flights → flight_instances → ticket_flights ← tickets ← bookings → payments.

SLIDE 4 — Technology stack
Table with 3 columns (Layer · Technology · Why):
- Big Data processing · PySpark 3.5 (Spark SQL, DataFrame API, window functions) · parallel, out-of-core, same code scales to a cluster
- Storage · MongoDB 9 + PyMongo · document model fits the wide "flight digital twin" record; aggregation framework; indexes
- Simulation API · Python FastAPI · discrete-event simulator, live updates with Server-Sent Events
- Dashboard · Next.js 16, TypeScript, Tailwind, shadcn/ui, Recharts, Leaflet maps (OpenStreetMap) · professional interactive web UI
- Quality · pytest (24 automated tests), Playwright screenshot checks
- Map coordinates · OurAirports (public domain)

SLIDE 5 — Architecture (diagram slide)
Draw a left-to-right pipeline diagram:
CSV files (18 tables) → [PySpark: 1 Ingest + clean → 2 Enrich (digital twin) → 3 Analytics (17 jobs) → 3b Simulator parameters] → MongoDB (40 collections) → FastAPI simulator + API → Next.js dashboard (5 pages).
Caption: "Spark is the Big Data engine; MongoDB is the serving store; the web app reads MongoDB."

SLIDE 6 — Big Data step 1: cleaning at scale (most important slide #1)
Title: "How Spark cleans the data"
- Exact duplicates: window ROW_NUMBER over all columns except id (duplicates had new ids).
- Near duplicates: ROW_NUMBER per business key (e.g. ticket_number), keep the most complete row.
- Typos: Spark levenshtein() maps to the nearest allowed value.
- Mixed date formats: coalesce over 20 to_timestamp patterns.
- Outliers: per-cabin IQR fence with percentile_approx; orphan keys: left-semi joins.
Results on the dirty copy (show as a before/after table):
  rows 248,267 → 239,382 · exact duplicates removed 2,392 (100% of those in scope) · near duplicates 991 · typos repaired 655 · outliers 707 · reformatted dates parsed 1,383 (0 left unparsed) · fares restored 3,201 · orphan rows removed 5,502.
On the clean 1M data every fault counter is 0 → no false positives. On the 1K copy the results match the dataset's published answers exactly.

SLIDE 7 — Big Data step 2: the digital twin
- Spark joins 7 tables into one "flight_ops" record per departure (10,000 documents).
- Each record: route, airline, aircraft, times, passengers, fare revenue, delay, crew, load factor.
- Plus estimated costs: fuel, crew, airport fees, ownership/overhead (all fields end in _est).
- localCheckpoint() cuts Spark's lineage so long cleaning plans stay fast.

SLIDE 8 — Big Data step 3: analytics with Spark SQL (most important slide #2)
17 analytics jobs, each stored as a MongoDB collection (a_*). Show techniques:
- Window functions: running totals, month-on-month growth (LAG), 3-month moving average, RANK of routes within each airline.
- PERCENTILE_APPROX for delay p90; DENSE_RANK for worst airports; CTEs and multi-table joins for airline P&L.
- Simulation tables: one row per calendar day with cumulative totals and a true 7-day moving average.
Pipeline run on a laptop (Ryzen 7, 8 cores, 15 GB RAM): about 252 seconds end to end — clean 103.5 s · enrich 16.9 s · analytics 15.4 s · simulator parameters 22.1 s · MongoDB load 93.6 s.

SLIDE 9 — Key findings from 5 years of data
Big-number layout:
- 10,000 departures · 1,000,000 passenger segments · 316.4M fare revenue (real).
- Revenue grew 38.8M (2021) → 87.7M (2025), about 2.3×, driven by more flights, not higher fares.
- Economy = 75.5% of seats but only 39.3% of revenue; First = 3.1% of seats, 18.5% of revenue.
- 10% of departures delayed 15+ minutes; weather is the top cause (30%).
- Estimated operating margin about 3% after maintenance (estimate).

SLIDE 10 — MongoDB design
- 40 collections: 18 cleaned tables, flight_ops (digital twin), 17 analytics results, simulator state and parameters, data-quality report, pipeline-run audit.
- Indexes on every foreign key + compound (route, year_month).
- Proof: route+month query uses IXSCAN and reads 10 documents instead of scanning 10,000 (COLLSCAN).
- Aggregation pipelines with $group, $lookup, $project power the dashboard.

SLIDE 11 — The link: Big Data drives the simulator (most important slide #3)
Title: "From history to simulation"
- A dedicated PySpark job (sim_params.py) learns 333 parameter documents from the history:
  per route (286): weekday departures, load-factor mean and spread, cabin mix, fare per cabin, delay probability;
  per airport (40): delay-minute distribution and delay reasons; per aircraft (60): last known location; network: maintenance rates.
- Delay probabilities are smoothed toward the airport average (statistical shrinkage) so small routes are not noisy.
- Honest data finding: in this synthetic dataset block time and fare do not depend on distance (correlation −0.008), so the simulator uses physical flight times from great-circle distance and keeps the historical revenue per block-hour.
Visual: arrow from "Spark: 2.4M rows" → "sim_params (333 docs)" → "Simulator".

SLIDE 12 — The operations simulator
- Discrete-event engine: every flight goes Scheduled → Boarding → Departed → In Flight → Landed (or Delayed / Cancelled).
- Builds a daily schedule per aircraft from real routes; respects aircraft range, 45-min turnaround, location and maintenance.
- Delays propagate to the next flight of the same aircraft; grounded aircraft trigger tail swaps or cancellations.
- Revenue booked at departure, costs accrue in flight; every event logged in MongoDB.
- Deterministic: same seed = same result (verified by automated tests).
- What-if scenarios: demand, delay probability, fuel price, bad weather, grounded aircraft.
- Real-life mode: random storms, fog and snow, ATC strikes, seasonal demand, fuel price moves and technical faults.

SLIDE 13 — Dashboard tour (screenshot slide, 2×2 grid with captions)
Leave 4 image placeholders and captions:
1. Live Operations — live profit, KPIs, flights table, event feed; period selector Day / Month / 6M / Year / YTD.
2. Flight Map — aircraft moving on great-circle routes, coloured by status; click a plane for details.
3. Daily P&L — profit per day and "Why this day lost money" with causes ranked by money impact.
4. Historical Analytics — the Spark results: monthly trend, delays, fuel efficiency, cabins, data quality.
(Also mention: Routes & Fleet page compares simulated routes with historical ones.)

SLIDE 14 — Example: why a day lost money
Show a horizontal bar chart (red bars) from a real simulation run (Pacific Lantern):
- Baseline day: +$569k profit.
- After applying a what-if scenario (demand 60%, 3× delays, bad weather at JFK and LHR): −$487k.
- Causes: low load factor on 31 flights −$295k · delays on 33 flights −$230k · weather cancellations −$15k.
- The causes add up exactly to the day's result (reconciliation gap 0).
Real-life mode over a simulated year: about +8% margin vs +11% with fixed conditions; winter quarter near break-even, summer strongest.
All profit figures are estimates.

SLIDE 15 — Real vs simulated vs estimated + limitations
Three-column table:
- Real data: routes, fleet, fares, cabin mix, load factors, delays and reasons, passengers.
- Simulated: daily schedule, aircraft assignment, flight positions, delays and cancellations in the simulator.
- Estimated (config.py): fuel, crew, airport fees, overhead, maintenance cost → therefore all profit figures.
Limitations: batch pipeline (no streaming), fictional airlines, synthetic dataset quirks (e.g. about 100 tickets per flight regardless of aircraft size), cost model is illustrative.
Future work: Spark Structured Streaming with Kafka; delay prediction with Spark MLlib.

SLIDE 16 — Conclusion and demo
- Spark cleaned and analysed 2.4M rows in about 4 minutes on a laptop, with no false positives.
- MongoDB serves 40 collections with index-backed queries.
- The simulator turns historical Big Data into a live, explainable airline twin.
- Live demo: start simulation → apply scenario → watch a day turn into a loss → open "Why this day lost money".
"Thank you — Questions?"

---------------------------------------------------------------
Also generate 6 likely viva questions with short answers as a final appendix slide:
1. Why Spark for 2.4M rows? (full-table dedup, window functions per id, 18-table joins, quantiles — parallel and scales unchanged to a cluster)
2. Why MongoDB? (wide denormalised flight record read as a whole; different shapes per analytics job; aggregation framework; indexes)
3. How do you know the cleaning works? (0 false positives on clean data; matches published answers on 1K; planted-vs-detected comparison on the dirty copy)
4. Are the profits real? (no — fares are real, costs are documented estimates in config.py, labelled "est.")
5. How is the simulator connected to Big Data? (sim_params Spark job → 333 parameter documents in MongoDB → engine)
6. Is the simulation reproducible? (yes — every random draw is seeded; same seed and scenario give the same result; tested)
