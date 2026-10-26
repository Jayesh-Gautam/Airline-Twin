"""Simulation state in MongoDB.

  simulation_state  one document: clock, speed, running, scenario, seed, start date
  sim_flights       one document per simulated departure (status, times, money)
  sim_aircraft      runtime state per aircraft (location, grounded)
  sim_maintenance   maintenance windows (planned and drawn from historical rates)
  flight_events     timestamped event log
  sim_daily_pnl     one document per airline per simulated day (with hourly snapshots)

reset() clears only these collections; the pipeline's collections are untouched.
"""
from datetime import timedelta

from pymongo import ASCENDING, DESCENDING, ReplaceOne

from .engine import AIRBORNE, DONE, PRI_DAY, PRI_FLIGHT, PRI_HOUR, PRI_MAINT, Engine, default_scenario, new_live

COLLECTIONS = ["simulation_state", "sim_flights", "sim_aircraft", "sim_maintenance", "flight_events", "sim_daily_pnl"]


def ensure_indexes(db):
    db.sim_flights.create_index([("airline_id", ASCENDING), ("day", ASCENDING)])
    db.sim_flights.create_index("status")
    db.flight_events.create_index([("airline_id", ASCENDING), ("seq", DESCENDING)])
    db.flight_events.create_index([("seq", DESCENDING)])
    db.sim_daily_pnl.create_index([("airline_id", ASCENDING), ("day", ASCENDING)])


def reset(db):
    for c in COLLECTIONS:
        db[c].drop()
    ensure_indexes(db)


def state_doc(eng, running, speed):
    return {"_id": "state", "clock": eng.clock, "start_date": eng.start.date().isoformat(), "seed": eng.seed,
            "running": running, "speed": speed, "scenario": eng.scenario, "event_seq": eng.event_seq,
            "days_generated": eng.days_generated, "day_index": eng.day_index(), "live": eng.live}


def _upsert(coll, docs):
    if not docs:
        return
    try:
        coll.bulk_write([ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs], ordered=False)
    except TypeError:            # mongomock (tests) can't take pymongo 4.x bulk ReplaceOne
        for d in docs:
            coll.replace_one({"_id": d["_id"]}, d, upsert=True)


def flush(db, eng, running, speed):
    """Write everything that changed since the last flush."""
    _upsert(db.sim_flights, [eng.flights[i] for i in sorted(eng.dirty_flights)])
    _upsert(db.sim_aircraft, [eng.aircraft[i] for i in sorted(eng.dirty_aircraft)])
    by = {m["_id"]: m for m in eng.maint}
    _upsert(db.sim_maintenance, [by[i] for i in sorted(eng.dirty_maint)])
    _upsert(db.sim_daily_pnl, [eng.daily_doc(a, d) for a, d in sorted(eng.dirty_days)])
    if eng.new_events:
        db.flight_events.insert_many(eng.new_events, ordered=False)
    eng.dirty_flights.clear(); eng.dirty_aircraft.clear(); eng.dirty_maint.clear()
    eng.dirty_days.clear(); eng.new_events = []
    db.simulation_state.replace_one({"_id": "state"}, state_doc(eng, running, speed), upsert=True)


def load(db, params):
    """Rebuild an Engine from MongoDB, or None when there is no saved simulation."""
    st = db.simulation_state.find_one({"_id": "state"})
    if not st:
        return None
    eng = Engine(params, seed=st["seed"], start_date=st["start_date"])
    eng.heap.clear(); eng.maint.clear(); eng.new_events = []
    eng.dirty_flights.clear(); eng.dirty_maint.clear(); eng.dirty_days.clear(); eng.dirty_aircraft.clear()
    eng.clock, eng.scenario = st["clock"], {**default_scenario(), **st["scenario"]}
    eng.live = st.get("live") or new_live()
    eng.event_seq, eng.days_generated = st["event_seq"], list(st["days_generated"])
    for a in db.sim_aircraft.find():
        if a["_id"] in eng.aircraft:
            eng.aircraft[a["_id"]].update(a)
    for f in db.sim_flights.find().sort([("std", 1), ("_id", 1)]):
        eng.flights[f["_id"]] = f
        eng.by_day[f["day"]].append(f["_id"])
        eng.legs[f["aircraft_id"]].append(f["_id"])
    eng.maint = list(db.sim_maintenance.find().sort("start", 1))
    for d in db.sim_daily_pnl.find():
        eng.hourly[(d["airline_id"], d["day"])] = d.get("hourly", [])
    for e in db.flight_events.find().sort("seq", -1).limit(eng.recent.maxlen):
        eng.recent.appendleft(e)
    # re-create the pending timeline
    c = eng.clock
    if eng.days_generated:
        last = eng.days_generated[-1]
        nxt = eng.start.__class__.fromisoformat(last) + timedelta(days=1)
        eng._push(nxt, PRI_DAY, "day", nxt.date().isoformat())
        for h in range(1, 25):
            t = nxt - timedelta(days=1) + timedelta(hours=h)
            if t > c:
                eng._push(t, PRI_HOUR, "hour", f"{last}|{h}")
    else:
        eng._push(eng.start, PRI_DAY, "day", eng.start.date().isoformat())
    for m in eng.maint:
        if not m.get("started"):
            eng._push(max(m["start"], c), PRI_MAINT, "maint", m["_id"])
    for e in eng.live["events"]:
        if not e.get("announced") and e["end"] > c:
            eng._push(max(e["start"], c), PRI_MAINT, "live", e["id"])
    lead = timedelta(minutes=15)
    for f in eng.flights.values():
        st_ = f["status"]
        if st_ in DONE:
            continue
        if st_ == "Scheduled":
            eng._push(max(c, f["std"] - timedelta(minutes=40)), PRI_FLIGHT, "board", f["_id"])
        elif st_ in ("Delayed", "Boarding"):
            if st_ == "Delayed":
                eng._push(max(c, f["etd"] - timedelta(minutes=40)), PRI_FLIGHT, "board", f["_id"])
            eng._push(max(c, f["etd"]), PRI_FLIGHT, "depart", f["_id"])
        elif st_ in AIRBORNE:
            if st_ == "Departed" and f["atd"] + lead < f["eta"]:
                eng._push(max(c, f["atd"] + lead), PRI_FLIGHT, "air", f["_id"])
            eng._push(max(c, f["eta"]), PRI_FLIGHT, "land", f["_id"])
    return eng
