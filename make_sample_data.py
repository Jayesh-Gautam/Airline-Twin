"""Offline fallback: generate a small dataset with the SAME tables and columns
as the databasesample.com airline database, so the pipeline can be tested
(or demoed) without internet. Use the real download for the actual project.

  python make_sample_data.py            -> data/sample/  and data/sample-dirty/
"""
import csv
import datetime as dt
import os
import random

import config as C

R = random.Random(C.SEED)
AIRPORTS = [("JFK", "John F. Kennedy International", "New York", 1),
            ("LAX", "Los Angeles International", "Los Angeles", 1),
            ("ORD", "O'Hare International", "Chicago", 1),
            ("LHR", "Heathrow", "London", 2), ("MAN", "Manchester", "Manchester", 2),
            ("FRA", "Frankfurt", "Frankfurt", 3), ("MUC", "Munich", "Munich", 3),
            ("CDG", "Charles de Gaulle", "Paris", 4), ("AMS", "Schiphol", "Amsterdam", 7),
            ("IST", "Istanbul", "Istanbul", 8), ("DXB", "Dubai International", "Dubai", 9),
            ("HND", "Haneda", "Tokyo", 10)]
MODELS = [(189, "Boeing", "737-800"), (180, "Airbus", "A320neo"), (220, "Airbus", "A321neo"),
          (296, "Boeing", "787-9"), (315, "Airbus", "A350-900"), (76, "Embraer", "E175"),
          (396, "Boeing", "777-300ER"), (141, "Airbus", "A220-300")]
CABIN_FARE = {1: (1280, 2544), 2: (592.8, 1248), 3: (243.2, 508.8), 4: (105, 224)}


def build(n_instances=400):
    T = {}
    T["countries"] = [{"id": i + 1, "iso_code": c, "name": n} for i, (c, n) in enumerate(
        [("US", "United States"), ("GB", "United Kingdom"), ("DE", "Germany"), ("FR", "France"),
         ("ES", "Spain"), ("IT", "Italy"), ("NL", "Netherlands"), ("TR", "Turkey"),
         ("AE", "United Arab Emirates"), ("JP", "Japan")])]
    T["cities"] = [{"id": i + 1, "country_id": a[3], "name": a[2]} for i, a in enumerate(AIRPORTS)]
    T["airports"] = [{"id": i + 1, "city_id": i + 1, "iata_code": a[0], "icao_code": "X" + a[0],
                      "name": a[1]} for i, a in enumerate(AIRPORTS)]
    T["airlines"] = [{"id": i + 1, "country_id": c, "iata_code": code, "name": n} for i, (c, code, n) in
                     enumerate([(1, "N7", "Northwind Air"), (1, "B9", "Blue Harbor Airlines"),
                                (2, "C8", "Atlantic Crown"), (3, "R4", "Rhine Sky"),
                                (8, "W6", "Bosphorus Wings"), (10, "P2", "Pacific Lantern")])]
    T["aircraft_models"] = [{"id": i + 1, "capacity": m[0], "manufacturer": m[1], "model_number": m[2]}
                            for i, m in enumerate(MODELS)]
    T["aircrafts"] = [{"id": i + 1, "airline_id": R.randint(1, 6), "model_id": R.randint(1, 8),
                       "registration_number": f"N{R.randint(100, 999)}{chr(65 + i % 26)}{chr(65 + i // 26)}",
                       "status": R.choice(["in_service"] * 9 + ["maintenance"])} for i in range(30)]
    T["cabins"] = [{"id": 1, "class_code": "F", "name": "First"}, {"id": 2, "class_code": "J", "name": "Business"},
                   {"id": 3, "class_code": "W", "name": "Premium Economy"}, {"id": 4, "class_code": "Y", "name": "Economy"}]
    T["promotions"] = [{"id": i + 1, "code": c, "discount_percentage": d, "start_date": "2021-01-01",
                        "end_date": "2025-12-31"} for i, (c, d) in
                       enumerate([("NONE", 0), ("SUMMER10", 10), ("EARLY15", 15), ("STUDENT20", 20)])]
    roles = ["captain", "first_officer", "purser", "flight_attendant"]
    T["crews"] = [{"id": i + 1, "first_name": f"Crew{i}", "last_name": f"Member{i}",
                   "license_number": f"CR-{100000 + i}", "role": roles[i % 4]} for i in range(200)]
    flights = []
    for i in range(60):
        a, b = R.sample(range(1, len(AIRPORTS) + 1), 2)
        flights.append({"id": i + 1, "airline_id": R.randint(1, 6), "departure_airport_id": a,
                        "arrival_airport_id": b, "flight_number": f"{1000 + i}"})
    T["flights"] = flights
    by_airline = {}
    for ac in T["aircrafts"]:
        by_airline.setdefault(ac["airline_id"], []).append(ac)
    cap = {m["id"]: m["capacity"] for m in T["aircraft_models"]}

    fi, fd, fc, bk, tk, tf, pay, ref = [], [], [], [], [], [], [], []
    start = dt.datetime(2021, 1, 1)
    for i in range(n_instances):
        f = R.choice(flights)
        fleet = by_airline.get(f["airline_id"]) or T["aircrafts"]
        ac = R.choice(fleet)
        dep = start + dt.timedelta(minutes=R.randint(0, 5 * 365 * 24 * 60))
        arr = dep + dt.timedelta(minutes=R.randint(60, 600))
        fid = i + 1
        fi.append({"id": fid, "flight_id": f["id"], "aircraft_id": ac["id"], "departure_time": dep,
                   "arrival_time": arr, "status": "arrived"})
        if R.random() < 0.2:
            fd.append({"id": len(fd) + 1, "flight_instance_id": fid,
                       "delay_reason": R.choice(["Weather", "Air traffic control", "Late inbound aircraft",
                                                 "Technical", "Crew"]), "duration_minutes": R.randint(15, 300)})
        used = set()   # a crew member is assigned at most once per departure, as in the real data
        for role in ["captain", "first_officer", "purser", "cabin", "cabin"]:
            pool = {"captain": 0, "first_officer": 1, "purser": 2, "cabin": 3}[role]
            cid = R.randrange(pool, 200, 4) + 1
            while cid in used:
                cid = R.randrange(pool, 200, 4) + 1
            used.add(cid)
            fc.append({"id": len(fc) + 1, "crew_id": cid,
                       "flight_instance_id": fid, "role_assigned": role})
        seats = cap[ac["model_id"]]
        npax = int(seats * R.uniform(0.55, 0.95))
        for s in range(npax):
            bid = len(bk) + 1
            bdate = dep - dt.timedelta(days=R.randint(1, 120), minutes=R.randint(0, 1440))
            promo = R.choice([1, 1, 1, 2, 3, 4])
            bk.append({"id": bid, "user_id": R.randint(1, 500), "promotion_id": promo,
                       "booking_reference": f"B{bid:07d}", "booking_date": bdate, "status": "confirmed"})
            cabin = R.choices([1, 2, 3, 4], [3, 10, 12, 75])[0]
            lo, hi = CABIN_FARE[cabin]
            fare = round(R.uniform(lo, hi), 2)
            tid = len(tk) + 1
            tk.append({"id": tid, "booking_id": bid, "passenger_id": R.randint(1, 5000),
                       "ticket_number": f"016-{tid:010d}", "total_price": fare})
            tf.append({"id": len(tf) + 1, "ticket_id": tid, "flight_instance_id": fid,
                       "seat_id": s + 1, "cabin_id": cabin, "fare": fare})
            disc = [0, 10, 15, 20][promo - 1]
            pdate = bdate + dt.timedelta(minutes=R.randint(1, 15))
            pid = len(pay) + 1
            amount = round(fare * (100 - disc) / 100, 2)
            pay.append({"id": pid, "booking_id": bid, "amount": amount, "payment_date": pdate,
                        "payment_method": R.choice(["card"] * 6 + ["paypal", "apple_pay", "bank_transfer"]),
                        "transaction_status": "succeeded"})
            if R.random() < 0.02:
                ref.append({"id": len(ref) + 1, "payment_id": pid, "amount": round(amount * R.uniform(0.3, 1), 2),
                            "refund_date": pdate + dt.timedelta(days=R.randint(1, 30)),
                            "reason": R.choice(["Schedule change", "Cancelled by customer",
                                                "Duplicate booking", "Medical", "Downgrade"])})
    T.update(flight_instances=fi, flight_delays=fd, flight_crews=fc, bookings=bk, tickets=tk,
             ticket_flights=tf, payments=pay, refunds=ref)
    for rows in T.values():
        for r in rows:
            for k, v in r.items():
                if isinstance(v, dt.datetime):
                    r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return T


def make_dirty(T, rate=0.03):
    """Plant the same kinds of fault the real dirty copy has."""
    D = {}
    for name, rows in T.items():
        rows = [dict(r) for r in rows]
        for r in rows:
            for k in list(r):
                if k == "id":
                    continue
                v, x = r[k], R.random()
                if k.endswith("_id") and isinstance(v, int):    # keys: only orphans, like the real copy
                    if x < 0.005:
                        r[k] = v + 10_000_000
                    continue
                if x < rate:
                    r[k] = ""                                   # missing value
                elif x < rate * 2 and isinstance(v, str) and not v[:1].isdigit() and len(v) > 3:
                    i = R.randrange(len(v) - 1)                 # typo / case / spaces
                    r[k] = R.choice([v[:i] + v[i + 1] + v[i] + v[i + 2:], v.upper(), f"  {v} "])
                elif x < rate * 2.2 and isinstance(v, float):
                    r[k] = R.choice([round(v * 10, 2), -v])     # outlier
                elif x < rate * 2.5 and isinstance(v, str) and len(v) == 19 and v[4] == "-":
                    d = dt.datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
                    r[k] = R.choice([d.strftime("%d/%m/%Y %H:%M"), d.strftime("%Y/%m/%d")])
        extra = []
        if len(rows) >= 20:
            for r in R.sample(rows, max(1, len(rows) // 100)):
                extra.append(dict(r))                          # exact duplicate
            for r in R.sample(rows, max(1, len(rows) // 100)):
                nd = dict(r)                                   # near duplicate (same id)
                k = R.choice([c for c in nd if not c.endswith("id")])
                nd[k] = ""
                extra.append(nd)
        D[name] = rows + extra
        R.shuffle(D[name])
    return D


def write(T, folder):
    os.makedirs(folder, exist_ok=True)
    for name, rows in T.items():
        with open(os.path.join(folder, f"{name}.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["id"])
            w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    T = build()
    write(T, os.path.join(C.DATA_ROOT, "sample"))
    write(make_dirty(T), os.path.join(C.DATA_ROOT, "sample-dirty"))
    print("ticket_flights rows:", len(T["ticket_flights"]),
          "| total rows:", sum(len(v) for v in T.values()))
    print("Wrote data/sample/ and data/sample-dirty/")
