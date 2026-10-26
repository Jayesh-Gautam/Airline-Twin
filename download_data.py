"""Download and extract the airline sample database (CC0) from databasesample.com.

  python download_data.py 1m            -> data/1m/          (2.9M rows, ~47 MB zip)
  python download_data.py 100k --dirty  -> data/100k-dirty/  (306K rows with planted faults)
  python download_data.py 1k            -> data/1k/          (19K rows, for a quick test)
"""
import argparse
import os
import sys
import urllib.request
import zipfile

import config as C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("size", choices=list(C.DOWNLOADS))
    ap.add_argument("--dirty", action="store_true", help="the copy with planted data faults")
    a = ap.parse_args()
    variant = "dirty" if a.dirty else "clean"
    if variant not in C.DOWNLOADS[a.size]:
        sys.exit(f"No dirty copy is published for size {a.size}; use 1k or 100k.")
    name = C.DOWNLOADS[a.size][variant]
    url = f"{C.BASE_URL}/{a.size}/{name}"
    dest = os.path.join(C.DATA_ROOT, a.size + ("-dirty" if a.dirty else ""))
    os.makedirs(dest, exist_ok=True)
    zpath = os.path.join(dest, name)
    print(f"Downloading {url}")

    def progress(blocks, bsize, total):
        if total > 0:
            print(f"\r  {min(blocks * bsize, total) / 1e6:6.1f} / {total / 1e6:.1f} MB", end="")
    urllib.request.urlretrieve(url, zpath, progress)
    print("\nExtracting...")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(dest)
    os.remove(zpath)
    csvs = [f for _, _, fs in os.walk(dest) for f in fs if f.endswith(".csv")]
    print(f"Done: {len(csvs)} CSV files in {dest}/")


if __name__ == "__main__":
    main()
