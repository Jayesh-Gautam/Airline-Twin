"""Discrete-event airline operations simulator.

Time only moves forward through advance_to(t): every scheduled transition up
to t is processed in time order (day roll-over, hourly P&L snapshot,
maintenance start, boarding check, departure, airborne, landing). The clock
tick of the web server only decides how far to advance, never the outcome.

Every random choice is a hash of (seed, flight or aircraft, purpose), so the
same seed and the same scenario changes at the same sim times give the same
results, and a state restored from MongoDB continues identically.

Inputs are the Spark-computed sim_params (routes, weekday pattern, load-factor
distribution, cabin mix, fares, delay odds/minutes/reasons, maintenance rates,
aircraft start positions). Aircraft performance, ground times and cost rates
come from config.py and are illustrative.
"""
import hashlib
import heapq
import math
from collections import defaultdict, deque
from datetime import datetime, timedelta
from statistics import NormalDist

import config as C

DONE = ("Landed", "Cancelled")
AIRBORNE = ("Departed", "In Flight")
COST_KEYS = ("fuel", "crew", "airport", "overhead", "delay", "compensation")
CABINS = ("First", "Business", "Premium Economy", "Economy")
PRI_DAY, PRI_HOUR, PRI_MAINT, PRI_FLIGHT = 0, 1, 2, 3
RANK = {"land": 0, "air": 1, "depart": 2, "board": 3}
MINUTE = timedelta(minutes=1)
_N = NormalDist()


def draw(seed, *keys):
    """Deterministic uniform number in [0, 1) for (seed, keys)."""
    h = hashlib.sha256(repr((seed,) + keys).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def quantile(qs, u):
    """Inverse CDF from evenly spaced quantiles (piecewise linear)."""
    if not qs:
        return 60.0
    x = u * (len(qs) - 1)
    i = min(int(x), len(qs) - 2)
    return qs[i] + (qs[i + 1] - qs[i]) * (x - i)


def pick(weights, u):
    """weights: list of (item, weight); returns the item the uniform u falls on."""
    tot = sum(w for _, w in weights)
    acc = 0.0
    for item, w in weights:
        acc += w / tot
        if u < acc:
            return item
    return weights[-1][0]


def round_up_5(t):
    base = t.replace(minute=0, second=0, microsecond=0)
    m = t.minute + (1 if (t.second or t.microsecond) else 0)
    return base + timedelta(minutes=-(-m // 5) * 5)


def default_scenario():
    return {"demand": 1.0, "delay_multiplier": 1.0, "fuel_price": C.FUEL_PRICE_PER_KG,
            "bad_weather": {"enabled": False, "airports": []}, "grounded_aircraft": [], "real_life": False}


def new_live():
    """Random 'real-life' conditions: daily indices plus timed disruption events."""
    return {"fuel_index": 1.0, "demand_index": 1.0, "delay_index": 1.0, "day": None, "events": []}


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


class Engine:
    def __init__(self, params, seed=C.SIM_SEED, start_date=C.SIM_START_DATE):
        self.p = params
        self.seed = seed
        self.start = datetime.fromisoformat(start_date)
        self.clock = self.start
        self.scenario = default_scenario()
        self.live = new_live()
        self.aircraft = {}
        for a in params.aircraft:
            self.aircraft[a["aircraft_id"]] = {
                "_id": a["aircraft_id"], "airline_id": a["airline_id"], "registration": a["registration"],
                "model": a["model"], "capacity": a["capacity"], "home": a["location"],
                "location": a["location"], "grounded": False, "source_status": a.get("status")}
        self.route_index = {(r["airline_id"], r["origin"], r["destination"]): r
                            for rs in params.routes.values() for r in rs}
        self.flights, self.maint = {}, []
        self.by_day, self.legs, self.hourly = defaultdict(list), defaultdict(list), defaultdict(list)
        self.heap, self._n = [], 0
        self.event_seq, self.new_events, self.recent = 0, [], deque(maxlen=3000)
        self.dirty_flights, self.dirty_aircraft, self.dirty_days, self.dirty_maint = set(), set(), set(), set()
        self.days_generated = []
        self._push(self.start, PRI_DAY, "day", self.start.date().isoformat())
        for ac in self.aircraft.values():   # listed as "maintenance" in the source data
            if ac["source_status"] == "maintenance":
                self._add_maintenance(ac, self.start, "A-check", note="listed as in maintenance in the source data")

    # ------------------------------------------------------------------ clock
    def _push(self, t, pri, kind, ref):
        self._n += 1
        heapq.heappush(self.heap, (t, pri, RANK.get(kind, 9), str(ref), self._n, kind, ref))

    def advance_to(self, target):
        while self.heap and self.heap[0][0] <= target:
            t, _, _, _, _, kind, ref = heapq.heappop(self.heap)
            self.clock = max(self.clock, t)
            getattr(self, "_on_" + kind)(ref)
        self.clock = max(self.clock, target)

    def next_day_start(self):
        d = self.clock.replace(hour=0, minute=0, second=0, microsecond=0)
        return d + timedelta(days=1)

    def day_index(self, day=None):
        d = datetime.fromisoformat(day) if day else self.clock
        return (d.date() - self.start.date()).days + 1

    # ------------------------------------------------------------------ helpers
    def perf(self, model):
        return C.MODEL_PERFORMANCE.get(model, C.DEFAULT_PERFORMANCE)

    def block_h(self, km, model):
        return round(max(C.MIN_BLOCK_H, km * C.ROUTING_FACTOR / self.perf(model)[0] + C.TAXI_BLOCK_H), 3)

    def in_range(self, km, model):
        return km * C.ROUTING_FACTOR <= self.perf(model)[1]

    def turnaround(self, capacity):
        return timedelta(minutes=C.WIDEBODY_TURNAROUND_MIN if capacity > 250 else C.TURNAROUND_MIN)

    def crew_rate(self, f):
        r = C.CREW_RATE_PER_HR
        pilots = (r["captain"] + r["first_officer"]) * (2 if f["block_h"] > C.RELIEF_PILOTS_ABOVE_H else 1)
        return pilots + r["purser"] + math.ceil(f["capacity"] / C.SEATS_PER_CABIN_CREW) * r["cabin"]

    # ---- effective conditions: the scenario sliders, x real-life conditions when that mode is on
    @property
    def real_life(self):
        return bool(self.scenario.get("real_life"))

    def _active(self, kind, t=None):
        t = t or self.clock
        return [e for e in self.live["events"] if e["kind"] == kind and e["start"] <= t < e["end"]]

    def demand_now(self):
        d = self.scenario["demand"]
        if self.real_life:
            d *= self.live["demand_index"]
            for e in self._active("demand"):
                d *= e["factor"]
        return d

    def fuel_price_now(self):
        return self.scenario["fuel_price"] * (self.live["fuel_index"] if self.real_life else 1.0)

    def delay_mult_at(self, iata):
        m = self.scenario["delay_multiplier"]
        if self.real_life:
            m *= self.live["delay_index"]
            for e in self._active("atc"):
                if iata in e["airports"]:
                    m *= e["factor"]
        return m

    def weather_at(self, iata):
        w = self.scenario["bad_weather"]
        if bool(w.get("enabled")) and iata in (w.get("airports") or []):
            return True
        return self.real_life and any(iata in e["airports"] for e in self._active("weather"))

    def _event(self, kind, text, f=None, amount=None, airline_id=None):
        self.event_seq += 1
        aid = f["airline_id"] if f else airline_id
        e = {"_id": self.event_seq, "seq": self.event_seq, "time": self.clock, "day": self.clock.date().isoformat(),
             "day_index": self.day_index(), "kind": kind, "text": text,
             "amount": round(amount, 2) if amount is not None else None, "airline_id": aid,
             "airline": self.p.airlines[aid]["airline"] if aid in self.p.airlines else None,
             "flight_id": f["_id"] if f else None, "flight_number": f["flight_number"] if f else None,
             "status": f["status"] if f else None}
        self.new_events.append(e)
        self.recent.append(e)

    def _dirty(self, f):
        self.dirty_flights.add(f["_id"])
        self.dirty_days.add((f["airline_id"], f["day"]))

    # ------------------------------------------------------------------ economics
    def _fare_scale(self, f):
        """Historical fares average 316 for a 5.5 h average block, whatever the distance.
        Keep that revenue per block-hour: scale each route's historical fare by its real block time."""
        return (f["block_h"] / self.p.glob["hist_block_mean"]) ** C.FARE_BLOCK_EXPONENT

    def _demand(self, f):
        """Passengers (by cabin) and revenue at the current demand level."""
        if f["is_ferry"]:
            return 0, {}, 0.0, 0.0
        r = self.route_index.get((f["airline_id"], f["origin"], f["destination"]), {})
        g = self.p.glob
        u = min(max(draw(self.seed, f["_id"], "lf"), 1e-6), 1 - 1e-6)
        lf = r.get("lf_mean", g["lf_mean"]) + r.get("lf_sd", g["lf_sd"]) * _N.inv_cdf(u)
        lf = min(1.0, max(C.LOAD_FACTOR_MIN, min(1.0, lf)) * self.demand_now())
        pax = int(round(lf * f["capacity"]))
        share = r.get("cabin_share") or g["cabin_share"]
        fares = r.get("fare_by_cabin") or g["fare_by_cabin"]
        scale = self._fare_scale(f)

        def split(n):
            raw = {c: n * share.get(c, 0.0) for c in CABINS}
            out = {c: int(v) for c, v in raw.items()}
            for c in sorted(CABINS, key=lambda c: (out[c] - raw[c], CABINS.index(c)))[:n - sum(out.values())]:
                out[c] += 1
            return out

        cab = split(pax)
        rev = sum(n * fares.get(c, g["fare_by_cabin"].get(c, 0.0)) * scale for c, n in cab.items())
        full = sum(n * fares.get(c, g["fare_by_cabin"].get(c, 0.0)) * scale for c, n in split(f["capacity"]).items())
        return pax, cab, rev, full

    def _normal_costs(self, f, price):
        burn = C.FUEL_BURN_KG_PER_HR.get(f["model"], C.DEFAULT_FUEL_BURN_KG_PER_HR)
        return {"fuel": (burn * f["block_h"] + C.TAXI_FUEL_KG) * price,
                "crew": self.crew_rate(f) * f["block_h"],
                "airport": C.AIRPORT_FEE_BASE + f["capacity"] * C.AIRPORT_FEE_PER_SEAT,
                "overhead": C.OWNERSHIP_OVERHEAD_PER_SEAT_HOUR * f["capacity"] * f["block_h"]}

    def _delay_costs(self, f, minutes, price, pax):
        h = minutes / 60
        burn = C.FUEL_BURN_KG_PER_HR.get(f["model"], C.DEFAULT_FUEL_BURN_KG_PER_HR)
        extra = (burn * C.HOLDING_SHARE_OF_DELAY * C.HOLDING_BURN_FACTOR * h * price
                 + self.crew_rate(f) * h * C.CREW_OVERTIME_MULTIPLIER)
        comp = (pax * C.DELAY_COMPENSATION_PER_PAX * C.COMPENSATION_CLAIM_RATE
                if minutes >= C.DELAY_COMPENSATION_AFTER_MIN else 0.0)
        return extra, comp

    def _project(self, f):
        """Refresh passengers, revenue and planned costs before departure."""
        price = f["fuel_price"] or self.fuel_price_now()
        if f["status"] not in AIRBORNE + DONE:
            f["pax"], f["pax_by_cabin"], f["revenue_expected"], full = self._demand(f)
            f["revenue_full"] = round(full, 2)
        f["plan"] = {k: round(v, 2) for k, v in self._normal_costs(f, price).items()}
        f["load_factor"] = round(f["pax"] / f["capacity"], 4) if f["capacity"] else 0.0
        normal = sum(f["plan"].values())
        f["break_even_lf"] = round(min(9.99, normal / f["revenue_full"]), 4) if f["revenue_full"] else None
        extra, comp = self._delay_costs(f, f["delay_minutes"], price, f["pax"])
        f["delay_cost_projected"] = round(extra + comp, 2)
        f["profit_projected"] = round(f["revenue_expected"] - normal - extra - comp, 2)

    def money_at(self, f, now):
        """(revenue, {cost by category}) recognised for a flight at time now.
        Revenue is booked at departure; fuel, crew and overhead accrue with flight progress."""
        st = f["status"]
        if st in ("Landed", "Cancelled"):
            return f["revenue"], dict(f["cost"])
        if st in AIRBORNE:
            span = (f["eta"] - f["atd"]).total_seconds() or 1
            prog = min(1.0, max(0.0, (now - f["atd"]).total_seconds() / span))
            c = dict(f["cost"])
            for k in ("fuel", "crew", "overhead"):
                c[k] = f["plan"][k] * prog
            return f["revenue"], c
        return 0.0, dict.fromkeys(COST_KEYS, 0.0)

    # ------------------------------------------------------------------ schedule
    def _position_before(self, ac, f=None):
        """Where the aircraft is (or will be) and when it is ready, before leg f
        (or after its last leg when f is None)."""
        legs = self.legs[ac["_id"]]
        if f is not None:
            legs = legs[:legs.index(f["_id"])] if f["_id"] in legs else legs
        for fid in reversed(legs):
            p = self.flights[fid]
            if p["status"] != "Cancelled":
                return p["destination"], (p["ata"] or p["eta"]) + self.turnaround(ac["capacity"])
        return ac["home"], self.start

    def _maintenance_overlap(self, aircraft_id, t0, t1):
        for m in self.maint:
            if m["aircraft_id"] == aircraft_id and m["start"] < t1 and m["end"] > t0:
                return m
        return None

    def _after_maintenance(self, aircraft_id, t):
        m = self._maintenance_overlap(aircraft_id, t, t + MINUTE)
        while m:
            t = m["end"]
            m = self._maintenance_overlap(aircraft_id, t, t + MINUTE)
        return t

    def _reposition_target(self, airline_id, loc, ac):
        """Nearest airport of the airline's network with a route this aircraft can fly."""
        best = None
        for (aid, origin), rs in self.p.routes_from.items():
            if aid != airline_id or origin == loc or loc not in self.p.coords:
                continue
            if not any(self.in_range(r["distance_km"], ac["model"]) for r in rs):
                continue
            d = self.p.distance(loc, origin)
            if self.in_range(d, ac["model"]) and (best is None or d < best[0]):
                best = (d, origin)
        return best[1] if best else None

    def _create(self, ac, origin, dest, km, std, seq, number, is_ferry=False):
        al = self.p.airlines[ac["airline_id"]]
        day = std.date().isoformat()
        f = {"_id": f"{day}-{al['code']}{seq:03d}", "day": day, "day_index": self.day_index(day),
             "airline_id": ac["airline_id"], "airline": al["airline"], "airline_code": al["code"],
             "flight_number": number, "route": f"{origin}-{dest}", "origin": origin, "destination": dest,
             "distance_km": round(km, 1), "aircraft_id": ac["_id"], "registration": ac["registration"],
             "model": ac["model"], "capacity": ac["capacity"], "is_ferry": is_ferry,
             "block_h": self.block_h(km, ac["model"]), "std": std, "status": "Scheduled",
             "atd": None, "ata": None, "delay_minutes": 0, "delay_reason": None, "delay_checked": False,
             "cancel_reason": None, "cancel_category": None, "pax": 0, "pax_by_cabin": {},
             "revenue": 0.0, "revenue_expected": 0.0, "revenue_full": 0.0, "revenue_lost": 0.0,
             "cost": dict.fromkeys(COST_KEYS, 0.0), "fuel_price": None, "loss_flagged": False}
        f["sta"] = f["etd"] = None
        f["sta"] = std + timedelta(hours=f["block_h"])
        f["etd"], f["eta"] = std, f["sta"]
        self._project(f)
        self.flights[f["_id"]] = f
        self.by_day[day].append(f["_id"])
        self.legs[ac["_id"]].append(f["_id"])
        self._push(std - timedelta(minutes=C.BOARDING_LEAD_MIN), PRI_FLIGHT, "board", f["_id"])
        self._dirty(f)
        return f

    def _on_day(self, day):
        D = datetime.fromisoformat(day)
        self.days_generated.append(day)
        self._push(D + timedelta(days=1), PRI_DAY, "day", (D + timedelta(days=1)).date().isoformat())
        for h in range(1, 25):
            self._push(D + timedelta(hours=h), PRI_HOUR, "hour", f"{day}|{h}")
        self._draw_maintenance(D)
        wd = D.weekday()
        for aid in sorted(self.p.airlines):
            al = self.p.airlines[aid]
            target = C.DAILY_BLOCK_TARGET_H * min(1.3, max(0.6, al["weekday_factor"][wd]))
            seq, used = 0, defaultdict(int)
            for ac in sorted((a for a in self.aircraft.values() if a["airline_id"] == aid), key=lambda a: a["_id"]):
                if ac["grounded"]:
                    continue
                loc, ready = self._position_before(ac)
                stagger = timedelta(minutes=int(draw(self.seed, "stagger", ac["_id"], day) * 120))
                t = max(ready, D + timedelta(hours=C.FIRST_DEPARTURE_HOUR) + stagger)
                day_end = D + timedelta(hours=C.LAST_DEPARTURE_HOUR)
                block_today, legs = 0.0, 0
                while True:
                    t = self._after_maintenance(ac["_id"], t)
                    std = round_up_5(t)
                    if std > day_end:
                        break
                    opts = [r for r in self.p.routes_from.get((aid, loc), [])
                            if self.in_range(r["distance_km"], ac["model"])]
                    if not opts:
                        if legs:
                            break
                        dest = self._reposition_target(aid, loc, ac)
                        if not dest:
                            break
                        seq += 1
                        f = self._create(ac, loc, dest, self.p.distance(loc, dest), std, seq,
                                         f"{al['code']} F{seq:02d}", is_ferry=True)
                        self._event("reposition", f"{ac['registration']} repositions {loc} to {dest} (no passengers)",
                                    f, amount=-sum(f["plan"].values()))
                    else:
                        r = pick([(r, r["departures_by_weekday"][wd] + r["departures"] / 14 + 0.5) for r in opts],
                                 draw(self.seed, "route", aid, day, ac["_id"], legs))
                        block = self.block_h(r["distance_km"], ac["model"])
                        if legs and block_today + block > target:
                            break
                        m = self._maintenance_overlap(ac["_id"], std, std + timedelta(hours=block) + self.turnaround(ac["capacity"]))
                        if m:
                            t = m["end"]
                            continue
                        nums = r.get("flight_numbers") or [f"{9000 + seq}"]
                        k = used[r["route"]]
                        used[r["route"]] += 1
                        number = f"{al['code']} {nums[k % len(nums)]}" + ("" if k < len(nums) else chr(64 + k // len(nums)))
                        seq += 1
                        f = self._create(ac, r["origin"], r["destination"], r["distance_km"], std, seq, number)
                    loc = f["destination"]
                    t = f["sta"] + self.turnaround(ac["capacity"])
                    block_today += f["block_h"]
                    legs += 1
        if self.real_life:          # drawn after the schedule: a technical fault is not planned around
            self._draw_live(D)

    # ------------------------------------------------------------------ maintenance
    def _draw_maintenance(self, D):
        day = D.date().isoformat()
        rates = self.p.glob.get("maintenance") or {}
        for ac in sorted(self.aircraft.values(), key=lambda a: a["_id"]):
            if ac["grounded"]:
                continue
            for mtype in sorted(rates):
                p_day = rates[mtype]["per_aircraft_month"] * 12 / 365.25
                if draw(self.seed, "maint", ac["_id"], day, mtype) < p_day:
                    _, ready = self._position_before(ac)
                    start = max(D + timedelta(hours=1), ready)
                    if not self._maintenance_overlap(ac["_id"], start, start + MINUTE):
                        self._add_maintenance(ac, start, mtype)

    def _add_maintenance(self, ac, start, mtype, note=None, hours=None, cost=None):
        rates = self.p.glob.get("maintenance") or {}
        p, base, per_seat, down = C.MAINTENANCE_TYPES.get(mtype, (0, 5000, 10, 12))
        hours = hours if hours is not None else rates.get(mtype, {}).get("downtime_hours", down)
        u = draw(self.seed, "maint_cost", ac["_id"], start.isoformat(), mtype)
        cost = cost if cost is not None else base + per_seat * ac["capacity"] * (0.8 + 0.4 * u)
        m = {"_id": f"M{ac['_id']}-{start:%Y%m%d%H%M}", "aircraft_id": ac["_id"], "airline_id": ac["airline_id"],
             "registration": ac["registration"], "model": ac["model"], "type": mtype, "start": start,
             "end": start + timedelta(hours=hours), "downtime_hours": hours, "day": start.date().isoformat(),
             "cost": round(cost, 2), "note": note, "started": False}
        self.maint.append(m)
        self.dirty_maint.add(m["_id"])
        self._push(start, PRI_MAINT, "maint", m["_id"])
        return m

    def _on_maint(self, mid):
        m = next((x for x in self.maint if x["_id"] == mid), None)
        if not m or m["started"]:
            return
        m["started"] = True
        self.dirty_maint.add(mid)
        self.dirty_days.add((m["airline_id"], m["day"]))
        self._event("maintenance", f"{m['registration']} in {m['type']} for {m['downtime_hours']:.0f} h"
                    + (f" ({m['note']})" if m["note"] else ""), amount=-m["cost"], airline_id=m["airline_id"])

    # ------------------------------------------------------------------ real-life mode
    def _draw_live(self, D, from_time=None):
        """Draw today's random conditions (deterministic per seed + date). With from_time
        (mode switched on mid-day) only disruptions that are still ahead are added."""
        day = D.date().isoformat()
        t0 = from_time or D
        L = self.live
        g = lambda *k: draw(self.seed, "live", day, *k)  # noqa: E731
        z = lambda u: _N.inv_cdf(min(max(u, 1e-6), 1 - 1e-6))  # noqa: E731
        L["events"] = [e for e in L["events"] if e["end"] > D - timedelta(days=1)]
        have = {e["id"] for e in L["events"]}
        new = []

        if L["day"] != day:                       # daily indices: fuel walk, demand, delay odds
            old_fuel = L["fuel_index"]
            L["fuel_index"] = _clip(old_fuel + C.LIVE_FUEL_REVERSION * (1 - old_fuel) + C.LIVE_FUEL_DAILY_VOL * z(g("fuel")),
                                    *C.LIVE_FUEL_RANGE)
            L["demand_index"] = _clip(C.LIVE_DEMAND_SEASON[D.month] * math.exp(C.LIVE_DEMAND_NOISE * z(g("demand"))), 0.6, 1.4)
            L["delay_index"] = _clip(math.exp(C.LIVE_DELAY_NOISE * z(g("delay"))), 0.5, 2.0)
            L["day"] = day
            p0, p1 = self.scenario["fuel_price"] * old_fuel, self.scenario["fuel_price"] * L["fuel_index"]
            if abs(p1 / p0 - 1) >= 0.02:
                self._event("disruption", f"Fuel price {'up' if p1 > p0 else 'down'} {abs(p1 / p0 - 1):.0%}: {p0:.2f} -> {p1:.2f}/kg")

        def add(kind, key, label, start, end, airports=(), factor=1.0):
            eid = f"{kind}:{day}:{key}"
            if eid in have or end <= t0:
                return
            e = {"id": eid, "kind": kind, "label": label, "airports": list(airports), "factor": round(factor, 3),
                 "start": max(start, t0), "end": end, "announced": False}
            L["events"].append(e)
            new.append(e)

        if g("shock") < C.LIVE_SHOCK_PROB:          # demand surge or slump for a few days
            days = 2 + int(g("shock_len") * 6)
            if g("shock_dir") < 0.5:
                f, label = 1.08 + 0.12 * g("shock_size"), "Demand surge (holiday / event)"
            else:
                f, label = 0.9 - 0.15 * g("shock_size"), "Demand slump (weak bookings)"
            add("demand", "shock", f"{label} {f - 1:+.0%} for {days} days", D, D + timedelta(days=days), factor=f)

        for iata in sorted(self.p.coords):          # bad-weather windows per airport
            lat = abs(self.p.coords[iata]["lat"])
            winter = D.month in (12, 1, 2) and lat > 35
            if g("wx", iata) < C.LIVE_WEATHER_PROB * (C.LIVE_WINTER_FACTOR if winter else 1):
                start = D + timedelta(hours=int(g("wx_start", iata) * 20))
                hours = 3 + int(g("wx_len", iata) * 8)
                kind = "Snow" if winter and lat > 40 else "Thunderstorms" if D.month in (5, 6, 7, 8, 9) else "Fog"
                add("weather", iata, f"{kind} at {iata}", start, start + timedelta(hours=hours), [iata])

        countries = {}
        for iata, c in self.p.coords.items():
            countries.setdefault(c.get("country") or "", []).append(iata)
        for cc in sorted(countries):                # air-traffic-control strike for a day
            if cc and g("atc", cc) < C.LIVE_ATC_PROB:
                add("atc", cc, f"ATC strike in {cc}: delays x{C.LIVE_ATC_DELAY_FACTOR:g}", D + timedelta(hours=5),
                    D + timedelta(hours=23), sorted(countries[cc]), C.LIVE_ATC_DELAY_FACTOR)

        for ac in sorted(self.aircraft.values(), key=lambda a: a["_id"]):   # technical faults
            if ac["grounded"] or g("aog", ac["_id"]) >= C.LIVE_AOG_PROB:
                continue
            start = D + timedelta(hours=4 + int(g("aog_start", ac["_id"]) * 18))
            if start < t0 or self._maintenance_overlap(ac["_id"], start, start + MINUTE):
                continue
            lo, hi = C.LIVE_AOG_HOURS
            hours = lo + int(g("aog_len", ac["_id"]) * (hi - lo))
            cost = C.LIVE_AOG_COST[0] + (C.LIVE_AOG_COST[1] - C.LIVE_AOG_COST[0]) * g("aog_cost", ac["_id"])
            self._add_maintenance(ac, start, "AOG (technical fault)", note="unscheduled", hours=hours, cost=cost)

        for e in new:
            self._push(max(e["start"], self.clock), PRI_MAINT, "live", e["id"])

    def _on_live(self, eid):
        e = next((x for x in self.live["events"] if x["id"] == eid), None)
        if not e or e["announced"] or not self.real_life:
            return
        e["announced"] = True
        until = e["end"].strftime("%H:%M") if e["end"].date() == self.clock.date() else e["end"].strftime("%d %b")
        self._event("disruption", f"{e['label']} until {until}")

    def live_status(self):
        on = self.real_life
        now = self.clock
        active = [e for e in self.live["events"] if e["start"] <= now < e["end"]] if on else []
        upcoming = sorted((e for e in self.live["events"] if now < e["start"] and e["start"].date() == now.date()),
                          key=lambda e: e["start"]) if on else []
        aog = [m for m in self.maint if m["type"].startswith("AOG") and m["start"] <= now < m["end"]] if on else []
        fmt = lambda e: {"kind": e["kind"], "label": e["label"], "start": e["start"].strftime("%Y-%m-%dT%H:%M:%S"),  # noqa: E731
                         "end": e["end"].strftime("%Y-%m-%dT%H:%M:%S")}
        return {"enabled": on, "fuel_price": round(self.fuel_price_now(), 3), "demand": round(self.demand_now(), 3),
                "delay_index": round(self.live["delay_index"], 2) if on else 1.0,
                "active": [fmt(e) for e in active] + [{"kind": "aog", "label": f"{m['registration']} technical fault",
                                                        "start": m["start"].strftime("%Y-%m-%dT%H:%M:%S"),
                                                        "end": m["end"].strftime("%Y-%m-%dT%H:%M:%S")} for m in aog],
                "upcoming": [fmt(e) for e in upcoming[:5]]}

    # ------------------------------------------------------------------ flight life cycle
    def _status(self, f, status, kind="status", text=None, amount=None):
        f["status"] = status
        self._dirty(f)
        self._event(kind, text or f"{f['flight_number']} {f['origin']}-{f['destination']} {status.lower()}", f, amount)

    def _availability(self, ac, f):
        if ac["grounded"]:
            return "grounded", None
        end = f["std"] + timedelta(hours=f["block_h"]) + self.turnaround(ac["capacity"])
        m = self._maintenance_overlap(ac["_id"], f["std"], end)
        if m:
            return "maintenance", m["end"]
        return None, None

    def _find_swap(self, f):
        for c in sorted(self.aircraft.values(), key=lambda a: a["_id"]):
            if c["airline_id"] != f["airline_id"] or c["_id"] == f["aircraft_id"] or c["grounded"]:
                continue
            if not self.in_range(f["distance_km"], c["model"]):
                continue
            if any(self.flights[x]["status"] not in DONE for x in self.legs[c["_id"]]):
                continue
            loc, ready = self._position_before(c)
            if loc != f["origin"] or ready > f["std"] + timedelta(minutes=C.MAX_WAIT_FOR_AIRCRAFT_MIN):
                continue
            end = f["std"] + timedelta(hours=f["block_h"]) + self.turnaround(c["capacity"])
            if self._maintenance_overlap(c["_id"], max(self.clock, f["std"]), end):
                continue
            return c
        return None

    def _swap(self, f, old, new):
        moved = [x for x in self.legs[old["_id"]] if x == f["_id"] or
                 (self.flights[x]["std"] > f["std"] and self.flights[x]["status"] == "Scheduled")]
        for fid in moved:
            g = self.flights[fid]
            self.legs[old["_id"]].remove(fid)
            self.legs[new["_id"]].append(fid)
            g.update(aircraft_id=new["_id"], registration=new["registration"], model=new["model"], capacity=new["capacity"])
            self._project(g)
            self._dirty(g)
        self.legs[new["_id"]].sort(key=lambda x: self.flights[x]["std"])
        self._event("swap", f"Tail swap: {new['registration']} replaces {old['registration']} on {len(moved)} flight(s)", f)

    def _on_board(self, fid):
        f = self.flights[fid]
        if f["status"] in DONE + AIRBORNE:
            return
        if f["delay_checked"]:
            return self._status(f, "Boarding")
        f["delay_checked"] = True
        ac = self.aircraft[f["aircraft_id"]]
        loc, ready = self._position_before(ac, f)
        if loc != f["origin"]:
            return self._cancel(f, "Aircraft out of position (previous leg cancelled)", "operational")
        why, free_at = self._availability(ac, f)
        if why:
            c = self._find_swap(f)
            if c:
                self._swap(f, ac, c)
                ac, why = c, None
                loc, ready = self._position_before(ac, f)
            elif why == "grounded" or free_at - f["std"] > timedelta(minutes=C.MAX_WAIT_FOR_AIRCRAFT_MIN):
                return self._cancel(f, f"No aircraft available ({why})", "maintenance")
        weather = self.weather_at(f["origin"])
        if weather and not f["is_ferry"] and draw(self.seed, f["_id"], "wx_cancel") < C.WEATHER_CANCEL_PROBABILITY:
            return self._cancel(f, "Weather", "weather")
        r = self.route_index.get((f["airline_id"], f["origin"], f["destination"]), {})
        ap = self.p.airports.get(f["origin"], {})
        g = self.p.glob
        prob = r.get("delay_prob", g["delay_prob"]) * self.delay_mult_at(f["origin"])
        prob = min(0.95, prob * (C.WEATHER_DELAY_MULTIPLIER if weather else 1.0))
        own, reason = 0.0, None
        if draw(self.seed, f["_id"], "delay") < prob:
            own = quantile(ap.get("delay_minutes_q") or g["delay_minutes_q"], draw(self.seed, f["_id"], "minutes"))
            if weather:
                own, reason = own * C.WEATHER_MINUTES_MULTIPLIER, "Weather"
            else:
                reasons = ap.get("delay_reasons") or g["delay_reasons"]
                reason = pick(sorted(reasons.items()), draw(self.seed, f["_id"], "reason"))
        etd = f["std"] + timedelta(minutes=own)
        f["delay_propagated"] = ready > etd       # knock-on delay from the inbound aircraft
        if ready > etd:
            etd, reason = ready, "Late inbound aircraft"
        if why == "maintenance" and free_at > etd:
            etd, reason = free_at, "Aircraft unavailable (maintenance)"
        if etd.second or etd.microsecond:          # whole minutes, never earlier than ready
            etd = etd.replace(second=0, microsecond=0) + MINUTE
        delay = (etd - f["std"]).total_seconds() / 60
        if delay > C.CANCEL_AFTER_DELAY_MIN:
            return self._cancel(f, f"Excessive delay ({delay / 60:.1f} h, {reason})", "operational")
        f["etd"], f["eta"] = etd, etd + timedelta(hours=f["block_h"])
        f["delay_minutes"], f["delay_reason"] = int(round(delay)), (reason if delay >= 1 else None)
        self._project(f)
        if delay >= C.DELAYED_THRESHOLD_MIN:
            self._status(f, "Delayed", "delay", f"{f['flight_number']} {f['origin']}-{f['destination']} delayed "
                         f"{_dur(delay)} ({reason})", amount=-f["delay_cost_projected"])
            board = etd - timedelta(minutes=C.BOARDING_LEAD_MIN)
            if board > self.clock:
                self._push(board, PRI_FLIGHT, "board", fid)
            else:
                self._status(f, "Boarding")
        else:
            self._status(f, "Boarding")
        self._push(etd, PRI_FLIGHT, "depart", fid)
        self._check_loss(f)

    def _on_depart(self, fid):
        f = self.flights[fid]
        if f["status"] in DONE + AIRBORNE or f["etd"] > self.clock:
            return
        if self.aircraft[f["aircraft_id"]]["grounded"]:
            return self._cancel(f, "No aircraft available (grounded)", "maintenance")
        f["fuel_price"] = self.fuel_price_now()
        self._project(f)                       # final passenger count at today's demand
        f["atd"] = self.clock
        f["revenue"] = round(f["revenue_expected"], 2)
        extra, comp = self._delay_costs(f, f["delay_minutes"], f["fuel_price"], f["pax"])
        f["cost"].update(airport=f["plan"]["airport"], delay=round(extra, 2), compensation=round(comp, 2))
        self._status(f, "Departed", text=f"{f['flight_number']} departed {f['origin']}"
                     + (f" with {f['pax']} pax" if not f["is_ferry"] else " (ferry)"),
                     amount=f["revenue"] if not f["is_ferry"] else None)
        air = self.clock + timedelta(minutes=C.TAXI_OUT_MIN)
        if air < f["eta"]:
            self._push(air, PRI_FLIGHT, "air", fid)
        self._push(f["eta"], PRI_FLIGHT, "land", fid)
        self._check_loss(f)

    def _on_air(self, fid):
        f = self.flights[fid]
        if f["status"] == "Departed":
            self._status(f, "In Flight")

    def _on_land(self, fid):
        f = self.flights[fid]
        if f["status"] not in AIRBORNE:
            return
        for k in ("fuel", "crew", "overhead"):
            f["cost"][k] = f["plan"][k]
        f["ata"] = self.clock
        ac = self.aircraft[f["aircraft_id"]]
        ac["location"] = f["destination"]
        self.dirty_aircraft.add(ac["_id"])
        profit = f["revenue"] - sum(f["cost"].values())
        self._status(f, "Landed", text=f"{f['flight_number']} landed {f['destination']}", amount=round(profit, 2))
        self._check_loss(f)

    def _cancel(self, f, reason, category):
        self._project(f)
        f["revenue_lost"] = round(f["revenue_expected"], 2)
        f["revenue"] = 0.0
        f["cost"] = {"fuel": 0.0, "crew": f["plan"]["crew"], "airport": 0.0, "overhead": f["plan"]["overhead"],
                     "delay": 0.0, "compensation": round(f["pax"] * C.CANCEL_COMPENSATION_PER_PAX
                                                         * C.COMPENSATION_CLAIM_RATE, 2)}
        f["cancel_reason"], f["cancel_category"] = reason, category
        impact = -(f["revenue_lost"] + sum(f["cost"].values()))
        self._status(f, "Cancelled", "cancel", f"{f['flight_number']} {f['origin']}-{f['destination']} cancelled: {reason}",
                     amount=impact)

    def _check_loss(self, f):
        if f["loss_flagged"] or f["is_ferry"] or f["status"] == "Cancelled":
            return
        profit = (f["revenue"] - sum(f["cost"].values())) if f["status"] == "Landed" else f["profit_projected"]
        if profit < 0:
            f["loss_flagged"] = True
            self._dirty(f)
            why = []
            if f["break_even_lf"] and f["load_factor"] < f["break_even_lf"]:
                why.append(f"load factor {f['load_factor']:.0%} < break-even {f['break_even_lf']:.0%}")
            if f["delay_minutes"] >= C.DELAYED_THRESHOLD_MIN:
                why.append(f"delay {_dur(f['delay_minutes'])}")
            self._event("loss", f"{f['flight_number']} {f['origin']}-{f['destination']} is loss-making"
                        + (f" ({', '.join(why)})" if why else ""), f, amount=round(profit, 2))

    # ------------------------------------------------------------------ P&L
    def day_totals(self, day, airline_id=None, now=None):
        now = now or self.clock
        cost = dict.fromkeys(COST_KEYS + ("maintenance", "reposition"), 0.0)
        t = {"revenue": 0.0, "pax": 0, "seats": 0, "flights": 0, "departed": 0, "landed": 0, "cancelled": 0,
             "delayed": 0, "in_air": 0, "revenue_lost": 0.0}
        for fid in self.by_day.get(day, ()):
            f = self.flights[fid]
            if airline_id is not None and f["airline_id"] != airline_id:
                continue
            rev, c = self.money_at(f, now)
            t["flights"] += 1
            if f["is_ferry"]:
                cost["reposition"] += sum(c.values())
            else:
                for k, v in c.items():
                    cost[k] += v
            t["revenue"] += rev
            st = f["status"]
            if st in AIRBORNE + ("Landed",):
                t["departed"] += 1
                if not f["is_ferry"]:
                    t["pax"] += f["pax"]
                    t["seats"] += f["capacity"]
            t["landed"] += st == "Landed"
            t["in_air"] += st in AIRBORNE
            if st == "Cancelled":
                t["cancelled"] += 1
                t["revenue_lost"] += f["revenue_lost"]
            t["delayed"] += f["delay_checked"] and f["delay_minutes"] >= C.DELAYED_THRESHOLD_MIN and st != "Cancelled"
        for m in self.maint:
            if m["day"] == day and m["start"] <= now and (airline_id is None or m["airline_id"] == airline_id):
                cost["maintenance"] += m["cost"]
        t["cost"] = {k: round(v, 2) for k, v in cost.items()}
        t["cost_total"] = round(sum(cost.values()), 2)
        t["revenue"] = round(t["revenue"], 2)
        t["revenue_lost"] = round(t["revenue_lost"], 2)
        t["profit"] = round(t["revenue"] - t["cost_total"], 2)
        t["load_factor"] = round(t["pax"] / t["seats"], 4) if t["seats"] else None
        return t

    def _on_hour(self, ref):
        day, h = ref.split("|")
        for aid in sorted(self.p.airlines):
            t = self.day_totals(day, aid)
            self.hourly[(aid, day)].append({"h": int(h), "revenue": t["revenue"], "cost": t["cost_total"],
                                            "profit": t["profit"], "pax": t["pax"]})
            self.dirty_days.add((aid, day))

    def daily_doc(self, airline_id, day):
        t = self.day_totals(day, airline_id)
        d = datetime.fromisoformat(day)
        open_ = any(self.flights[x]["status"] not in DONE for x in self.by_day.get(day, ())
                    if self.flights[x]["airline_id"] == airline_id)
        return {"_id": f"{airline_id}:{day}", "airline_id": airline_id,
                "airline": self.p.airlines[airline_id]["airline"], "day": day, "day_index": self.day_index(day),
                "weekday": d.strftime("%a"), "closed": (not open_) and self.clock >= d + timedelta(days=1),
                **t, "hourly": self.hourly.get((airline_id, day), []), "is_estimate": True}

    # ------------------------------------------------------------------ scenario
    def set_scenario(self, changes):
        s = self.scenario
        labels = {"demand": ("Demand", lambda v: f"{v:.0%}"), "delay_multiplier": ("Delay probability", lambda v: f"{v:.1f}x"),
                  "fuel_price": ("Fuel price", lambda v: f"{v:.2f}/kg")}
        for k, (name, fmt) in labels.items():
            if k in changes and changes[k] is not None and float(changes[k]) != s[k]:
                old, s[k] = s[k], float(changes[k])
                self._event("scenario", f"Scenario: {name} {fmt(old)} -> {fmt(s[k])}")
        if changes.get("bad_weather") is not None:
            w = {"enabled": bool(changes["bad_weather"].get("enabled")),
                 "airports": sorted(set(changes["bad_weather"].get("airports") or []))}
            if w != s["bad_weather"]:
                s["bad_weather"] = w
                self._event("scenario", "Scenario: bad weather at " + ", ".join(w["airports"])
                            if w["enabled"] and w["airports"] else "Scenario: bad weather cleared")
        if changes.get("grounded_aircraft") is not None:
            new = sorted({int(x) for x in changes["grounded_aircraft"]})
            for ac in self.aircraft.values():
                g = ac["_id"] in new
                if g != ac["grounded"]:
                    ac["grounded"] = g
                    self.dirty_aircraft.add(ac["_id"])
                    self._event("scenario", f"Scenario: {ac['registration']} {'grounded' if g else 'returned to service'}",
                                airline_id=ac["airline_id"])
            s["grounded_aircraft"] = new
        if changes.get("real_life") is not None and bool(changes["real_life"]) != self.real_life:
            s["real_life"] = bool(changes["real_life"])
            if s["real_life"]:
                self._event("scenario", "Real-life mode on: weather, strikes, demand, fuel price and technical faults "
                                        "now change randomly")
                self._draw_live(self.clock.replace(hour=0, minute=0, second=0, microsecond=0), from_time=self.clock)
            else:
                self._event("scenario", "Real-life mode off: conditions are fixed again")


def _dur(minutes):
    m = int(round(minutes))
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"
