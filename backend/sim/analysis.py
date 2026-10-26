"""Why did a day make (or lose) money?

The day's operating profit is split into parts that add up exactly:

  profit = contribution of flights that covered their normal costs   (+)
         - shortfall of flights whose revenue did not cover them      (low load factor)
         - delay costs (holding fuel, crew overtime, compensation)
         - cancellation costs (compensation + fixed crew/aircraft cost)
         - repositioning (ferry) flights
         - maintenance

Revenue lost to cancellations is not in the P&L (it was never booked) but is
reported next to the cancellation cost because it is the bigger economic hit.
"""
import config as C


def _flight_row(f, impact, detail):
    return {"id": f["_id"], "flight_number": f["flight_number"], "route": f["route"], "registration": f["registration"],
            "impact": round(impact, 2), "detail": detail, "load_factor": f.get("load_factor"),
            "break_even_lf": f.get("break_even_lf"), "delay_minutes": f.get("delay_minutes", 0)}


def explain_day(eng, airline_id, day):
    now = eng.clock
    flights = [eng.flights[i] for i in eng.by_day.get(day, ()) if airline_id is None or eng.flights[i]["airline_id"] == airline_id]
    good, low, delays, cancel_ops, cancel_wx, cancel_mx, ferry = [], [], [], [], [], [], []
    for f in flights:
        rev, c = eng.money_at(f, now)
        if f["status"] == "Cancelled":
            cost = sum(c.values())
            row = _flight_row(f, -(cost + f["revenue_lost"]), f"{f['cancel_reason']}; {f['pax']} pax refunded")
            row["cost"], row["revenue_lost"] = round(cost, 2), f["revenue_lost"]
            {"weather": cancel_wx, "maintenance": cancel_mx}.get(f["cancel_category"], cancel_ops).append(row)
            continue
        if f["is_ferry"]:
            ferry.append(_flight_row(f, -sum(c.values()), f"Repositioning {f['route']} without passengers"))
            continue
        if f["status"] not in ("Departed", "In Flight", "Landed"):
            continue
        normal = c["fuel"] + c["crew"] + c["airport"] + c["overhead"]
        margin = rev - normal
        if margin >= 0:
            good.append(margin)
        else:
            low.append(_flight_row(f, margin, f"load factor {f['load_factor']:.0%} vs break-even {f['break_even_lf']:.0%}"
                                   if f.get("break_even_lf") else "revenue below cost"))
        dc = c["delay"] + c["compensation"]
        if dc > 0:
            comp = " incl. passenger compensation" if c["compensation"] else ""
            delays.append(_flight_row(f, -dc, f"{f['delay_minutes']} min late ({f['delay_reason']}){comp}"))
    maint = [m for m in eng.maint if m["day"] == day and m["start"] <= now
             and (airline_id is None or m["airline_id"] == airline_id)]

    def cause(key, label, rows, extra=None):
        impact = sum(r["impact"] for r in rows)
        return {"key": key, "label": label, "impact": round(impact, 2), "count": len(rows),
                "flights": sorted(rows, key=lambda r: r["impact"]), **(extra or {})}

    def cancel_cause(key, label, rows):
        return cause(key, label, rows, {"cost": round(sum(r["cost"] for r in rows), 2),
                                        "revenue_lost": round(sum(r["revenue_lost"] for r in rows), 2)})

    causes = [
        cause("low_load", f"Low load factor on {len(low)} flight{'s' * (len(low) != 1)}", low),
        cause("delays", f"Delays on {len(delays)} flight{'s' * (len(delays) != 1)}", delays),
        cancel_cause("cancel_weather", "Weather cancellations", cancel_wx),
        cancel_cause("cancel_ops", "Operational cancellations", cancel_ops),
        cancel_cause("cancel_maintenance", "Cancellations: no aircraft (maintenance/grounded)", cancel_mx),
        cause("reposition", "Repositioning flights", ferry),
        {"key": "maintenance", "label": f"Maintenance ({len(maint)} event{'s' * (len(maint) != 1)})",
         "impact": round(-sum(m["cost"] for m in maint), 2), "count": len(maint),
         "flights": [{"id": m["_id"], "flight_number": m["registration"], "route": m["type"],
                      "impact": -m["cost"], "detail": f"{m['type']}, {m['downtime_hours']:.0f} h downtime"} for m in maint]},
    ]
    causes = sorted((c for c in causes if c["count"]), key=lambda c: c["impact"])
    tot = eng.day_totals(day, airline_id)
    explained = sum(good) + sum(c["impact"] + c.get("revenue_lost", 0) for c in causes)
    return {"day": day, "profit": tot["profit"], "is_loss": tot["profit"] < 0,
            "profitable_contribution": round(sum(good), 2), "causes": causes,
            "reconciliation_gap": round(tot["profit"] - explained, 2),
            "note": "Cancellation impact = cost + revenue lost; revenue lost is not part of the day's P&L."}


def route_stats(eng, airline_id=None):
    """Simulated route economics over all simulated days so far."""
    acc = {}
    for f in eng.flights.values():
        if f["is_ferry"] or (airline_id is not None and f["airline_id"] != airline_id):
            continue
        r = acc.setdefault((f["airline_id"], f["route"]), {
            "airline_id": f["airline_id"], "airline": f["airline"], "route": f["route"], "origin": f["origin"],
            "destination": f["destination"], "distance_km": f["distance_km"], "flights": 0, "cancelled": 0,
            "delayed": 0, "pax": 0, "seats": 0, "revenue": 0.0, "cost": 0.0, "be": []})
        rev, c = eng.money_at(f, eng.clock)
        if f["status"] == "Cancelled":
            r["cancelled"] += 1
        elif f["status"] in ("Departed", "In Flight", "Landed"):
            r["flights"] += 1
            r["pax"] += f["pax"]
            r["seats"] += f["capacity"]
            r["delayed"] += f["delay_minutes"] >= C.DELAYED_THRESHOLD_MIN
        else:
            continue
        r["revenue"] += rev
        r["cost"] += sum(c.values())
        if f.get("break_even_lf"):
            r["be"].append(f["break_even_lf"])
    out = []
    for r in acc.values():
        be = r.pop("be")
        r["load_factor"] = round(r["pax"] / r["seats"], 4) if r["seats"] else None
        r["break_even_lf"] = round(sum(be) / len(be), 4) if be else None
        r["profit"] = round(r["revenue"] - r["cost"], 2)
        r["margin"] = round(r["profit"] / r["revenue"], 4) if r["revenue"] else None
        r["revenue"], r["cost"] = round(r["revenue"], 2), round(r["cost"], 2)
        out.append(r)
    return sorted(out, key=lambda r: -r["profit"])
