"""Central configuration and documented modelling assumptions.

Everything in the ASSUMPTIONS block is ILLUSTRATIVE. The source dataset
(databasesample.com airline sample database, CC0) has no fuel, salary,
airport-fee or maintenance-cost data, so these values are used to
synthesize those parts. They are not measurements from any real airline.
"""
import os

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "airline_twin")
DATA_ROOT = os.environ.get("AIRLINE_DATA_DIR", "data")
OUTPUT_ROOT = os.environ.get("AIRLINE_OUTPUT_DIR", "output")
SEED = 42

BASE_URL = ("https://database-sample-website.s3.eu-north-1.amazonaws.com/"
            "datasets/airline-sample-database/v2/flagship")
# size -> {variant: zip name}. The site publishes a dirty copy only for 1k and 100k.
DOWNLOADS = {
    "1k":   {"clean": "csv.zip", "dirty": "dirty-csv.zip"},
    "100k": {"clean": "csv.zip", "dirty": "dirty-csv.zip"},
    "1m":   {"clean": "csv.zip"},
}

# ------------------------------------------------------------------ ASSUMPTIONS
# Cruise fuel burn per block hour, kg/h, by aircraft model (rounded,
# order-of-magnitude public figures; illustrative only).
FUEL_BURN_KG_PER_HR = {
    "737-800": 2500, "A320neo": 2100, "A321neo": 2400, "787-9": 5600,
    "A350-900": 5800, "E175": 1600, "777-300ER": 7500, "A220-300": 1700,
}
DEFAULT_FUEL_BURN_KG_PER_HR = 2500
TAXI_FUEL_KG = 200            # taxi-out + taxi-in allowance per departure
FUEL_PRICE_PER_KG = 0.80      # currency units per kg of jet fuel

# Crew cost per block hour, by role_assigned in flight_crews.
CREW_RATE_PER_HR = {"captain": 160, "first_officer": 95, "purser": 55, "cabin": 40}
# Monthly salary by crew role (crews.role) for the payroll view.
CREW_MONTHLY_SALARY = {"captain": 18000, "first_officer": 11000,
                       "purser": 5500, "flight_attendant": 4200}

# Airport + landing fee per departure = base + per-seat charge * capacity.
AIRPORT_FEE_BASE = 300
AIRPORT_FEE_PER_SEAT = 2.5

# Aircraft ownership/lease, insurance and overhead, per seat per block hour.
# Without this the model would only count direct trip costs and show
# unrealistically high margins.
# Calibrated on the real 1M run: 12 gave an airline-level margin of about -9%
# (after maintenance), 9 gives about +3%, in line with the low single-digit
# margins airlines typically report. It is a tuning knob, not a measurement.
OWNERSHIP_OVERHEAD_PER_SEAT_HOUR = 9

# ------------------------------------------------------------- SIMULATOR (web/ + backend/)
# Everything that the history CAN tell us (routes, fleet, weekday pattern, load
# factors, cabin mix, fares, delay odds/minutes/reasons, maintenance rates) is
# computed by pipeline/sim_params.py with Spark. The constants below cover what
# the source data cannot: aircraft performance, ground times, delay costs.
# All ILLUSTRATIVE.
SIM_START_DATE = "2026-01-05"          # day 1 of the simulation (a Monday)
SIM_SEED = 42
# model -> (cruise speed km/h, practical range km); rounded public figures
MODEL_PERFORMANCE = {
    "737-800": (840, 5400), "A320neo": (840, 6300), "A321neo": (840, 7400), "787-9": (900, 14000),
    "A350-900": (900, 15000), "E175": (780, 3700), "777-300ER": (900, 13600), "A220-300": (820, 6200),
}
DEFAULT_PERFORMANCE = (840, 6000)
ROUTING_FACTOR = 1.05                  # flown distance / great-circle distance
TAXI_BLOCK_H = 0.4                     # taxi-out + taxi-in time added to air time
MIN_BLOCK_H = 0.75
TURNAROUND_MIN = 45                    # narrow-body minimum ground time
WIDEBODY_TURNAROUND_MIN = 75           # aircraft with more than 250 seats
BOARDING_LEAD_MIN = 40                 # boarding starts 40 min before departure
TAXI_OUT_MIN = 15                      # "Departed" (off-block) -> "In flight"
FIRST_DEPARTURE_HOUR = 5               # UTC departure window of the daily schedule
LAST_DEPARTURE_HOUR = 22
DAILY_BLOCK_TARGET_H = 13              # planned block hours per aircraft per day
DELAYED_THRESHOLD_MIN = 15             # same 15-minute rule as the analytics
LOAD_FACTOR_MIN = 0.15
# Fares: the dataset's fares and block times do not vary with distance
# (r = -0.008 for both): on average a ticket earns 316 for a 5.5 h block. The
# simulator keeps that revenue per block-hour - each route's historical fare
# per cabin x (real block time / historical mean block time) ** exponent - so
# its unit economics match the historical P&L computed by Spark.
FARE_BLOCK_EXPONENT = 1.0
# Crew complement: 2 pilots (+2 relief pilots above 9 block hours), 1 purser,
# 1 cabin crew per 50 seats (the usual regulatory minimum)
RELIEF_PILOTS_ABOVE_H = 9
SEATS_PER_CABIN_CREW = 50
# Delay and disruption costs
HOLDING_SHARE_OF_DELAY = 0.25          # share of a delay spent airborne in a hold
HOLDING_BURN_FACTOR = 0.6              # holding burn as a share of cruise burn
CREW_OVERTIME_MULTIPLIER = 1.5         # crew pay for delay time beyond the schedule
DELAY_COMPENSATION_AFTER_MIN = 180     # passenger compensation for 3h+ delays
DELAY_COMPENSATION_PER_PAX = 300
CANCEL_COMPENSATION_PER_PAX = 250
COMPENSATION_CLAIM_RATE = 0.4          # share of eligible passengers who actually claim
CANCEL_AFTER_DELAY_MIN = 360           # a flight delayed beyond 6 h is cancelled
MAX_WAIT_FOR_AIRCRAFT_MIN = 180        # otherwise a flight without an aircraft is cancelled
# "Bad weather day" scenario at chosen airports
WEATHER_DELAY_MULTIPLIER = 3.0
WEATHER_MINUTES_MULTIPLIER = 1.5
WEATHER_CANCEL_PROBABILITY = 0.12

# "Real-life mode" (Scenario sheet): conditions change randomly every day, the
# way they do in reality. Probabilities and sizes are ILLUSTRATIVE assumptions.
LIVE_FUEL_DAILY_VOL = 0.025            # daily random walk of the fuel price index (sd)
LIVE_FUEL_REVERSION = 0.08             # pull back toward the baseline price each day
LIVE_FUEL_RANGE = (0.7, 1.5)           # fuel index limits (x the scenario fuel price)
LIVE_DEMAND_NOISE = 0.07               # day-to-day demand noise (log sd)
# monthly demand seasonality (summer and Christmas peaks, February low)
LIVE_DEMAND_SEASON = {1: 0.93, 2: 0.9, 3: 0.97, 4: 1.0, 5: 1.02, 6: 1.08, 7: 1.12, 8: 1.1,
                      9: 1.0, 10: 0.98, 11: 0.94, 12: 1.04}
LIVE_SHOCK_PROB = 0.025                # chance per day that a demand surge or slump starts
LIVE_DELAY_NOISE = 0.18                # day-to-day variation of delay odds (log sd)
LIVE_WEATHER_PROB = 0.03               # chance per airport per day of a bad-weather window
LIVE_WINTER_FACTOR = 2.0               # Dec-Feb, airports beyond 35 degrees latitude
LIVE_ATC_PROB = 0.012                  # chance per country per day of an ATC strike
LIVE_ATC_DELAY_FACTOR = 2.5            # delay odds multiplier during a strike
LIVE_AOG_PROB = 0.003                  # chance per aircraft per day of a technical fault (AOG)
LIVE_AOG_HOURS = (6, 36)               # out of service for this many hours
LIVE_AOG_COST = (15_000, 80_000)       # unscheduled repair cost

# Maintenance event generator: type -> (monthly probability per aircraft,
# base cost, extra cost per seat, downtime hours).
MAINTENANCE_TYPES = {
    "Line check": (0.30, 2_000, 5, 6),
    "A-check":    (0.08, 15_000, 40, 24),
    "C-check":    (0.01, 250_000, 600, 240),
}
