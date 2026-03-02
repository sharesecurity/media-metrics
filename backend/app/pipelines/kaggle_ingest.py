"""
Kaggle "All the News" dataset ingest pipeline.

Supports two dataset versions:
  v1  snapcrack/all-the-news  — articles1/2/3.csv
      Columns: id, title, publication, author, date, year, month, url, content
  v2  a2rad/all-the-news-2-1  — all-the-news-2-1.csv
      Columns: date, year, month, day, author, title, article, url, section, publication

Data directory layout on LabStorage:
  /Volumes/LabStorage/media_metrics/raw_articles/v1/articles1.csv  (etc.)
  /Volumes/LabStorage/media_metrics/raw_articles/v2/all-the-news-2-1.csv

Call ingest_kaggle_dataset() from the router or as a script.
"""
from __future__ import annotations

import csv
import os
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional

DATA_ROOT = Path("/Volumes/LabStorage/media_metrics/raw_articles")

# Kaggle source slugs → DB source names
# Map publication name → existing seeded source name (case-insensitive substring match)
_PUB_MAP: dict[str, str] = {
    "new york times":       "The New York Times",
    "nytimes":              "The New York Times",
    "fox news":             "Fox News",
    "reuters":              "Reuters",
    "associated press":     "AP News",
    "guardian":             "The Guardian",
    "washington post":      "The Washington Post",
    "wapo":                 "The Washington Post",
    "breitbart":            "Breitbart",
    "npr":                  "NPR",
    "cnn":                  "CNN",
    "business insider":     "Business Insider",
    "buzzfeed news":        "BuzzFeed News",
    "buzzfeed":             "BuzzFeed News",
    "atlantic":             "The Atlantic",
    "the atlantic":         "The Atlantic",
    "vox":                  "Vox",
    "politico":             "Politico",
    "hill":                 "The Hill",
    "the hill":             "The Hill",
    "talking points memo":  "Talking Points Memo",
    "national review":      "National Review",
    "new yorker":           "The New Yorker",
    "vice":                 "Vice News",
    "techcrunch":           "TechCrunch",
    "wired":                "Wired",
    "verge":                "The Verge",
}


def _map_publication(pub: str) -> str:
    """Normalize a publication name to our standard source name."""
    lower = pub.strip().lower()
    for key, val in _PUB_MAP.items():
        if key in lower or lower in key:
            return val
    # Fall back: title-case the raw name
    return pub.strip().title()


def _parse_date(raw: str) -> Optional[datetime]:
    """Try common date formats used in the Kaggle dataset."""
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%Y"):
        try:
            return datetime.strptime(raw[:len(fmt) + 2], fmt)
        except ValueError:
            continue
    return None


def _csv_files(version: str) -> list[Path]:
    """List CSV files for a given dataset version."""
    root = DATA_ROOT / version
    if not root.exists():
        return []
    if version == "v1":
        return sorted(root.glob("articles*.csv"))
    elif version == "v2":
        return sorted(root.glob("*.csv"))
    return sorted(root.glob("*.csv"))


async def ingest_kaggle_dataset(
    version: str = "v1",
    limit: int = 5000,
    offset: int = 0,
    publications: Optional[list[str]] = None,
    min_content_length: int = 200,
) -> dict:
    """
    Ingest articles from the Kaggle dataset into Postgres.

    Args:
        version: "v1" or "v2"
        limit: max articles to insert (per call)
        offset: skip this many rows across all files
        publications: if set, only ingest these publication names (lowercase substrings)
        min_content_length: skip articles shorter than this many characters

    Returns:
        {"inserted": N, "skipped_dup": N, "skipped_short": N, "total_read": N}
    """
    from app.core.database import AsyncSessionLocal
    from app.models import Article, Source, Author
    from app.services.demographics import infer_demographics
    from app.services.minio_service import store_article_text
    from sqlalchemy import select

    csv_files = _csv_files(version)
    if not csv_files:
        raise FileNotFoundError(
            f"No CSV files found at {DATA_ROOT / version}. "
            "Run: python scripts/download_kaggle_data.py --dataset "
            + version
        )

    stats = {"inserted": 0, "skipped_dup": 0, "skipped_short": 0, "total_read": 0}

    async with AsyncSessionLocal() as db:
        # Pre-load sources into a lookup dict
        result = await db.execute(select(Source))
        all_sources = result.scalars().all()
        source_map: dict[str, uuid.UUID] = {s.name: s.id for s in all_sources}

        # Pre-load existing URLs for duplicate detection
        existing_urls_result = await db.execute(
            select(Article.url).where(Article.url.isnot(None))
        )
        existing_urls: set[str] = {r for (r,) in existing_urls_result.all()}

        rows_skipped = 0

        for csv_path in csv_files:
            if stats["inserted"] >= limit:
                break
            print(f"[Kaggle] Reading {csv_path.name} …")

            with open(csv_path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    stats["total_read"] += 1

                    # Skip up to offset rows
                    if rows_skipped < offset:
                        rows_skipped += 1
                        continue

                    if stats["inserted"] >= limit:
                        break

                    # --- Extract fields (handle v1 and v2 column names) ---
                    title   = (row.get("title") or "").strip()
                    pub     = (row.get("publication") or "").strip()
                    author  = (row.get("author") or "").strip()
                    url     = (row.get("url") or "").strip() or None
                    content = (row.get("content") or row.get("article") or "").strip()
                    raw_date = row.get("date") or ""

                    # Filter by publication if requested
                    if publications:
                        pub_lower = pub.lower()
                        if not any(p in pub_lower for p in publications):
                            continue

                    # Skip short/empty content
                    if len(content) < min_content_length:
                        stats["skipped_short"] += 1
                        continue

                    # Skip duplicate URLs
                    if url and url in existing_urls:
                        stats["skipped_dup"] += 1
                        continue

                    # --- Resolve or create Source ---
                    source_name = _map_publication(pub)
                    if source_name not in source_map:
                        new_source = Source(
                            id=uuid.uuid4(),
                            name=source_name,
                            domain=source_name.lower().replace(" ", "") + ".com",
                            political_lean_baseline=0.0,
                        )
                        db.add(new_source)
                        await db.flush()
                        source_map[source_name] = new_source.id
                        print(f"[Kaggle] Created source: {source_name}")

                    source_id = source_map[source_name]

                    # --- Resolve or create Author ---
                    author_id = None
                    if author and len(author) > 2:
                        auth_result = await db.execute(
                            select(Author).where(
                                Author.name == author,
                                Author.source_id == source_id,
                            )
                        )
                        existing_author = auth_result.scalar_one_or_none()
                        if existing_author:
                            author_id = existing_author.id
                        else:
                            demo = infer_demographics(author)
                            new_author = Author(
                                id=uuid.uuid4(),
                                name=author,
                                source_id=source_id,
                                gender=demo["gender"],
                                ethnicity=demo["ethnicity"],
                            )
                            db.add(new_author)
                            await db.flush()
                            author_id = new_author.id

                    # --- Parse date ---
                    published_at = _parse_date(raw_date)

                    # --- Build article text (title + content) ---
                    full_text = f"{title}\n\n{content}" if title else content

                    # --- Create Article record ---
                    article = Article(
                        id=uuid.uuid4(),
                        title=title or f"Article from {source_name}",
                        url=url,
                        source_id=source_id,
                        author_id=author_id,
                        published_at=published_at,
                        ingested_at=datetime.utcnow(),
                        source_name=source_name,
                        raw_text=None,  # will store in MinIO below
                    )
                    db.add(article)
                    await db.flush()

                    # --- Store full text in MinIO ---
                    try:
                        minio_key = await store_article_text(str(article.id), full_text)
                        article.minio_key = minio_key
                    except Exception as e:
                        # MinIO failure is non-critical; store in Postgres as fallback
                        article.raw_text = full_text[:50000]
                        print(f"[Kaggle] MinIO fallback for {article.id}: {e}")

                    await db.commit()

                    if url:
                        existing_urls.add(url)
                    stats["inserted"] += 1

                    if stats["inserted"] % 100 == 0:
                        print(
                            f"[Kaggle] Inserted {stats['inserted']}/{limit} "
                            f"(skipped dup={stats['skipped_dup']}, short={stats['skipped_short']})"
                        )

    print(
        f"[Kaggle] Done: inserted={stats['inserted']}, "
        f"skipped_dup={stats['skipped_dup']}, skipped_short={stats['skipped_short']}, "
        f"total_read={stats['total_read']}"
    )
    return stats
