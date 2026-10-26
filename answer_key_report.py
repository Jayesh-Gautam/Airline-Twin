"""Compare the faults planted in the 100K dirty copy (the dataset page's answer
key) with what our pipeline detected and fixed.

  python run_pipeline.py --data data/100k-dirty --db airline_dirty
  python answer_key_report.py                     -> output/100k-dirty/cleaning_vs_answer_key.csv

The answer key counts faults over all 32 tables; the pipeline loads 18. So the
"in scope" column re-measures each fault type directly on the raw CSVs of the
18 loaded tables, and that is the fair figure to compare against.
"""
import argparse
import csv
import glob
import json
import os
import re

from pipeline.clean import DATE_FORMATS, SPECS

PLANTED = {"missing": 19802, "typos": 7377, "outliers": 1214, "duplicate_rows": 2977,
           "near_duplicates": 1843, "reformatted_dates": 1923, "orphaned_keys": 3643}
STD_TS = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def read(data, t):
    """Rows of one raw CSV as lists of strings (header first)."""
    hits = glob.glob(os.path.join(data, "**", f"{t}.csv"), recursive=True)
    with open(hits[0], encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


def _int_key(v):
    try:
        return str(int(float(v)))
    except ValueError:
        return None


def measure(data):
    raw = {t: read(data, t) for t in SPECS}
    ids = {t: {r[rows[0].index("id")] for r in rows[1:]} for t, rows in raw.items()}
    m = dict.fromkeys(["missing", "typos", "duplicate_rows", "reformatted_dates", "orphaned_keys"], 0)
    for t, spec in SPECS.items():
        header, body = raw[t][0], raw[t][1:]
        col = {c: header.index(c) for c in header}
        values = lambda c: (r[col[c]].strip() for r in body)  # noqa: E731
        m["missing"] += sum(1 for c in spec["cols"] if c in col for v in values(c) if v == "")
        seen, dup = set(), 0
        for r in body:
            key = tuple(v for c, v in zip(header, r) if c != "id")
            dup += key in seen
            seen.add(key)
        m["duplicate_rows"] += dup
        for c, typ in spec["cols"].items():
            if typ == "ts":
                m["reformatted_dates"] += sum(1 for v in values(c) if v and not STD_TS.match(v))
        for c, allowed in spec.get("categorical", {}).items():
            m["typos"] += sum(1 for v in values(c) if v and v not in allowed)
        for c in spec.get("lower", []):
            m["typos"] += sum(1 for v in values(c) if v and v != v.lower())
        for c, parent in spec.get("fks", []) + spec.get("soft_fks", []):
            keys = (_int_key(v) for v in values(c) if v)
            m["orphaned_keys"] += sum(1 for k in keys if k is not None and k not in ids[parent])
    return m


def table_totals(path):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {k: sum(int(r[k]) for r in rows) for k in rows[0] if k != "table"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/100k-dirty")
    ap.add_argument("--out", default="output/100k-dirty")
    a = ap.parse_args()
    tot = table_totals(os.path.join(a.out, "data_quality_by_table.csv"))
    rules = json.load(open(os.path.join(a.out, "run_summary.json")))["data_quality"]
    scope = measure(a.data)

    nulls_after = int(tot["null_values_remaining"])
    rows = [
        ("missing values", PLANTED["missing"], scope["missing"], rules["fares_imputed"],
         "blank cells in the 18 loaded tables; pipeline figure = fares restored (the only column that is imputed)",
         f"also recomputed from other columns: {rules['payments_repaired']:,} payments (blank or outlier) and "
         f"{rules['ticket_prices_recomputed']:,} ticket prices; rows with a blank required key are dropped. "
         f"The rest cannot be recovered (names, license numbers, optional links), so {nulls_after:,} NULLs remain"),
        ("typos / case / spaces", PLANTED["typos"], scope["typos"], int(tot["category_values_repaired"]),
         "categorical values outside the allowed set, plus status columns with wrong case",
         "Levenshtein repair covers only the 10 categorical columns we validate (free-text names and codes are "
         "not repaired); wrong-case status values are lower-cased but not counted in the pipeline figure"),
        ("outliers", PLANTED["outliers"], "n/a", int(tot["outliers_nulled"]),
         "no independent baseline (answer key counts all numeric columns)",
         "negatives and values above Q3+3*IQR set to NULL, then repaired by business rules"),
        ("exact duplicate rows", PLANTED["duplicate_rows"], scope["duplicate_rows"], int(tot["exact_duplicates"]),
         "rows identical to another row except the id (duplicates are appended under new ids)",
         "removed, lowest id kept"),
        ("near duplicates", PLANTED["near_duplicates"], "n/a", int(tot["near_duplicates"]),
         "no independent baseline",
         "removed by business key (e.g. ticket_number); only found when the key columns are intact"),
        ("reformatted dates", PLANTED["reformatted_dates"], scope["reformatted_dates"],
         scope["reformatted_dates"] - int(tot["unparsed_dates"]),
         "timestamps not in 'yyyy-MM-dd HH:mm:ss' in the 18 loaded tables",
         f"parsed by {len(DATE_FORMATS)} patterns; {int(tot['unparsed_dates'])} left unparsed"),
        ("orphaned keys", PLANTED["orphaned_keys"], scope["orphaned_keys"],
         int(tot["orphan_rows_removed"]) + int(tot["orphan_keys_nulled"]),
         "foreign-key values with no parent row in the 18 loaded tables",
         f"{int(tot['orphan_rows_removed']):,} child rows removed (cascades: a removed departure also removes its "
         f"tickets, so this exceeds the key count) + {int(tot['orphan_keys_nulled']):,} optional keys set to NULL"),
    ]
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "cleaning_vs_answer_key.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fault_type", "planted_all_32_tables", "in_scope_baseline_18_tables",
                    "detected_or_fixed_by_pipeline", "baseline_definition", "how_handled_and_notes"])
        w.writerows(rows)
    print(f"{'fault':<22}{'planted(32)':>12}{'in-scope(18)':>14}{'pipeline':>10}")
    for r in rows:
        print(f"{r[0]:<22}{r[1]:>12}{r[2]:>14}{r[3]:>10}")
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
