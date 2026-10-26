"""Simulation engine tests on a small fixture network (no Spark, no MongoDB)."""
import copy
from datetime import timedelta

import pytest

import config as C
from backend.sim import analysis, params as P
from backend.sim.engine import DONE, Engine

COORDS = {k: {"iata": k, "name": k, "lat": la, "lon": lo} for k, la, lo in [
    ("JFK", 40.6398, -73.7789), ("LAX", 33.9425, -118.408), ("ORD", 41.9786, -87.9048),
    ("BOS", 42.3643, -71.0052), ("MIA", 25.7932, -80.2906)]}
QS = [15, 25, 40, 55, 75, 100, 125, 160, 200, 250, 300]
REASONS = {"Weather": 0.3, "Air traffic control": 0.25, "Late inbound aircraft": 0.2, "Technical": 0.15, "Crew": 0.1}
SHARE = {"First": 0.03, "Business": 0.1, "Premium Economy": 0.12, "Economy": 0.75}
FARES = {"First": 1880, "Business": 917, "Premium Economy": 376, "Economy": 165}


def route(o, d, n=40, num="0100"):
    return {"_id": f"route:1:{o}-{d}", "kind": "route", "airline_id": 1, "airline": "Test Air", "origin": o,
            "destination": d, "route": f"{o}-{d}", "flight_numbers": [num], "departures": n,
            "departures_by_weekday": [n // 7] * 7, "lf_mean": 0.62, "lf_sd": 0.15, "cabin_share": SHARE,
            "fare_by_cabin": FARES, "delay_prob": 0.1, "hist_block_mean": 5.5}


def make_params():
    glob = {"_id": "global", "kind": "global", "delay_prob": 0.1, "delay_minutes_q": QS, "delay_reasons": REASONS,
            "hist_block_mean": 5.49, "mean_km": 3000.0, "lf_mean": 0.6, "lf_sd": 0.15, "cabin_share": SHARE,
            "fare_by_cabin": FARES, "maintenance": {"Line check": {"per_aircraft_month": 0.6, "downtime_hours": 6},
                                                    "A-check": {"per_aircraft_month": 0.3, "downtime_hours": 24}}}
    airline = {"_id": "airline:1", "kind": "airline", "airline_id": 1, "airline": "Test Air", "hub": "JFK",
               "departures_by_weekday": [10] * 7, "weekday_factor": [1.0] * 7}
    routes = [route("JFK", "LAX", 80, "0100"), route("JFK", "ORD", 60, "0200"), route("ORD", "BOS", 40, "0300"),
              route("BOS", "JFK", 50, "0400"), route("JFK", "MIA", 60, "0500")]
    aps = [{"_id": f"airport:{k}", "kind": "airport", "iata": k, "delay_prob": 0.1, "delay_minutes_q": QS,
            "delay_reasons": REASONS} for k in COORDS]
    ac = [{"_id": f"aircraft:{i}", "kind": "aircraft", "aircraft_id": i, "airline_id": 1, "registration": f"N{i}00TA",
           "model": m, "capacity": c, "status": s, "location": loc}
          for i, (m, c, s, loc) in enumerate([("A320neo", 180, "in_service", "JFK"), ("737-800", 189, "in_service", "JFK"),
                                              ("A321neo", 220, "in_service", "ORD"), ("E175", 76, "maintenance", "BOS")], 1)]
    return P.from_docs([glob, airline, *routes, *aps, *ac], [{"_id": 1, "name": "Test Air", "iata_code": "TA"}],
                       copy.deepcopy(COORDS))


def run(days=4, seed=7, steps=None, scenario=None):
    e = Engine(make_params(), seed=seed, start_date="2026-01-05")
    if scenario:
        e.set_scenario(scenario)
    end = e.start + timedelta(days=days)
    if steps:
        t = e.start
        while t < end:
            t = min(end, t + steps)
            e.advance_to(t)
    else:
        e.advance_to(end)
    return e


def flown_legs(e, ac_id):
    return sorted((e.flights[i] for i in e.legs[ac_id]
                   if e.flights[i]["status"] != "Cancelled" and e.flights[i]["delay_checked"]), key=lambda f: f["etd"])


def snapshot(e):
    return {k: {x: v for x, v in f.items()} for k, f in sorted(e.flights.items())}


# ------------------------------------------------------------------ schedule integrity
def test_schedule_is_generated_from_real_routes():
    e = run(2)
    assert e.flights, "no flights generated"
    routes = {(r["origin"], r["destination"]) for r in e.p.routes[1]}
    assert all((f["origin"], f["destination"]) in routes for f in e.flights.values() if not f["is_ferry"])
    assert any(r.get("mirrored") for r in e.p.routes[1]), "return legs should be added"


@pytest.mark.parametrize("scenario", [None, {"delay_multiplier": 3.0}])
def test_no_aircraft_overlap_and_location_continuity(scenario):
    e = run(5, scenario=scenario)
    for ac_id in e.aircraft:
        legs = flown_legs(e, ac_id)
        for a, b in zip(legs, legs[1:]):
            assert b["origin"] == a["destination"], f"{b['_id']} departs from where {a['_id']} did not land"
            assert b["etd"] >= a["eta"] + e.turnaround(a["capacity"]), f"{b['_id']} overlaps {a['_id']}"
            assert (b["etd"] - a["eta"]) >= timedelta(minutes=C.TURNAROUND_MIN)


def test_maintenance_windows_are_respected():
    e = run(10)
    assert e.maint, "fixture should produce maintenance events"
    for m in e.maint:
        for f in flown_legs(e, m["aircraft_id"]):
            if f["status"] in ("Departed", "In Flight", "Landed"):
                assert not (f["etd"] < m["end"] and f["eta"] > m["start"]), f"{f['_id']} flew during {m['_id']}"
    listed = next(a for a in e.aircraft.values() if a["source_status"] == "maintenance")
    first = flown_legs(e, listed["_id"])
    assert not first or first[0]["etd"] >= e.start + timedelta(hours=24)


def test_state_transitions_are_valid():
    e = run(4, scenario={"delay_multiplier": 2.0})
    allowed = {None: {"Scheduled"}, "Scheduled": {"Boarding", "Delayed", "Cancelled"},
               "Delayed": {"Boarding", "Cancelled"}, "Boarding": {"Departed", "Cancelled"},
               "Departed": {"In Flight", "Landed"}, "In Flight": {"Landed"}, "Landed": set(), "Cancelled": set()}
    seen = {}
    for ev in e.recent:
        if ev["kind"] in ("status", "delay", "cancel") and ev["flight_id"]:
            prev = seen.get(ev["flight_id"], "Scheduled")
            assert ev["status"] in allowed[prev] | ({prev} if prev == "Scheduled" else set()), \
                f"{ev['flight_id']}: {prev} -> {ev['status']}"
            seen[ev["flight_id"]] = ev["status"]
    landed = [f for f in e.flights.values() if f["status"] == "Landed"]
    assert landed and all(f["atd"] and f["ata"] and f["ata"] > f["atd"] for f in landed)


# ------------------------------------------------------------------ money
def test_pnl_sums_and_no_double_counting():
    e = run(4, scenario={"delay_multiplier": 2.5})
    for day in e.days_generated:
        t = e.day_totals(day, 1)
        rev = cost = 0.0
        for i in e.by_day[day]:
            r, c = e.money_at(e.flights[i], e.clock)
            rev += r
            cost += sum(c.values())
        cost += sum(m["cost"] for m in e.maint if m["day"] == day and m["start"] <= e.clock)
        assert t["revenue"] == pytest.approx(rev, abs=0.05)
        assert t["cost_total"] == pytest.approx(cost, abs=0.05)
        assert t["profit"] == pytest.approx(t["revenue"] - t["cost_total"], abs=0.05)
        assert sum(t["cost"].values()) == pytest.approx(t["cost_total"], abs=0.05)
        assert e.day_totals(day)["profit"] == pytest.approx(t["profit"], abs=0.05)   # single airline = network
        why = analysis.explain_day(e, 1, day)
        assert why["reconciliation_gap"] == pytest.approx(0, abs=0.5)
    for f in e.flights.values():
        if f["status"] == "Cancelled":
            assert f["revenue"] == 0 and f["cost"]["fuel"] == 0      # revenue lost is a memo, not booked
        if f["status"] == "Landed" and not f["is_ferry"]:
            assert f["revenue"] > 0 and f["cost"]["fuel"] > 0


def test_fuel_cost_follows_config_formula():
    e = run(2)
    f = next(f for f in e.flights.values() if f["status"] == "Landed")
    burn = C.FUEL_BURN_KG_PER_HR[f["model"]]
    assert f["cost"]["fuel"] == pytest.approx((burn * f["block_h"] + C.TAXI_FUEL_KG) * f["fuel_price"], abs=0.02)


def test_demand_scenario_reduces_passengers():
    base, low = run(3), run(3, scenario={"demand": 0.5})
    pax = lambda e: sum(f["pax"] for f in e.flights.values() if f["status"] == "Landed")  # noqa: E731
    assert pax(low) < 0.7 * pax(base)


# ------------------------------------------------------------------ determinism
def test_same_seed_same_result_and_tick_size_does_not_matter():
    a, b = run(4, seed=11), run(4, seed=11, steps=timedelta(minutes=7))
    assert snapshot(a) == snapshot(b)
    assert [x["text"] for x in a.recent] == [x["text"] for x in b.recent]
    c = run(4, seed=12)
    assert snapshot(a) != snapshot(c)


def test_restore_from_mongodb_continues_identically():
    mongomock = pytest.importorskip("mongomock")
    from backend.sim import store
    db = mongomock.MongoClient().simtest
    store.reset(db)
    params = make_params()
    a = Engine(params, seed=5, start_date="2026-01-05")
    a.advance_to(a.start + timedelta(days=1, hours=13, minutes=17))
    store.flush(db, a, False, 900)
    b = store.load(db, make_params())
    end = a.start + timedelta(days=3)
    a.advance_to(end)
    b.advance_to(end)
    sa, sb = snapshot(a), snapshot(b)
    assert sa.keys() == sb.keys()
    for k in sa:
        for field in ("status", "etd", "eta", "pax", "revenue", "cost", "delay_minutes", "aircraft_id"):
            assert sa[k][field] == sb[k][field], (k, field)


# ------------------------------------------------------------------ disruption
def test_delays_propagate_to_the_next_leg():
    e = run(5, scenario={"delay_multiplier": 3.0})
    late = [f for f in e.flights.values() if f.get("delay_propagated") and f["status"] != "Cancelled"]
    assert late, "no propagated delays at 3x delay probability"
    for f in late:
        prev = flown_legs(e, f["aircraft_id"])
        prev = [p for p in prev if p["etd"] < f["etd"]][-1]
        ready = prev["eta"] + e.turnaround(prev["capacity"])
        assert ready <= f["etd"] < ready + timedelta(minutes=1)
        assert f["delay_reason"] in ("Late inbound aircraft", "Aircraft unavailable (maintenance)")


def test_grounded_aircraft_does_not_fly():
    e = Engine(make_params(), seed=3, start_date="2026-01-05")
    e.advance_to(e.start + timedelta(hours=12))
    e.set_scenario({"grounded_aircraft": [1]})
    t0 = e.clock
    e.advance_to(e.start + timedelta(days=3))
    assert not [f for f in e.flights.values() if f["aircraft_id"] == 1 and f["atd"] and f["atd"] >= t0]
    assert any(ev["kind"] == "scenario" for ev in e.recent)


# ------------------------------------------------------------------ real-life mode
def run_real_life(days, seed=21, steps=None):
    e = Engine(make_params(), seed=seed, start_date="2026-01-05")
    e.set_scenario({"real_life": True})
    indices = []
    for d in range(days):
        target = e.start + timedelta(days=d + 1)
        if steps:
            t = e.clock
            while t < target:
                t = min(target, t + steps)
                e.advance_to(t)
        else:
            e.advance_to(target)
        indices.append((round(e.live["fuel_index"], 4), round(e.live["demand_index"], 4), round(e.live["delay_index"], 4)))
    return e, indices


def test_real_life_mode_varies_conditions_and_is_deterministic():
    a, ia = run_real_life(40)
    b, ib = run_real_life(40, steps=timedelta(minutes=13))
    assert ia == ib and snapshot(a) == snapshot(b)               # same seed, any tick size -> same result
    assert len(set(x[1] for x in ia)) > 30                        # demand changes day to day
    assert len(set(x[0] for x in ia)) > 30                        # fuel price walks
    kinds = {e["kind"] for e in a.live["events"]} | {e["kind"] for e in a.recent}
    assert "disruption" in kinds
    assert any("at " in ev["text"] for ev in a.recent if ev["kind"] == "disruption")   # weather windows announced
    c, ic = run_real_life(40, seed=22)
    assert ic != ia


def test_real_life_off_is_unchanged_and_switch_on_mid_day_looks_forward():
    base = run(3, seed=9)
    e = Engine(make_params(), seed=9, start_date="2026-01-05")
    e.advance_to(e.start + timedelta(days=3))
    assert snapshot(base) == snapshot(e)                          # default (off) = previous behaviour
    e.set_scenario({"real_life": True})
    now = e.clock
    assert all(ev["start"] >= now for ev in e.live["events"])     # nothing is created in the past
    assert any(ev["kind"] == "scenario" and "Real-life mode on" in ev["text"] for ev in e.recent)
    e.set_scenario({"real_life": False})
    assert e.demand_now() == e.scenario["demand"] and e.fuel_price_now() == e.scenario["fuel_price"]


def test_real_life_state_survives_restore():
    mongomock = pytest.importorskip("mongomock")
    from backend.sim import store
    db = mongomock.MongoClient().simtest_rl
    store.reset(db)
    a = Engine(make_params(), seed=4, start_date="2026-01-05")
    a.set_scenario({"real_life": True})
    a.advance_to(a.start + timedelta(days=5, hours=9))
    store.flush(db, a, False, 900)
    b = store.load(db, make_params())
    assert b.real_life and b.live["day"] == a.live["day"]
    end = a.start + timedelta(days=9)
    a.advance_to(end)
    b.advance_to(end)
    for k, f in snapshot(a).items():
        assert (f["status"], f["etd"], f["pax"]) == (snapshot(b)[k]["status"], snapshot(b)[k]["etd"], snapshot(b)[k]["pax"]), k


def test_bad_weather_cancels_and_delays():
    e = run(4, scenario={"bad_weather": {"enabled": True, "airports": ["JFK", "ORD", "BOS"]}})
    assert any(f["cancel_category"] == "weather" for f in e.flights.values())
    assert any(f["delay_reason"] == "Weather" for f in e.flights.values())
    assert all(f["status"] in DONE or f["std"] >= e.clock - timedelta(hours=12) for f in e.flights.values()
               if f["day"] < e.days_generated[-2])
