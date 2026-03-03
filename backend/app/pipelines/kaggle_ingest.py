"""
Kaggle news dataset ingest pipeline.

Supports three dataset versions:
  headlines  jordankrishnayah/45m-headlines-from-2007-2022-10-largest-sites
             Columns: Date, Publication, Headline, URL
             4.4M rows, 10 outlets (NYT, WaPo, Fox, CNN, Guardian, BBC, etc.), 2007-2023
             ✓ Available/working — downloaded to LabStorage

  v1  snapcrack/all-the-news  (REMOVED from Kaggle — kept for compatibility)
      Columns: id, title, publication, author, date, year, month, url, content

  v2  a2rad/all-the-news-2-1  (REMOVED from Kaggle — kept for compatibility)
      Columns: date, year, month, day, author, title, article, url, section, publication

Data directory layout on LabStorage:
  /Volumes/LabStorage/media_metrics/raw_articles/headlines/headlines.csv
  /Volumes/LabStorage/media_metrics/raw_articles/v1/articles1.csv  (etc.)
  /Volumes/LabStorage/media_metrics/raw_articles/v2/all-the-news-2-1.csv

For the `headlines` dataset: articles are ingested with headline as title + URL stored.
The scraper can then fetch full article text from those URLs.
"""
from __future__ import annotations

import csv
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_ROOT = Path("/Volumes/LabStorage/media_metrics/raw_articles")

# Map publication name → our standard source name (case-insensitive substring match)
_PUB_MAP: dict[str, str] = {
    "new york times":       "The New York Times",
    "nytimes":              "The New York Times",
    "fox news":             "Fox News",
    "fox":                  "Fox News",
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
    "daily mail":           "Daily Mail",
    "new york post":        "New York Post",
    "bbc":                  "BBC",
    "cnbc":                 "CNBC",
    "usa today":            "USA Today",
}


def _map_publication(pub: str) -> str:
    """Normalize a publication name to our standard source name."""
    lower = pub.strip().lower()
    for key, val in _PUB_MAP.items():
        if key in lower or lower in key:
            return val
    return pub.strip().title()


def _parse_date(raw: str) -> Optional[datetime]:
    """Parse dates in various formats used across the Kaggle datasets."""
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%Y"):
        try:
            return datetime.strptime(raw[:len(fmt)], fmt)
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
    elif version == "headlines":
        return sorted(root.glob("*.csv"))
    else:  # v2 or any other
        return sorted(root.glob("*.csv"))


async def ingest_kaggle_dataset(
    version: str = "headlines",
    limit: int = 5000,
    offset: int = 0,
    publications: Optional[list[str]] = None,
    min_content_length: int = 0,
) -> dict:
    """
    Ingest articles from a Kaggle news dataset into Postgres.

    Args:
        version: "headlines" (recommended), "v1", or "v2"
        limit: max articles to insert per call
        offset: skip this many rows across all files (for paging through large datasets)
        publications: optional list of lowercase publication name substrings to filter
        min_content_length: skip articles shorter than this (0 = allow headlines-only)

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
            f"Run: python scripts/download_kaggle_data.py --dataset {version}"
        )

    stats = {"inserted": 0, "skipped_dup": 0, "skipped_short": 0, "total_read": 0}
    is_headlines = version == "headlines"

    async with AsyncSessionLocal() as db:
        # Pre-load sources
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

                    # --- Extract fields based on format ---
                    if is_headlines:
                        title   = (row.get("Headline") or "").strip()
                        pub     = (row.get("Publication") or "").strip()
                        author  = ""
                        url     = (row.get("URL") or "").strip() or None
                        content = ""  # no body text in this dataset
                        raw_date = row.get("Date") or ""
                    else:
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

                    # Skip short content (only enforced for v1/v2 with body text)
                    if not is_headlines and min_content_length > 0 and len(content) < min_content_length:
                        stats["skipped_short"] += 1
                        continue

                    # Skip missing title
                    if not title:
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

                    # --- Resolve or create Author (only for v1/v2) ---
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

                    # --- Create Article ---
                    article = Article(
                        id=uuid.uuid4(),
                        title=title,
                        url=url,
                        source_id=source_id,
                        author_id=author_id,
                        published_at=published_at,
                        ingested_at=datetime.utcnow(),
                        source_name=source_name,
                        raw_text=None,
                    )
                    db.add(article)
                    await db.flush()

                    # --- Store content if available ---
                    if content:
                        full_text = f"{title}\n\n{content}"
                        try:
                            minio_key = await store_article_text(str(article.id), full_text)
                            article.minio_key = minio_key
                        except Exception as e:
                            article.raw_text = full_text[:50000]
                            print(f"[Kaggle] MinIO fallback for {article.id}: {e}")
                    # For headlines-only: leave raw_text=None, URL present → scraper picks it up

                    await db.commit()

                    if url:
                        existing_urls.add(url)
                    stats["inserted"] += 1

                    if stats["inserted"] % 500 == 0:
                        print(
                            f"[Kaggle] Inserted {stats['inserted']}/{limit} "
                            f"(dup={stats['skipped_dup']}, short={stats['skipped_short']})"
                        )

    print(
        f"[Kaggle] Done: inserted={stats['inserted']}, "
        f"skipped_dup={stats['skipped_dup']}, skipped_short={stats['skipped_short']}, "
        f"total_read={stats['total_read']}"
    )
    return stats
