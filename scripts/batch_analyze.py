#!/usr/bin/env python3
"""
Parallel batch analyzer for Media Metrics.
Queries DB directly for unanalyzed articles with sufficient text.
Usage: python3 scripts/batch_analyze.py [--concurrency 3] [--min-text 100]
"""
import asyncio
import aiohttp
import argparse
import subprocess
import json
from datetime import datetime

API_BASE = "http://localhost:8010"
DB_CONTAINER = "mm_postgres"
DB_USER = "media"
DB_NAME = "media_metrics"

def get_unanalyzed_ids(min_text=100):
    """Query DB directly for unanalyzed article IDs with enough text."""
    sql = f"""
        SELECT a.id FROM articles a
        LEFT JOIN analysis_results ar ON a.id = ar.article_id
        WHERE ar.id IS NULL
        AND LENGTH(a.raw_text) >= {min_text}
        ORDER BY LENGTH(a.raw_text) DESC;
    """
    result = subprocess.run(
        ["docker", "exec", DB_CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-c", sql],
        capture_output=True, text=True
    )
    ids = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    return ids

async def analyze_article(session, article_id, sem, idx, total):
    async with sem:
        try:
            async with session.post(
                f"{API_BASE}/api/analysis/run",
                json={"article_id": article_id},
                timeout=aiohttp.ClientTimeout(total=300)
            ) as r:
                result = await r.json()
                if r.status == 200:
                    lean = result.get("political_lean", "?")
                    print(f"[{idx}/{total}] ✅ {article_id[:8]}... lean={lean}", flush=True)
                else:
                    print(f"[{idx}/{total}] ❌ {article_id[:8]}... {r.status}: {result.get('detail','')}", flush=True)
                return result
        except Exception as e:
            print(f"[{idx}/{total}] ❌ {article_id[:8]}... ERROR: {e}", flush=True)
            return None

async def main(concurrency=3, min_text=100):
    print(f"=== Batch Analyzer | concurrency={concurrency} min_text={min_text} ===")
    print(f"Started: {datetime.now().strftime('%H:%M:%S')}", flush=True)

    ids = get_unanalyzed_ids(min_text)
    total = len(ids)
    print(f"Found {total} unanalyzed articles with >={min_text} chars in DB\n", flush=True)

    if total == 0:
        print("Nothing to do!")
        return

    sem = asyncio.Semaphore(concurrency)
    connector = aiohttp.TCPConnector(limit=concurrency + 2)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [analyze_article(session, aid, sem, i+1, total) for i, aid in enumerate(ids)]
        results = await asyncio.gather(*tasks)

    success = sum(1 for r in results if r and "political_lean" in r)
    print(f"\n=== Done | {success}/{total} succeeded | {datetime.now().strftime('%H:%M:%S')} ===")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--min-text", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(main(args.concurrency, args.min_text))
