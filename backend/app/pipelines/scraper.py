"""
Article Scraper Pipeline
Fetches full text for articles that only have URLs (no raw_text).
Uses trafilatura — the best Python web scraping library for news articles.
"""

import asyncio
import httpx
import trafilatura
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, update, case, func, cast, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from app.config import settings
from app.models import Article, Source, Author

engine = create_async_engine(settings.database_url)
AsyncSession_ = async_sessionmaker(engine, expire_on_commit=False)

# Global status tracker — read by ingest status endpoint
SCRAPER_STATUS: dict = {
    "running": False,
    "scraped": 0,
    "failed": 0,
    "total": 0,
    "started_at": None,
    "finished_at": None,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# HTTP status codes that indicate a permanent failure — don't retry
PERMANENT_FAILURE_CODES = {400, 401, 403, 404, 410, 451}

# Source domains with better scraping success rates — prioritized first
PRIORITY_DOMAINS = {
    "theguardian.com", "dailymail.co.uk", "bbc.com", "bbc.co.uk",
    "cnbc.com", "breitbart.com", "huffpost.com", "npr.org",
}


def extract_text_and_meta(html: bytes, url: str) -> tuple[str | None, str | None, str | None]:
    """Use trafilatura to extract article text, title, and author byline."""
    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            favor_recall=True,
        )
        meta = trafilatura.extract_metadata(html, default_url=url)
        title = meta.title if meta and meta.title else None
        author = meta.author if meta and meta.author else None
        return text, title, author
    except Exception as e:
        print(f"[Scraper] trafilatura error for {url}: {e}")
        return None, None, None


def extract_text(html: bytes, url: str) -> str | None:
    """Backward-compatible wrapper — returns text only."""
    text, _, _ = extract_text_and_meta(html, url)
    return text


async def scrape_article(
    client: httpx.AsyncClient, url: str
) -> tuple[str | None, str | None, str | None, int | None]:
    """
    Fetch a URL and extract (text, title, author, http_status).
    http_status is None on network errors, otherwise the HTTP status code.
    """
    try:
        resp = await client.get(url, follow_redirects=True, timeout=20)
        if resp.status_code != 200:
            print(f"[Scraper] HTTP {resp.status_code} for {url}")
            return None, None, None, resp.status_code
        text, title, author = extract_text_and_meta(resp.content, url)
        return text, title, author, 200
    except httpx.TimeoutException:
        print(f"[Scraper] Timeout: {url}")
        return None, None, None, None
    except Exception as e:
        print(f"[Scraper] Error fetching {url}: {e}")
        return None, None, None, None


async def scrape_missing_articles(
    limit: int = 200,
    min_text_length: int = 150,
    concurrency: int = 5,
) -> dict:
    """
    Find all articles with no raw_text and scrape them.
    - Excludes articles already marked scrape_failed or with null URLs
    - Prioritizes sources known to be more accessible
    - Marks permanent HTTP failures (403, 404, etc.) as scrape_failed
    Returns a summary of results.
    """
    global SCRAPER_STATUS
    print(f"[Scraper] Starting — limit={limit}, concurrency={concurrency}")

    async with AsyncSession_() as db:
        # Priority ordering: prefer known-good domains first
        priority = case(
            *[
                (Article.url.ilike(f"%{domain}%"), 1)
                for domain in PRIORITY_DOMAINS
            ],
            else_=2,
        )
        result = await db.execute(
            select(Article.id, Article.url, Article.title, Article.source_id, Article.author_id)
            .where(Article.raw_text.is_(None))
            .where(Article.minio_key.is_(None))
            .where(Article.url.is_not(None))
            .where(
                ~cast(
                    func.coalesce(Article.extra["scrape_failed"].astext, "false"),
                    Boolean,
                )
            )
            .order_by(priority, Article.published_at.desc().nulls_last())
            .limit(limit)
        )
        articles_to_scrape = result.all()

    total = len(articles_to_scrape)
    print(f"[Scraper] Found {total} articles without text")

    if total == 0:
        SCRAPER_STATUS.update({"running": False, "scraped": 0, "failed": 0, "total": 0,
                               "started_at": None, "finished_at": None})
        return {"scraped": 0, "failed": 0, "total_candidates": 0}

    scraped = 0
    failed = 0
    semaphore = asyncio.Semaphore(concurrency)

    SCRAPER_STATUS.update({
        "running": True,
        "scraped": 0,
        "failed": 0,
        "total": total,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    })

    async def scrape_one(article_id, url: str, current_title: str = "", source_id=None, has_author: bool = False):
        nonlocal scraped, failed
        async with semaphore:
            text, scraped_title, scraped_author, http_status = await scrape_article(client, url)
            if text and len(text) >= min_text_length:
                async with AsyncSession_() as db:
                    values = {"raw_text": text[:80000], "word_count": len(text.split())}
                    # Update placeholder titles (e.g. "Article from CNN (2026-03-01)")
                    if scraped_title and (
                        not current_title
                        or current_title.startswith("Article from ")
                        or current_title.startswith("Untitled")
                    ):
                        values["title"] = scraped_title[:500]
                    try:
                        from app.services.minio_service import store_article_text, ensure_bucket
                        await ensure_bucket()
                        minio_key = await store_article_text(str(article_id), text[:200000])
                        if minio_key:
                            values["minio_key"] = minio_key
                            values["raw_text"] = None
                    except Exception as me:
                        print(f"[Scraper] MinIO store failed (non-critical): {me}")
                    await db.execute(update(Article).where(Article.id == article_id).values(**values))
                    await db.commit()
                # Wire up author from scraped metadata (only when article has no author yet)
                if scraped_author and not has_author and source_id:
                    try:
                        from app.pipelines.gdelt_ingest import split_author_names, get_or_create_author
                        names = split_author_names(scraped_author)
                        if names:
                            async with AsyncSession_() as db_auth:
                                for i, name in enumerate(names):
                                    aid = await get_or_create_author(db_auth, name, source_id)
                                    if i == 0 and aid:
                                        await db_auth.execute(
                                            update(Article).where(Article.id == article_id).values(author_id=aid)
                                        )
                                await db_auth.commit()
                            print(f"[Scraper] Author linked: {scraped_author[:60]}")
                    except Exception as ae:
                        print(f"[Scraper] Author create failed: {ae}")
                scraped += 1
                SCRAPER_STATUS["scraped"] = scraped
                if scraped % 5 == 0:
                    print(f"[Scraper] Progress: {scraped}/{total} scraped")
            else:
                failed += 1
                SCRAPER_STATUS["failed"] = failed
                # Mark permanent HTTP failures so they're not retried
                if http_status in PERMANENT_FAILURE_CODES:
                    async with AsyncSession_() as db:
                        await db.execute(
                            update(Article)
                            .where(Article.id == article_id)
                            .values(extra=func.jsonb_set(
                                func.coalesce(Article.extra, cast({}, JSONB)),
                                "{scrape_failed}",
                                cast("true", JSONB),
                            ))
                        )
                        await db.commit()

    async with httpx.AsyncClient(headers=HEADERS, timeout=25) as client:
        tasks = [
            scrape_one(art_id, url, title or "", source_id, author_id is not None)
            for art_id, url, title, source_id, author_id in articles_to_scrape
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    SCRAPER_STATUS.update({
        "running": False,
        "scraped": scraped,
        "failed": failed,
        "total": total,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    })
    print(f"[Scraper] Done. Scraped={scraped}, Failed/Short={failed}")
    return {
        "scraped": scraped,
        "failed": failed,
        "total_candidates": total,
    }
