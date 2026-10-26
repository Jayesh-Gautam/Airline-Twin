"""Airline Twin API - operations simulator + historical analytics.

  uvicorn backend.main:app --port 8000        (from the project root)
  docs: http://127.0.0.1:8000/docs

This is a simulation and analytics project, not a real flight-control system.
"""
import asyncio
import json
import os
import sys
import threading
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
import config as C  # noqa: E402

from .sim import analysis, geo  # noqa: E402
from .sim import params as P  # noqa: E402
from .sim.engine import AIRBORNE, DONE  # noqa: E402
from .sim.runner import SPEEDS, Runner  # noqa: E402
from . import history  # noqa: E402

app = FastAPI(title="Airline Twin API",
              description="Operations simulator and historical analytics for six FICTIONAL airlines. "
                          "Simulation, not real flight data. Costs and profit are illustrative estimates (config.py).",
              version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_state = {"db": None, "runner": None, "params": None}
_init_lock = threading.Lock()


class ServiceUnavailable(Exception):
    def __init__(self, error, hint):
        self.error, self.hint = error, hint


@app.exception_handler(ServiceUnavailable)
async def _unavailable(_, e):
    return JSONResponse(status_code=503, content={"error": e.error, "hint": e.hint})


def get_db():
    if _state["db"] is None:
        from pymongo import MongoClient
        client = MongoClient(os.environ.get("MONGO_URI", C.MONGO_URI), serverSelectionTimeoutMS=2500, tz_aware=False)
        try:
            client.admin.command("ping")
        except Exception as e:
            raise ServiceUnavailable(f"MongoDB is not reachable ({type(e).__name__})",
                                     "Start the MongoDB service, then retry.")
        _state["db"] = client[os.environ.get("MONGO_DB", C.MONGO_DB)]
    return _state["db"]


def get_runner():
    with _init_lock:
        if _state["runner"] is None:
            db = get_db()
            try:
                _state["params"] = P.load(db)
            except P.ParamsMissing as e:
                raise ServiceUnavailable(str(e), "python run_pipeline.py --data data/1m")
            _state["runner"] = Runner(db, _state["params"])
        return _state["runner"]


# ------------------------------------------------------------------ serialisation
def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S") if isinstance(t, datetime) else t


def flight_out(eng, f, now):
    rev, c = eng.money_at(f, now)
    cost_now = sum(c.values())
    pos = None
    if f["status"] in AIRBORNE:
        a, b = eng.p.coords[f["origin"]], eng.p.coords[f["destination"]]
        t0 = f["atd"] + timedelta(minutes=C.TAXI_OUT_MIN)
        t1 = f["eta"] - timedelta(minutes=10)
        frac = (now - t0).total_seconds() / max(60.0, (t1 - t0).total_seconds())
        la, lo, hd = geo.position(a["lat"], a["lon"], b["lat"], b["lon"], frac)
        pos = {"lat": round(la, 4), "lon": round(lo, 4), "heading": round(hd, 1), "progress": round(max(0, min(1, frac)), 4)}
    burn = C.FUEL_BURN_KG_PER_HR.get(f["model"], C.DEFAULT_FUEL_BURN_KG_PER_HR)
    return {
        "id": f["_id"], "day": f["day"], "flight_number": f["flight_number"], "airline_id": f["airline_id"],
        "airline": f["airline"], "airline_code": f["airline_code"], "route": f["route"], "origin": f["origin"],
        "destination": f["destination"], "distance_km": f["distance_km"], "block_h": f["block_h"],
        "registration": f["registration"], "model": f["model"], "capacity": f["capacity"], "is_ferry": f["is_ferry"],
        "status": f["status"], "std": iso(f["std"]), "sta": iso(f["sta"]), "etd": iso(f["etd"]), "eta": iso(f["eta"]),
        "atd": iso(f["atd"]), "ata": iso(f["ata"]), "delay_minutes": f["delay_minutes"] if f["delay_checked"] else 0,
        "delay_reason": f["delay_reason"], "cancel_reason": f["cancel_reason"], "pax": f["pax"],
        "load_factor": f["load_factor"], "break_even_lf": f["break_even_lf"], "revenue": round(rev, 2),
        "cost_so_far": round(cost_now, 2), "profit_so_far": round(rev - cost_now, 2),
        "profit_projected": f["profit_projected"] if f["status"] not in DONE else round(f["revenue"] - sum(f["cost"].values()), 2),
        "revenue_lost": f["revenue_lost"], "fuel_kg_est": round(burn * f["block_h"] + C.TAXI_FUEL_KG),
        "loss": f["loss_flagged"], "position": pos}


def event_out(e):
    return {**{k: v for k, v in e.items() if k != "_id"}, "time": iso(e["time"])}


def state_out(r):
    eng = r.engine
    return {"clock": iso(eng.clock), "day": eng.clock.date().isoformat(), "day_index": eng.day_index(),
            "weekday": eng.clock.strftime("%a"), "running": r.running, "speed": r.speed, "speeds": SPEEDS,
            "seed": eng.seed, "start_date": eng.start.date().isoformat(), "scenario": eng.scenario,
            "event_seq": eng.event_seq, "error": r.error, "conditions": eng.live_status(),
            "disclaimer": "Simulation, not real flight data. Fictional airlines; costs are illustrative estimates."}


def _aid(airline):
    return int(airline) if airline not in (None, "", "all") else None


def live_pnl(eng, aid):
    day = eng.clock.date().isoformat()
    yday = (eng.clock - timedelta(days=1)).date().isoformat()
    t = eng.day_totals(day, aid)
    hour = eng.clock.hour

    def hourly(d):
        keys = [aid] if aid is not None else sorted(eng.p.airlines)
        rows = {}
        for k in keys:
            for h in eng.hourly.get((k, d), []):
                r = rows.setdefault(h["h"], {"h": h["h"], "revenue": 0.0, "cost": 0.0, "profit": 0.0, "pax": 0})
                for x in ("revenue", "cost", "profit", "pax"):
                    r[x] += h[x]
        return [rows[h] for h in sorted(rows)]

    yh = hourly(yday)
    same = next((h for h in yh if h["h"] == hour), None) if hour else None
    ytot = eng.day_totals(yday, aid) if yday in eng.by_day else None
    return {"day": day, "day_index": eng.day_index(), "clock": iso(eng.clock), **t,
            "hourly": hourly(day) + [{"h": hour + eng.clock.minute / 60, "revenue": t["revenue"], "cost": t["cost_total"],
                                      "profit": t["profit"], "pax": t["pax"]}],
            "hourly_yesterday": yh, "yesterday_same_time": same, "yesterday": {k: ytot[k] for k in ("revenue", "cost_total", "profit", "pax", "flights")} if ytot else None,
            "is_estimate": True}


def flights_now(eng, aid, status=None):
    now = eng.clock
    day = now.date().isoformat()
    ids = list(eng.by_day.get(day, ()))
    prev = (now - timedelta(days=1)).date().isoformat()
    ids += [i for i in eng.by_day.get(prev, ()) if eng.flights[i]["status"] not in DONE]
    out = []
    for i in ids:
        f = eng.flights[i]
        if aid is not None and f["airline_id"] != aid:
            continue
        if status and f["status"].lower().replace(" ", "_") != status.lower().replace(" ", "_"):
            continue
        out.append(flight_out(eng, f, now))
    return sorted(out, key=lambda f: (f["etd"], f["id"]))


# ------------------------------------------------------------------ reference data
@app.get("/health", tags=["meta"])
def health():
    try:
        get_db()
        ok = True
    except ServiceUnavailable:
        ok = False
    return {"mongodb": ok, "simulator": _state["runner"] is not None}


@app.get("/airlines", tags=["reference"])
def airlines():
    r = get_runner()
    p = r.params
    out = []
    for aid, a in sorted(p.airlines.items()):
        fleet = [x for x in p.aircraft if x["airline_id"] == aid]
        out.append({"id": aid, "name": a["airline"], "code": a["code"], "hub": a["hub"], "fleet": len(fleet),
                    "routes": len(p.routes.get(aid, [])), "fictional": True})
    return out


@app.get("/airports", tags=["reference"])
def airports(airline: str = None):
    p = get_runner().params
    aid = _aid(airline)
    served = {}
    for a_id, rs in p.routes.items():
        for r in rs:
            for x in (r["origin"], r["destination"]):
                served.setdefault(x, set()).add(a_id)
    routes = [{"airline_id": a_id, "route": r["route"], "origin": r["origin"], "destination": r["destination"],
               "distance_km": round(r["distance_km"]), "departures_hist": r["departures"],
               "arc": geo.arc(p.coords[r["origin"]]["lat"], p.coords[r["origin"]]["lon"],
                              p.coords[r["destination"]]["lat"], p.coords[r["destination"]]["lon"], 32)}
              for a_id, rs in p.routes.items() if aid is None or a_id == aid for r in rs]
    aps = [{**{k: c[k] for k in ("iata", "name", "lat", "lon", "city", "country")}, "airlines": sorted(served.get(k, []))}
           for k, c in sorted(p.coords.items()) if aid is None or aid in served.get(k, set())]
    return {"airports": aps, "routes": routes, "source": "OurAirports (public domain)"}


# ------------------------------------------------------------------ simulation control
class SpeedIn(BaseModel):
    speed: int


class ResetIn(BaseModel):
    seed: int | None = None
    start_date: str | None = None


class WeatherIn(BaseModel):
    enabled: bool = False
    airports: list[str] = []


class ScenarioIn(BaseModel):
    demand: float | None = None
    delay_multiplier: float | None = None
    fuel_price: float | None = None
    bad_weather: WeatherIn | None = None
    grounded_aircraft: list[int] | None = None
    real_life: bool | None = None


@app.get("/sim/state", tags=["simulation"])
def sim_state():
    return state_out(get_runner())


@app.post("/sim/start", tags=["simulation"])
def sim_start():
    r = get_runner(); r.start(); return state_out(r)


@app.post("/sim/pause", tags=["simulation"])
def sim_pause():
    r = get_runner(); r.pause(); return state_out(r)


@app.post("/sim/reset", tags=["simulation"])
def sim_reset(body: ResetIn = ResetIn()):
    r = get_runner()
    if body.start_date:
        try:
            datetime.fromisoformat(body.start_date)
        except ValueError:
            raise HTTPException(422, "start_date must be YYYY-MM-DD")
    r.reset(body.seed, body.start_date)
    return state_out(r)


@app.post("/sim/speed", tags=["simulation"])
def sim_speed(body: SpeedIn):
    if body.speed not in SPEEDS:
        raise HTTPException(422, f"speed must be one of {SPEEDS} (sim seconds per real second)")
    r = get_runner(); r.set_speed(body.speed); return state_out(r)


@app.post("/sim/next-day", tags=["simulation"])
def sim_next_day():
    r = get_runner(); r.next_day(); return state_out(r)


class AdvanceIn(BaseModel):
    days: int


@app.post("/sim/advance", tags=["simulation"])
def sim_advance(body: AdvanceIn):
    """Fast-forward 1-90 whole simulated days (the clock stops at midnight)."""
    if not 1 <= body.days <= 90:
        raise HTTPException(422, "days must be between 1 and 90")
    r = get_runner()
    r.advance(body.days)
    return state_out(r)


@app.get("/sim/scenario", tags=["simulation"])
def get_scenario():
    return get_runner().engine.scenario


@app.post("/sim/scenario", tags=["simulation"])
def set_scenario(body: ScenarioIn):
    if body.demand is not None and not 0.5 <= body.demand <= 1.3:
        raise HTTPException(422, "demand must be between 0.5 and 1.3")
    if body.delay_multiplier is not None and not 0 <= body.delay_multiplier <= 3:
        raise HTTPException(422, "delay_multiplier must be between 0 and 3")
    if body.fuel_price is not None and not 0.2 <= body.fuel_price <= 3:
        raise HTTPException(422, "fuel_price must be between 0.2 and 3.0 per kg")
    r = get_runner()
    r.scenario(body.model_dump(exclude_none=True))
    return r.engine.scenario


# ------------------------------------------------------------------ simulation data
@app.get("/sim/flights", tags=["simulation"])
def sim_flights(airline: str = None, status: str = None):
    r = get_runner()
    with r.lock:
        return flights_now(r.engine, _aid(airline), status)


@app.get("/sim/events", tags=["simulation"])
def sim_events(airline: str = None, limit: int = Query(50, le=1000), after: int = 0, day: str = None):
    r = get_runner()
    aid = _aid(airline)
    with r.lock:
        evs = [e for e in r.engine.recent if e["seq"] > after and (aid is None or e["airline_id"] in (aid, None))
               and (day is None or e["day"] == day)]
    if len(evs) < limit and after == 0 and day is None:
        q = {} if aid is None else {"airline_id": {"$in": [aid, None]}}
        evs = list(get_db().flight_events.find(q).sort("seq", -1).limit(limit))[::-1]
    return [event_out(e) for e in evs[-limit:]][::-1]


@app.get("/sim/pnl/live", tags=["simulation"])
def sim_pnl_live(airline: str = None):
    r = get_runner()
    with r.lock:
        return live_pnl(r.engine, _aid(airline))


@app.get("/sim/pnl/daily", tags=["simulation"])
def sim_pnl_daily(airline: str = None):
    r = get_runner()
    aid = _aid(airline)
    with r.lock:
        eng = r.engine
        out = []
        for day in eng.days_generated:
            t = eng.day_totals(day, aid)
            d = datetime.fromisoformat(day)
            out.append({"day": day, "day_index": eng.day_index(day), "weekday": d.strftime("%a"),
                        "closed": eng.clock >= d + timedelta(days=1) and not any(
                            eng.flights[i]["status"] not in DONE for i in eng.by_day.get(day, ())
                            if aid is None or eng.flights[i]["airline_id"] == aid),
                        **{k: t[k] for k in ("revenue", "cost_total", "profit", "pax", "flights", "cancelled",
                                             "delayed", "load_factor", "revenue_lost")}, "cost": t["cost"]})
    return out


PERIOD_DAYS = {"day": 1, "month": 30, "6m": 182, "year": 365}
_closed_cache = {}          # (engine id, airline, day) -> totals of a finished day (they never change)
DAY_KEYS = ("revenue", "cost_total", "profit", "pax", "seats", "flights", "delayed", "cancelled", "revenue_lost")


def _day_row(eng, aid, day):
    key = (id(eng), aid, day)
    if key in _closed_cache:
        return _closed_cache[key]
    t = eng.day_totals(day, aid)
    d = datetime.fromisoformat(day)
    closed = eng.clock >= d + timedelta(days=1) and not any(
        eng.flights[i]["status"] not in DONE for i in eng.by_day.get(day, ()) if aid is None or eng.flights[i]["airline_id"] == aid)
    row = {"day": day, "day_index": eng.day_index(day), "weekday": d.strftime("%a"), "closed": closed,
           **{k: t[k] for k in DAY_KEYS}, "cost": t["cost"], "load_factor": t["load_factor"]}
    if closed:
        _closed_cache[key] = row
    return row


def _sum_rows(rows):
    out = {k: round(sum(r[k] for r in rows), 2) for k in DAY_KEYS}
    out["cost"] = {k: round(sum(r["cost"][k] for r in rows), 2) for k in (rows[0]["cost"] if rows else {})}
    out["load_factor"] = round(out["pax"] / out["seats"], 4) if out["seats"] else None
    return out


@app.get("/sim/pnl/period", tags=["simulation"])
def sim_pnl_period(airline: str = None, period: str = "month"):
    """Totals and one row per simulated day for a window ending today:
    day, month (30 days), 6m (182), year (365) or ytd (since 1 January of the sim year)."""
    if period not in (*PERIOD_DAYS, "ytd"):
        raise HTTPException(422, "period must be one of day, month, 6m, year, ytd")
    r = get_runner()
    aid = _aid(airline)
    with r.lock:
        eng = r.engine
        end = eng.clock.date()
        if period == "ytd":
            start = end.replace(month=1, day=1)
        else:
            start = end - timedelta(days=PERIOD_DAYS[period] - 1)
        length = (end - start).days + 1
        first = eng.start.date()
        sim_start = max(start, first)
        days = [d for d in eng.days_generated if sim_start.isoformat() <= d <= end.isoformat()]
        rows = [_day_row(eng, aid, d) for d in days]
        # the same-length window just before, only if it was fully simulated
        p_end, p_start = start - timedelta(days=1), start - timedelta(days=length)
        prev = None
        if p_start >= first:
            prev_rows = [_day_row(eng, aid, d) for d in eng.days_generated if p_start.isoformat() <= d <= p_end.isoformat()]
            prev = _sum_rows(prev_rows) if len(prev_rows) == length else None
    cum, series = 0.0, []
    for x in rows:
        cum += x["profit"]
        series.append({**x, "cumulative_profit": round(cum, 2)})
    return {"period": period, "start": start.isoformat(), "end": end.isoformat(), "window_days": length,
            "simulated_days": len(rows), "first_simulated": first.isoformat(), "totals": _sum_rows(rows) if rows else None,
            "previous": prev, "daily": series, "is_estimate": True}


@app.get("/sim/pnl/day/{day}", tags=["simulation"])
def sim_pnl_day(day: str, airline: str = None):
    r = get_runner()
    aid = _aid(airline)
    with r.lock:
        eng = r.engine
        if day not in eng.by_day:
            raise HTTPException(404, f"day {day} has not been simulated")
        t = eng.day_totals(day, aid)
        flights = [flight_out(eng, eng.flights[i], eng.clock) for i in eng.by_day[day]
                   if aid is None or eng.flights[i]["airline_id"] == aid]
        return {"totals": t, "why": analysis.explain_day(eng, aid, day),
                "flights": sorted(flights, key=lambda f: f["profit_so_far"])}


@app.get("/sim/routes", tags=["simulation"])
def sim_routes(airline: str = None):
    r = get_runner()
    aid = _aid(airline)
    with r.lock:
        sim = analysis.route_stats(r.engine, aid)
    hist = {(h["airline"], h["route"]): h for h in get_db().a_route_profitability.find({}, {"_id": 0})}
    for s in sim:
        h = hist.get((s["airline"], s["route"]))
        s["historical"] = {k: h[k] for k in ("departures", "avg_load_factor", "revenue", "profit_est", "margin_est")} if h else None
    return sim


@app.get("/sim/fleet", tags=["simulation"])
def sim_fleet(airline: str = None):
    r = get_runner()
    aid = _aid(airline)
    with r.lock:
        eng = r.engine
        now = eng.clock
        out = []
        for ac in sorted(eng.aircraft.values(), key=lambda a: a["_id"]):
            if aid is not None and ac["airline_id"] != aid:
                continue
            legs = [eng.flights[i] for i in eng.legs[ac["_id"]]]
            flown = [f for f in legs if f["status"] in AIRBORNE + ("Landed",)]
            current = next((f for f in legs if f["status"] in AIRBORNE), None)
            m = next((m for m in eng.maint if m["aircraft_id"] == ac["_id"] and m["start"] <= now < m["end"]), None)
            upcoming = next((m for m in eng.maint if m["aircraft_id"] == ac["_id"] and m["start"] > now), None)
            status = ("Grounded" if ac["grounded"] else "Maintenance" if m else "In Flight" if current else "On ground")
            loc = current["route"] if current else eng._position_before(ac)[0]
            out.append({"id": ac["_id"], "registration": ac["registration"], "model": ac["model"],
                        "capacity": ac["capacity"], "airline_id": ac["airline_id"],
                        "airline": eng.p.airlines[ac["airline_id"]]["airline"], "status": status, "location": loc,
                        "flights": len(flown), "block_hours": round(sum(f["block_h"] for f in flown), 1),
                        "crew_cost_est": round(sum(f["cost"]["crew"] for f in legs), 2),
                        "revenue": round(sum(f["revenue"] for f in flown), 2),
                        "maintenance": {"type": m["type"], "until": iso(m["end"])} if m else None,
                        "next_maintenance": {"type": upcoming["type"], "start": iso(upcoming["start"])} if upcoming else None,
                        "maintenance_cost_est": round(sum(x["cost"] for x in eng.maint if x["aircraft_id"] == ac["_id"] and x["start"] <= now), 2)})
        return out


@app.get("/sim/stream", tags=["simulation"])
async def sim_stream(request: Request, airline: str = None, after: int = 0):
    """Server-Sent Events: clock, flights (with positions), new events and live P&L, twice a second."""
    r = get_runner()
    aid = _aid(airline)

    async def gen():
        last = after
        last_version = None
        first = True
        while True:
            if await request.is_disconnected():
                break
            with r.lock:
                eng = r.engine
                evs = [e for e in eng.recent if e["seq"] > last and (aid is None or e["airline_id"] in (aid, None))]
                if first and not after:
                    evs = evs[-50:]
                msg = {"state": state_out(r), "flights": flights_now(eng, aid), "pnl": live_pnl(eng, aid),
                       "events": [event_out(e) for e in evs][::-1]}
                last = eng.event_seq
                changed = (r.version, eng.event_seq, r.running, r.speed) != last_version
                last_version = (r.version, eng.event_seq, r.running, r.speed)
            if changed or first:
                yield f"data: {json.dumps(msg, default=str)}\n\n"
            else:
                yield ": keep-alive\n\n"
            first = False
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


app.include_router(history.router(get_db, _aid))
