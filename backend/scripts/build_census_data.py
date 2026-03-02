#!/usr/bin/env python3
"""
Download and process the US Census 2010 surname frequency data.
Produces: app/data/census_surnames.pkl

Run once at Docker build time (or locally with `python scripts/build_census_data.py`).
The pickle maps lowercase surname → (pct_white, pct_black, pct_asian, pct_hispanic).
Suppressed Census values ("(S)") are treated as 0 (meaning <0.5% — near-zero representation).

Source: https://www.census.gov/topics/population/genealogy/data/2010_surnames.html
"""
from __future__ import annotations

import csv
import io
import os
import pickle
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://www2.census.gov/topics/genealogy/2010surnames/names.zip"
OUT_PATH = Path(__file__).parent.parent / "app" / "data" / "census_surnames.pkl"


def parse_pct(s: str) -> float:
    """Parse a Census percentage string; treat suppressed '(S)' as 0.0."""
    s = s.strip()
    if not s or s.startswith("("):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def main() -> None:
    if OUT_PATH.exists():
        size_kb = OUT_PATH.stat().st_size // 1024
        print(f"[census] {OUT_PATH} already exists ({size_kb:,} KB) — skipping download.")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"[census] Downloading {URL} …", flush=True)
    zip_data, _ = urllib.request.urlretrieve(URL)

    lookup: dict[str, tuple[float, float, float, float]] = {}
    skipped = 0

    with zipfile.ZipFile(zip_data) as z:
        with z.open("Names_2010Census.csv") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in reader:
                name = row["name"].strip().lower()
                if not name or name.startswith("all other"):
                    continue
                white    = parse_pct(row["pctwhite"])
                black    = parse_pct(row["pctblack"])
                asian    = parse_pct(row["pctapi"])
                hispanic = parse_pct(row["pcthispanic"])
                if white + black + asian + hispanic < 1.0:
                    skipped += 1
                    continue
                lookup[name] = (white, black, asian, hispanic)

    with open(OUT_PATH, "wb") as f:
        pickle.dump(lookup, f, protocol=4)

    size_kb = OUT_PATH.stat().st_size // 1024
    print(f"[census] Saved {len(lookup):,} surnames → {OUT_PATH} ({size_kb:,} KB), skipped {skipped}")


if __name__ == "__main__":
    main()
