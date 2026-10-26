"""Presentation charts from the pipeline's CSV results (not part of the pipeline).

  python docs/make_charts.py          # reads output/1m and output/100k-dirty, writes docs/charts/*.png
"""
import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "docs", "charts")
os.makedirs(OUT, exist_ok=True)

# validated reference palette (light surface); categorical slots used in fixed order
SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
RED = "#e34948"
CABIN_COLORS = {"First": BLUE, "Business": ORANGE, "Premium Economy": AQUA, "Economy": YELLOW}

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": INK2,
    "axes.edgecolor": GRID, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "font.size": 11,
})
money = FuncFormatter(lambda v, _: f"{v / 1e6:,.1f}M" if abs(v) >= 1e6 else f"{v:,.0f}")


def rows(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def finish(fig, ax, name, title, sub, source):
    ax.set_title(title, loc="left", fontsize=14, fontweight="bold", color=INK, pad=26)
    ax.text(0, 1.03, sub, transform=ax.transAxes, fontsize=10, color=INK2, va="bottom")
    fig.text(0.01, 0.01, source, fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(os.path.join(OUT, name), dpi=160)
    plt.close(fig)
    print("wrote", name)


def hbar(ax, labels, values, colors, fmt):
    y = range(len(labels))
    ax.barh(list(y), values, color=colors, height=0.62)
    ax.set_yticks(list(y), labels); ax.invert_yaxis(); ax.grid(axis="y", visible=False)
    for i, v in zip(y, values):
        ax.text(v, i, " " + fmt(v) if v >= 0 else fmt(v) + " ", va="center",
                ha="left" if v >= 0 else "right", fontsize=9.5, color=INK2)


# 1 ---- monthly revenue trend
m = rows("output/1m/monthly_trend.csv")
x = [r["year_month"] for r in m]
fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(x, [float(r["fare_revenue"]) for r in m], color=BLUE, lw=2, label="Monthly fare revenue")
ax.plot(x, [float(r["revenue_3m_moving_avg"]) for r in m], color=ORANGE, lw=2, label="3-month moving average")
ax.set_xticks([i for i, v in enumerate(x) if v.endswith("-01")], [v[:4] for v in x if v.endswith("-01")])
ax.yaxis.set_major_formatter(money); ax.set_ylabel("Fare revenue (dataset currency)")
ax.legend(frameon=False, loc="upper left")
finish(fig, ax, "monthly_revenue_trend.png", "Yearly fare revenue grew about 2.3x from 2021 to 2025",
       "Real fares from the source data, summed per departure month", "Source: output/1m/monthly_trend.csv (real fares, not estimates)")

# 2 ---- route profitability top 10 (estimated)
r = sorted(rows("output/1m/route_profitability.csv"), key=lambda d: -float(d["profit_est"]))[:10]
fig, ax = plt.subplots(figsize=(10, 5.2))
hbar(ax, [f'{d["route"]}  ({d["airline"]})' for d in r], [float(d["profit_est"]) for d in r],
     [BLUE] * len(r), lambda v: f"{v / 1e3:,.0f}K")
ax.xaxis.set_major_formatter(money); ax.set_xlabel("Estimated operating profit over 5 years (ESTIMATE)")
finish(fig, ax, "route_profitability_top10.png", "Top 10 routes by estimated operating profit",
       "Fare revenue is real; costs (fuel, crew, fees, overhead) are illustrative estimates",
       "Source: output/1m/route_profitability.csv. profit_est = real fares minus estimated costs.")

# 3 ---- delays by reason
d = rows("output/1m/delays_by_reason.csv")
fig, ax = plt.subplots(figsize=(10, 4.6))
hbar(ax, [x_["delay_reason"] for x_ in d], [int(x_["delays"]) for x_ in d], [BLUE] * len(d),
     lambda v: f"{v:,.0f}")
ax.set_xlabel("Delayed departures (delay of 15 min or more)")
share = {x_["delay_reason"]: float(x_["share"]) for x_ in d}
top = d[0]["delay_reason"]
finish(fig, ax, "delays_by_reason.png", f"{top} causes the most delays ({share[top]:.0%})",
       "Count of departures delayed 15+ minutes, by recorded reason (real data)", "Source: output/1m/delays_by_reason.csv")

# 4 ---- fuel efficiency by model
f = rows("output/1m/fuel_efficiency.csv")
fig, ax = plt.subplots(figsize=(10, 4.8))
hbar(ax, [f'{x_["model_number"]} ({x_["capacity"]} seats)' for x_ in f],
     [float(x_["kg_per_seat_hour_est"]) for x_ in f], [BLUE] * len(f), lambda v: f"{v:.1f}")
ax.set_xlabel("Estimated fuel burn, kg per seat per block hour (ESTIMATE)")
finish(fig, ax, "fuel_efficiency_by_model.png", f"{f[0]['model_number']} burns the least fuel per seat-hour, the small {f[-1]['model_number']} the most",
       "Based on assumed burn rates per model in config.py, not measured fuel data",
       "Source: output/1m/fuel_efficiency.csv (kg/h per model is an illustrative assumption)")

# 5 ---- cabin revenue share
c = rows("output/1m/cabin_fares.csv")
c = sorted(c, key=lambda d_: -float(d_["revenue_share"]))
fig, ax = plt.subplots(figsize=(10, 4.2))
hbar(ax, [x_["cabin"] for x_ in c], [float(x_["revenue_share"]) for x_ in c],
     [CABIN_COLORS[x_["cabin"]] for x_ in c], lambda v: f"{v:.1%}")
seg = {x_["cabin"]: int(x_["segments"]) for x_ in c}; tot = sum(seg.values())
ax.set_xlabel("Share of total fare revenue"); ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
ax.set_xlim(0, max(float(x_["revenue_share"]) for x_ in c) * 1.15)
finish(fig, ax, "cabin_revenue_share.png",
       f"Economy is {seg['Economy'] / tot:.0%} of seats but only {float(c[0]['revenue_share']):.0%} of revenue",
       f"The three premium cabins are {1 - seg['Economy'] / tot:.0%} of seats and earn the rest (real fares)",
       "Source: output/1m/cabin_fares.csv")

# 6 ---- data quality before / after (100K dirty copy)
k = rows("output/100k-dirty/cleaning_vs_answer_key.csv")
dq = json.load(open(os.path.join(ROOT, "output/100k-dirty/run_summary.json")))["data_quality"]
labels = {"missing values": "Missing values\n(fares restored)", "typos / case / spaces": "Typos / case",
          "outliers": "Outliers\n(set to NULL)", "exact duplicate rows": "Exact duplicates",
          "near duplicates": "Near duplicates", "reformatted dates": "Mixed date formats",
          "orphaned keys": "Orphaned rows\n(incl. cascade)"}
fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5), gridspec_kw={"width_ratios": [1.6, 1]})
names = [labels[x_["fault_type"]] for x_ in k]
vals = [int(x_["detected_or_fixed_by_pipeline"]) for x_ in k]
hbar(a1, names, vals, [BLUE] * len(vals), lambda v: f"{v:,.0f}")
a1.set_xlabel("Faults detected and fixed by the pipeline"); a1.set_xlim(0, max(vals) * 1.15)
a2.bar(["Before", "After"], [dq["rows_raw"], dq["rows_clean"]], color=[ORANGE, BLUE], width=0.55)
for i, v in enumerate([dq["rows_raw"], dq["rows_clean"]]):
    a2.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=9.5, color=INK2)
a2.set_ylim(0, dq["rows_raw"] * 1.12); a2.grid(axis="x", visible=False)
a2.set_ylabel("Rows in the 18 loaded tables"); a2.yaxis.set_major_formatter(money)
a2.set_title("Rows before / after", loc="left", fontsize=11, color=INK2)
finish(fig, a1, "data_quality_before_after.png", "Cleaning the 100K dirty copy with Spark",
       f"{dq['unparsed_dates']} dates left unparsed; 248K rows in, {dq['rows_clean']:,} rows out",
       "Source: output/100k-dirty (data_quality_by_table.csv, cleaning_vs_answer_key.csv)")
