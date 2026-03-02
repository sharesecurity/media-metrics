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
from sqlalchemy import select, update
from app.config import settings
from app.models import Article

engine = create_async_engine(settings.database_url)
AsyncSession_ = async_sessionmaker(engine, expire_on_commit=False)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def extract_text(html: bytes, url: str) -> str | None:
    """Use trafilatura to extract clean article text from raw HTML."""
    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            favor_recall=True,
        )
        return text
    except Exception as e:
        print(f"[Scraper] trafilatura error for {url}: {e}")
        return None


async def scrape_article(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch a URL and extract article text."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=20)
        if resp.status_code != 200:
            print(f"[Scraper] HTTP {resp.status_code} for {url}")
            return None
        return extract_text(resp.content, url)
    except httpx.TimeoutException:
        print(f"[Scraper] Timeout: {url}")
        return None
    except Exception as e:
        print(f"[Scraper] Error fetching {url}: {e}")
        return None


async def scrape_missing_articles(
    limit: int = 200,
    min_text_length: int = 150,
    concurrency: int = 5,
) -> dict:
    """
    Find all articles with no raw_text and scrape them.
    Returns a summary of results.
    """
    print(f"[Scraper] Starting — limit={limit}, concurrency={concurrency}")

    # Get articles needing text
    async with AsyncSession_() as db:
        result = await db.execute(
            select(Article.id, Article.url)
            .where(Article.raw_text.is_(None))
            .limit(limit)
        )
        articles_to_scrape = result.all()

    total = len(articles_to_scrape)
    print(f"[Scraper] Found {total} articles without text")

    if total == 0:
        return {"scraped": 0, "failed": 0, "total_candidates": 0}

    scraped = 0
    failed = 0
    semaphore = asyncio.Semaphore(concurrency)

    async def scrape_one(article_id, url: str):
        nonlocal scraped, failed
        async with semaphore:
            text = await scrape_article(client, url)
            if text and len(text) >= min_text_length:
                async with AsyncSession_() as db:
                    await db.execute(
                        update(Article)
                        .where(Article.id == article_id)
                        .values(
                            raw_text=text[:80000],
                            word_count=len(text.split()),
                        )
                    )
                    await db.commit()
                scraped += 1
                if scraped % 10 == 0:
                    print(f"[Scraper] Progress: {scraped}/{total} scraped")
            else:
                failed += 1

    async with httpx.AsyncClient(headers=HEADERS, timeout=25) as client:
        tasks = [scrape_one(art_id, url) for art_id, url in articles_to_scrape]
        await asyncio.gather(*tasks, return_exceptions=True)

    print(f"[Scraper] Done. Scraped={scraped}, Failed/Short={failed}")
    return {
        "scraped": scraped,
        "failed": failed,
        "total_candidates": total,
    }
