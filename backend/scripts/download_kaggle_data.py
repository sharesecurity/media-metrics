#!/usr/bin/env python3
"""
Download the "All the News" datasets from Kaggle to LabStorage.

Requires Kaggle API credentials: https://www.kaggle.com/settings → API → Create New Token
Place the downloaded kaggle.json in ~/.kaggle/kaggle.json (chmod 600).

Usage:
    python scripts/download_kaggle_data.py [--dataset v1|v2|both]

Datasets:
  v1  snapcrack/all-the-news        3 CSV files, ~210K articles, 2012-2018, ~500MB
  v2  a2rad/all-the-news-2-1        1 CSV file,  ~2.7M articles, 2016-2020, ~9GB

Both are stored to: /Volumes/LabStorage/media_metrics/raw_articles/
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
from pathlib import Path

DEST_DIR = Path("/Volumes/LabStorage/media_metrics/raw_articles")

DATASETS = {
    "v1": {
        "slug": "snapcrack/all-the-news",
        "label": "All the News v1 (~210K articles, 2012-2018, ~500MB)",
        "files": ["articles1.csv", "articles2.csv", "articles3.csv"],
    },
    "v2": {
        "slug": "a2rad/all-the-news-2-1",
        "label": "All the News v2 (~2.7M articles, 2016-2020, ~9GB)",
        "files": ["all-the-news-2-1.csv"],
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


def download_dataset(slug: str, dest: Path, label: str):
    dest.mkdir(parents=True, exist_ok=True)
    print(f"\nDownloading {label}")
    print(f"  Destination: {dest}")
    result = subprocess.run(
        ["kaggle", "datasets", "download", "-d", slug, "--unzip", "-p", str(dest)],
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"  ERROR: kaggle download failed (exit code {result.returncode})")
        sys.exit(result.returncode)
    print(f"  Done → {dest}")


def main():
    parser = argparse.ArgumentParser(description="Download All the News datasets from Kaggle")
    parser.add_argument("--dataset", choices=["v1", "v2", "both"], default="v1",
                        help="Which dataset to download (default: v1)")
    args = parser.parse_args()

    check_kaggle_auth()

    targets = []
    if args.dataset in ("v1", "both"):
        targets.append("v1")
    if args.dataset in ("v2", "both"):
        targets.append("v2")

    for key in targets:
        ds = DATASETS[key]
        dest = DEST_DIR / key
        download_dataset(ds["slug"], dest, ds["label"])

    print("\n✓ Download complete.")
    print(f"  Data at: {DEST_DIR}")
    print("\nNext step: POST /api/ingest/kaggle to ingest into Postgres")
    print("  or run:   make ingest-kaggle")


if __name__ == "__main__":
    main()
