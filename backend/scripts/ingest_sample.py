"""
Ingest sample articles from GDELT and RSS feeds.
Run: python -m app.scripts.ingest_sample
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

import httpx
import feedparser
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import AsyncSessionLocal
from app.models.db import Article, Source, Author
from sqlalchemy import select

RSS_FEEDS = [
    ("Reuters", "https://feeds.reuters.com/reuters/topNews"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("Fox News", "https://moxie.foxnews.com/google-publisher/latest.xml"),
    ("CNN", "http://rss.cnn.com/rss/cnn_topstories.rss"),
]

async def get_or_create_source(db: AsyncSession, name: str) -> int:
    result = await db.execute(select(Source).where(Source.name == name))
    source = result.scalar_one_or_none()
    if source:
        return source.id
    source = Source(name=name)
    db.add(source)
    await db.flush()
    return source.id

async def ingest_feed(db: AsyncSession, source_name: str, feed_url: str) -> int:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(feed_url, headers={"User-Agent": "MediaMetrics/1.0"})
            feed = feedparser.parse(r.text)
    except Exception as e:
        print(f"  Error fetching {feed_url}: {e}")
        return 0

    source_id = await get_or_create_source(db, source_name)
    count = 0

    for entry in feed.entries[:20]:  # 20 per feed for sample
        url = entry.get("link", "")
        # Skip if exists
        existing = await db.execute(select(Article).where(Article.url == url))
        if existing.scalar_one_or_none():
            continue

        # Parse date
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6])
            except Exception:
                pass

        content = entry.get("summary", "") or entry.get("description", "")
        title = entry.get("title", "No title")
        
        article = Article(
            source_id=source_id,
            title=title,
            url=url,
            content=content,
            word_count=len(content.split()),
            published_at=published,
            section=entry.get("tags", [{}])[0].get("term") if entry.get("tags") else None
        )
        db.add(article)
        count += 1

    await db.commit()
    return count

async def main():
    print("🗞️  Media Metrics — Sample Ingest")
    print("="*40)
    total = 0
    async with AsyncSessionLocal() as db:
        for source_name, feed_url in RSS_FEEDS:
            print(f"  Ingesting {source_name}...")
            n = await ingest_feed(db, source_name, feed_url)
            print(f"    ✓ {n} new articles")
            total += n
    print(f"\n✅ Total ingested: {total} articles")

if __name__ == "__main__":
    asyncio.run(main())
