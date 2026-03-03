#!/usr/bin/env python3
"""
Download Kaggle news datasets to LabStorage.

Requires Kaggle API credentials: https://www.kaggle.com/settings → API → Create New Token
Place the downloaded kaggle.json in ~/.kaggle/kaggle.json (chmod 600).

Usage:
    python scripts/download_kaggle_data.py [--dataset headlines|v1|v2|both]

Datasets:
  headlines  jordankrishnayah/45m-headlines-from-2007-2022-10-largest-sites  ← RECOMMENDED
             4.4M headlines, 10 major outlets (NYT, WaPo, Fox, CNN, BBC, etc.), 2007-2023
             ~714MB on disk. No full article text — use scraper to fetch after ingest.
             ✓ Verified working with Kaggle API

  v1  snapcrack/all-the-news        [REMOVED from Kaggle — likely 403]
  v2  a2rad/all-the-news-2-1        [REMOVED from Kaggle — likely 403]

Data is stored to: /Volumes/LabStorage/media_metrics/raw_articles/{version}/
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEST_DIR = Path("/Volumes/LabStorage/media_metrics/raw_articles")

DATASETS = {
    "headlines": {
        "slug": "jordankrishnayah/45m-headlines-from-2007-2022-10-largest-sites",
        "label": "4.5M Headlines from 10 major outlets (2007-2022), ~714MB",
        "note": "Headlines only (no body text). Run scraper after ingest to fetch full text.",
    },
    "v1": {
        "slug": "snapcrack/all-the-news",
        "label": "All the News v1 (~210K articles, 2012-2018) [may be unavailable]",
        "note": "This dataset has been removed/privatized on Kaggle and may 403.",
    },
    "v2": {
        "slug": "a2rad/all-the-news-2-1",
        "label": "All the News v2 (~2.7M articles, 2016-2020) [may be unavailable]",
        "note": "This dataset has been removed/privatized on Kaggle and may 403.",
    },
}


def check_kaggle_auth():
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    if not kaggle_json.exists():
        print("ERROR: ~/.kaggle/kaggle.json not found.")
        print("  1. Go to https://www.kaggle.com/settings → API → Create New Token")
        print("  2. Move downloaded kaggle.json to ~/.kaggle/kaggle.json")
        print("  3. chmod 600 ~/.kaggle/kaggle.json")
        sys.exit(1)
    os.chmod(kaggle_json, 0o600)


def download_dataset(slug: str, dest: Path, label: str, note: str = ""):
    dest.mkdir(parents=True, exist_ok=True)
    print(f"\nDownloading: {label}")
    if note:
        print(f"  Note: {note}")
    print(f"  Destination: {dest}")
    result = subprocess.run(
        ["kaggle", "datasets", "download", "-d", slug, "--unzip", "-p", str(dest)],
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"  ERROR: download failed (exit code {result.returncode})")
        print("  If you got a 403, this dataset may have been removed from Kaggle.")
        sys.exit(result.returncode)
    print(f"  Done → {dest}")


def main():
    parser = argparse.ArgumentParser(description="Download Kaggle news datasets")
    parser.add_argument(
        "--dataset",
        choices=["headlines", "v1", "v2", "both"],
        default="headlines",
        help="Which dataset to download (default: headlines — the working one)",
    )
    args = parser.parse_args()

    check_kaggle_auth()

    targets = []
    if args.dataset == "both":
        targets = ["v1", "v2"]
    else:
        targets = [args.dataset]

    for key in targets:
        ds = DATASETS[key]
        dest = DEST_DIR / key
        download_dataset(ds["slug"], dest, ds["label"], ds.get("note", ""))

    print("\n✓ Download complete.")
    print(f"  Data at: {DEST_DIR}")
    print("\nNext steps:")
    if "headlines" in targets:
        print("  1. POST /api/ingest/kaggle  (version=headlines, limit=5000)")
        print("  2. POST /api/ingest/start   (source=scrape) to fetch full text from URLs")
        print("  3. POST /api/analysis/run-all to analyze scraped articles")
    else:
        print("  1. POST /api/ingest/kaggle  (version=v1 or v2, limit=1000)")


if __name__ == "__main__":
    main()
