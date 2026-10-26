# Results from the 1M run

Everything below comes from `output/1m/*.csv` and the MongoDB database `airline_twin`, produced by
`python run_pipeline.py --data data/1m`.

**Real vs estimated.** Passengers, fares, routes, times, delays and reasons are **real** (from the source
dataset; the airlines themselves are fictional). Anything marked **(est.)** (fuel, crew cost, airport fees,
overhead, maintenance, and therefore every cost, profit and margin) is an **illustrative estimate** from
`config.py` and says nothing about a real airline. Currency is whatever the dataset uses (it names none).

## 1. Dataset and machine

| | |
|---|---|
| Source | databasesample.com airline sample database (CC0), "1M" size: 32 CSV files, 124 MB unzipped |
| Loaded by the pipeline | 18 of the 32 tables, **2,436,874 rows** (the dataset page's "2.9M" counts all 32 tables) |
| Big tables | ticket_flights 1,000,000 · tickets 700,000 · bookings 350,000 · payments 350,000 · flight_crews 20,000 · flight_instances 10,000 |
| Span | 2021-01-01 to 2025-12-31, 6 airlines, 40 airports, 239 routes, 60 aircraft, 8 aircraft models |
| Machine | Windows 11, AMD Ryzen 7 7840HS (8 cores / 16 threads), 15 GB RAM |
| Software | Python 3.12, PySpark 3.5.9 (local mode, 4 GB driver), Java 17 (Temurin), MongoDB 9.0.2 |

## 2. Run timings (1M run, clean state)

| Stage | Seconds |
|---|---|
| 1. Ingest + clean (Spark, 18 tables) | 90.6 |
| 2. Enrich (flight_ops twin, maintenance, payroll) | 21.1 |
| 3. Analytics (17 jobs incl. 2 simulation tables, Spark SQL + DataFrame) | 9.7 |
| 4. Load into MongoDB (2.4M docs, PyMongo bulk insert) | 71.4 |
| **Total** | **192.8 (about 3 min 13 s)** |

For comparison, the 100K dirty copy (248K rows) takes 102.8 s in total: 67.7 clean, 19.3 enrich, 6.6 analytics,
9.1 MongoDB. Small runs are dominated by Spark's fixed start-up and planning cost.

## 3. Data quality

**On the clean 1M data every counter is zero**: 0 duplicates, 0 typos repaired, 0 outliers, 0 orphans,
0 unparsed dates, 0 payments or ticket prices recomputed. 2,436,874 rows in, 2,436,874 out. This confirms
the cleaning rules produce no false positives on good data.

**On the 100K dirty copy** (faults planted by the dataset authors), 248,267 rows in, 239,382 out:

| Fault type | Planted (all 32 tables) | Present in our 18 tables (measured on raw CSV) | Pipeline detected / fixed |
|---|---|---|---|
| Exact duplicate rows | 2,977 | 2,392 | **2,392** (all) |
| Reformatted dates | 1,923 | 1,383 | **1,383** parsed, 0 unparsed |
| Near duplicates | 1,843 | n/a | 991 |
| Outliers | 1,214 | n/a | 707 set to NULL |
| Typos / case / spaces | 7,377 | 1,548 | 655 |
| Missing values | 19,802 | 15,105 | 3,201 fares restored, plus 6,005 payments and 7,242 ticket prices recomputed |
| Orphaned keys | 3,643 | 2,177 | 5,502 rows removed, 178 keys nulled |

Reading the gaps honestly:
- The planted counts cover **32 tables**. We load 18, so seats, baggage, meals, users, boarding_passes, gates and
  frequent-flyer faults are out of scope. The third column re-measures what is actually in our tables.
- **Duplicates**: the dirty copy appends duplicates under *new ids*, so they are found by comparing every column
  except the id (exact) and by a business key such as `ticket_number` (near). Near duplicates are found only
  when the key columns are intact, hence 991 rather than 1,843.
- **Typos**: we repair only the categorical columns we validate (status, role, reason, payment method).
  Misspelled names and codes in free-text columns are left alone.
- **Missing values**: most blanks are in columns that cannot be reconstructed (names, license numbers, optional
  links). Fares are re-estimated from the cabin median; prices and payments are recomputed from related rows.
- **Orphans**: removing a bad departure also removes its tickets, so removed rows exceed the number of bad keys.
- The full table with notes is `output/100k-dirty/cleaning_vs_answer_key.csv`.

## 4. KPIs (1M run)

| KPI | Value | Real or est. |
|---|---|---|
| Departures | 10,000 on 239 routes | real |
| Passenger segments (tickets × flights) | 1,000,000 | real |
| Fare revenue | 316,374,903.60 | real |
| Operating cost | 282,184,540.07 | est. |
| Operating profit before maintenance | 34,190,363.53 (10.8%) | est. |
| Maintenance cost | 24,598,622.90 | est. (synthetic events) |
| **Operating profit after maintenance** | **9,591,740.62 (3.0% margin)** | est. |
| Delayed departures (15+ min) | 1,000 (10.0%) | real |
| Average load factor | 0.534 | real |
| Fuel burned | 193,888 tonnes | est. |

Airline P&L (est., after maintenance): Atlantic Crown +16.1%, Northwind Air +8.4%, Pacific Lantern +4.8%,
Blue Harbor Airlines −0.7%, Bosphorus Wings −1.0%, Rhine Sky −5.7%.

Yearly fare revenue (real): 2021 38.8M, 2022 51.8M, 2023 63.3M, 2024 74.7M, 2025 87.7M.

## 5. Routes (profit figures are estimates; revenue is real)

Top 5 by estimated operating profit, before maintenance (airline-route level):

| Route | Airline | Departures | Revenue | Profit (est.) | Margin (est.) |
|---|---|---|---|---|---|
| JFK-SFO | Atlantic Crown | 82 | 2,595,375 | 534,822 | 20.6% |
| JFK-LAX | Pacific Lantern | 142 | 4,747,866 | 533,382 | 11.2% |
| FCO-MCO | Atlantic Crown | 47 | 1,574,217 | 408,435 | 26.0% |
| BCN-JFK | Pacific Lantern | 41 | 1,331,068 | 394,859 | 29.7% |
| SEA-MXP | Atlantic Crown | 34 | 1,115,759 | 375,168 | 33.6% |

Bottom 5:

| Route | Airline | Departures | Revenue | Profit (est.) | Margin (est.) |
|---|---|---|---|---|---|
| LHR-ATL | Rhine Sky | 34 | 1,021,857 | −259,876 | −25.4% |
| ATL-BCN | Rhine Sky | 34 | 1,054,703 | −223,688 | −21.2% |
| BCN-BOS | Rhine Sky | 40 | 1,253,070 | −177,968 | −14.2% |
| SFO-ADB | Blue Harbor Airlines | 42 | 1,325,107 | −168,569 | −12.7% |
| YVR-DEN | Blue Harbor Airlines | 35 | 1,079,545 | −162,078 | −15.0% |

All 286 route margins fall between −41% and +34%. JFK is the busiest airport (3,091 departures + arrivals).

## 6. Delays (real data)

| Reason | Delays | Share | Avg minutes | 90th percentile |
|---|---|---|---|---|
| Weather | 302 | 30.2% | 114.8 | 247 |
| Air traffic control | 237 | 23.7% | 112.1 | 254 |
| Late inbound aircraft | 237 | 23.7% | 109.0 | 245 |
| Technical | 128 | 12.8% | 107.7 | 254 |
| Crew | 96 | 9.6% | 113.1 | 246 |

By airline the delay rate is 9% to 11%, so no airline stands out. Worst origin airport: MUC (16.4% of 177
departures), then KIX (15.3% of 98). Delays are long when they happen (about 110 minutes on average). By
aircraft model the rate runs from 8.6% (A350-900) to 11.7% (E175).

## 7. Fuel efficiency by aircraft model (all fuel figures are estimates)

Fuel burn per hour is an assumption in `config.py`, so this table shows what those assumptions imply.

| Model | Seats | Departures | kg per seat-hour (est.) | Fuel cost per passenger (est.) | Avg load factor |
|---|---|---|---|---|---|
| A321neo | 220 | 1,990 | 11.1 | 107.63 | 0.45 |
| A320neo | 180 | 1,551 | 11.9 | 92.62 | 0.56 |
| A220-300 | 141 | 551 | 12.3 | 77.31 | 0.71 |
| 737-800 | 189 | 1,394 | 13.4 | 112.19 | 0.53 |
| A350-900 | 315 | 1,039 | 18.5 | 250.66 | 0.32 |
| 777-300ER | 396 | 526 | 19.0 | 327.67 | 0.25 |
| 787-9 | 296 | 1,943 | 19.0 | 251.75 | 0.34 |
| E175 | 76 | 1,006 | 21.5 | 71.48 | 1.31 |

## 8. Cabin revenue share (real fares)

| Cabin | Segments | Avg fare | Revenue | Share of revenue |
|---|---|---|---|---|
| Economy | 755,387 (75.5%) | 164.52 | 124,272,659 | 39.3% |
| Business | 98,459 (9.8%) | 917.00 | 90,286,568 | 28.5% |
| First | 31,187 (3.1%) | 1,877.51 | 58,553,968 | 18.5% |
| Premium Economy | 114,967 (11.5%) | 376.30 | 43,261,709 | 13.7% |

## 9. Insights in plain English

1. **Growth came from more flights, not higher fares.** Fare revenue rose from 38.8M in 2021 to 87.7M in 2025
   (about 2.3×). Departures rose from 1,234 to 2,768 (2.2×), while revenue per departure stayed near 31.5K.
2. **Premium cabins carry the revenue.** Economy is 75% of the seats but 39% of the money. First class, with just
   3% of the seats, brings in 18.5% of all revenue.
3. **Delays are a steady 10% for everyone.** Weather is the largest single cause (30%), but no airline is clearly
   worse than another (9–11%), so the delays look like a property of the network rather than one operator.
4. **Under our cost assumptions the big jets are the expensive ones.** Wide-bodies (A350, 777, 787) fly about
   1.6× the fuel per seat-hour of the A320/A321 family and, with load factors of only 25–34%, cost 250–330 in
   fuel per passenger versus 77–112 for the narrow-bodies. This follows from assumed burn rates, so it illustrates
   the method, not a real-world finding.
5. **Margins are thin and uneven (est.).** The network earns about 3% after maintenance, but results range from
   +16% (Atlantic Crown) to −6% (Rhine Sky), and the five worst routes lose 12–25% of their revenue.

## 10. Limitations visible in the data

- **Load factor can exceed 100%.** The source assigns about 100 tickets to every departure regardless of
  aircraft size (62 to 145 per flight), so the 76-seat E175 often carries more passengers than seats (994
  departures, 9.9%, flagged `over_capacity`). Passenger counts are kept as given and flagged rather than
  capped. This also makes per-seat metrics for small aircraft look better than they would in reality, and the
  low wide-body load factors in section 7 partly reflect the same quirk.
- **1,339 departures (13%) have no crew rows** in the source, so crew cost (est.) is understated for them.
- **Overhead calibration.** `OWNERSHIP_OVERHEAD_PER_SEAT_HOUR` was lowered from 12 to 9. At 12 the network lost
  about 9% after maintenance; at 9 it earns about 3%, in line with typical airline margins. This is a tuning
  knob, not a measurement, so every profit and margin figure depends on it.
