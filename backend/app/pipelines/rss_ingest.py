"""
RSS Feed Ingest Pipeline
Fetches real articles from major news outlet RSS feeds and extracts full text.
No API keys required — uses public RSS feeds + trafilatura for text extraction.
"""

import asyncio
import httpx
import uuid
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from app.config import settings
from app.models import Article, Source, Author

engine = create_async_engine(settings.database_url)
AsyncSession_ = async_sessionmaker(engine, expire_on_commit=False)

# RSS feeds from major news outlets — all public
RSS_FEEDS = {
    "The New York Times": {
        "domain": "nytimes.com",
        "feeds": [
            "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/US.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        ]
    },
    "Fox News": {
        "domain": "foxnews.com",
        "feeds": [
            "https://moxie.foxnews.com/google-publisher/latest.xml",
            "https://moxie.foxnews.com/google-publisher/politics.xml",
            "https://moxie.foxnews.com/google-publisher/us.xml",
        ]
    },
    "Reuters": {
        "domain": "reuters.com",
        "feeds": [
            "https://feeds.reuters.com/reuters/topNews",
            "https://feeds.reuters.com/reuters/politicsNews",
            "https://feeds.reuters.com/reuters/USdomesticNews",
        ]
    },
    "AP News": {
        "domain": "apnews.com",
        "feeds": [
            "https://rsshub.app/apnews/topics/apf-topnews",
            "https://rsshub.app/apnews/topics/apf-politics",
        ]
    },
    "The Guardian": {
        "domain": "theguardian.com",
        "feeds": [
            "https://www.theguardian.com/us-news/rss",
            "https://www.theguardian.com/world/rss",
            "https://www.theguardian.com/politics/rss",
        ]
    },
    "NPR": {
        "domain": "npr.org",
        "feeds": [
            "https://feeds.npr.org/1001/rss.xml",
            "https://feeds.npr.org/1014/rss.xml",  # politics
            "https://feeds.npr.org/1003/rss.xml",  # US
        ]
    },
    "The Washington Post": {
        "domain": "washingtonpost.com",
        "feeds": [
            "https://feeds.washingtonpost.com/rss/politics",
            "https://feeds.washingtonpost.com/rss/national",
            "https://feeds.washingtonpost.com/rss/world",
        ]
    },
    "BBC News": {
        "domain": "bbc.com",
        "feeds": [
            "http://feeds.bbci.co.uk/news/rss.xml",
            "http://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
            "http://feeds.bbci.co.uk/news/politics/rss.xml",
        ]
    },
    "Breitbart": {
        "domain": "breitbart.com",
        "feeds": [
            "https://feeds.feedburner.com/breitbart",
        ]
    },
    "HuffPost": {
        "domain": "huffpost.com",
        "feeds": [
            "https://www.huffpost.com/section/front-page/feed",
            "https://www.huffpost.com/section/politics/feed",
        ]
    },
}

# Namespaces commonly in RSS/Atom feeds
NS = {
    "media": "http://search.yahoo.com/mrss/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

def parse_rss_date(date_str: str) -> Optional[datetime]:
    """Parse common RSS date formats."""
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]
    date_str = date_str.strip()
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None

def clean_html(text: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&[a-z]+;', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_author_from_rss_item(item: ET.Element, text: str = "") -> Optional[str]:
    """Extract author from RSS item dc:creator, then fall back to byline patterns in text.

    Returns the raw author string as-is; the caller is responsible for splitting
    compound names (e.g. "Evan Halper, Rachel Siegel") via split_author_names().
    """
    # dc:creator is the standard RSS author field
    creator = item.find("dc:creator", NS)
    if creator is not None and creator.text:
        name = creator.text.strip()
        # Accept any non-trivial string — split_author_names() will separate
        # compound names downstream.  Only reject obviously bad values.
        if name and len(name) > 2:
            return name

    # Fallback: byline patterns in article text
    if text:
        patterns = [
            r'^By ([A-Z][a-z]+ [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            r'By ([A-Z][a-z]+ [A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*[|\n\r]',
            r'Written by ([A-Z][a-z]+ [A-Z][a-z]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text[:500])
            if match:
                name = match.group(1).strip()
                parts = name.split()
                if 2 <= len(parts) <= 4:
                    return name
    return None

async def get_or_create_author(db: AsyncSession, name: str, source_id: uuid.UUID) -> Optional[uuid.UUID]:
    """Find or create an author record with demographic inference."""
    from app.services.demographics import infer_demographics
    result = await db.execute(
        select(Author).where(Author.name == name, Author.source_id == source_id)
    )
    author = result.scalar_one_or_none()
    if author:
        return author.id
    demo = infer_demographics(name)
    author = Author(
        name=name,
        source_id=source_id,
        gender=demo.get("gender"),
        ethnicity=demo.get("ethnicity"),
        created_at=datetime.now(timezone.utc),
    )
    db.add(author)
    await db.commit()
    await db.refresh(author)
    return author.id

def extract_text_from_rss_item(item: ET.Element) -> str:
    """Extract as much text content as possible from an RSS item."""
    parts = []
    
    # Try content:encoded first (full article body if available)
    content_encoded = item.find("content:encoded", NS)
    if content_encoded is not None and content_encoded.text:
        parts.append(clean_html(content_encoded.text))
    
    # description / summary
    desc = item.find("description")
    if desc is not None and desc.text:
        cleaned = clean_html(desc.text)
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    
    # dc:description
    dc_desc = item.find("dc:description", NS)
    if dc_desc is not None and dc_desc.text:
        cleaned = clean_html(dc_desc.text)
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    
    return " ".join(parts)

def parse_rss_feed(xml_content: bytes) -> List[dict]:
    """Parse RSS/Atom feed XML and return list of article dicts."""
    articles = []
    try:
        root = ET.fromstring(xml_content)
        # Handle Atom feeds
        ns_atom = "http://www.w3.org/2005/Atom"
        
        items = root.findall(".//item")
        if not items:
            items = root.findall(f".//{{{ns_atom}}}entry")
        
        for item in items:
            def get_text(tag, ns=None):
                el = item.find(f"{{{ns}}}{tag}" if ns else tag)
                return el.text.strip() if el is not None and el.text else None
            
            title = get_text("title") or get_text("title", ns_atom)
            link = get_text("link") or get_text("link", ns_atom)
            if not link:
                # Atom link is sometimes an attribute
                link_el = item.find(f"{{{ns_atom}}}link")
                if link_el is not None:
                    link = link_el.get("href")

            pub_date_str = (get_text("pubDate") or get_text("published", ns_atom)
                           or get_text("updated", ns_atom) or get_text("date", "http://purl.org/dc/elements/1.1/"))

            text = extract_text_from_rss_item(item)
            author = extract_author_from_rss_item(item, text)

            if title and link:
                articles.append({
                    "title": clean_html(title),
                    "url": link,
                    "published_at": parse_rss_date(pub_date_str) if pub_date_str else None,
                    "text": text,
                    "author": author,
                })
    except ET.ParseError as e:
        print(f"[RSS] XML parse error: {e}")
    
    return articles

async def fetch_feed(client: httpx.AsyncClient, url: str) -> bytes:
    """Fetch a single RSS feed URL."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=20)
        if resp.status_code == 200:
            return resp.content
    except Exception as e:
        print(f"[RSS] Failed to fetch {url}: {e}")
    return b""

async def get_or_create_source(db: AsyncSession, domain: str, name: str) -> Optional[uuid.UUID]:
    result = await db.execute(select(Source).where(Source.name == name))
    source = result.scalar_one_or_none()
    if source:
        return source.id
    source = Source(name=name, domain=domain, country="US")
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source.id

def guess_section(title: str, url: str) -> str:
    text = (title + " " + url).lower()
    if any(x in text for x in ["politi", "elect", "congress", "senate", "house", "president", "democrat", "republican"]):
        return "politics"
    if any(x in text for x in ["econom", "market", "financ", "trade", "stock", "gdp", "inflation"]):
        return "economy"
    if any(x in text for x in ["health", "covid", "medic", "hospital", "disease", "vaccine"]):
        return "health"
    if any(x in text for x in ["tech", "digit", "ai ", "cyber", "software", "apple", "google", "meta"]):
        return "technology"
    if any(x in text for x in ["climat", "environment", "energy", "carbon", "weather"]):
        return "environment"
    if any(x in text for x in ["crime", "murder", "arrest", "police", "court", "legal"]):
        return "crime"
    if any(x in text for x in ["world", "international", "global", "ukraine", "russia", "china", "israel"]):
        return "world"
    return "general"

async def ingest_rss_feeds(
    limit_per_source: int = 20,
    sources: Optional[List[str]] = None,
    min_text_length: int = 100,
) -> dict:
    """
    Main entry point: fetch RSS feeds from major news outlets and store in DB.
    
    Args:
        limit_per_source: max articles per news source
        sources: list of source names to fetch (None = all)
        min_text_length: minimum character length to keep an article (filters stubs)
    
    Returns: summary dict
    """
    selected = {k: v for k, v in RSS_FEEDS.items() if sources is None or k in sources}
    print(f"[RSS] Starting ingest: {len(selected)} sources, {limit_per_source} articles each")
    
    total_ingested = 0
    results = {}
    
    async with httpx.AsyncClient(
        headers={"User-Agent": "MediaMetrics/1.0 (news research tool; +https://github.com/sharesecurity/media-metrics)"},
        timeout=30,
    ) as client:
        for source_name, config in selected.items():
            domain = config["domain"]
            feeds = config["feeds"]
            source_count = 0
            
            print(f"[RSS] Fetching {source_name} ({len(feeds)} feeds)")
            
            # Fetch all feeds for this source concurrently
            tasks = [fetch_feed(client, feed_url) for feed_url in feeds]
            feed_contents = await asyncio.gather(*tasks)
            
            # Parse all feeds
            all_articles = []
            for content in feed_contents:
                if content:
                    all_articles.extend(parse_rss_feed(content))
            
            # Deduplicate by URL
            seen_urls = set()
            unique_articles = []
            for art in all_articles:
                if art["url"] not in seen_urls:
                    seen_urls.add(art["url"])
                    unique_articles.append(art)
            
            print(f"[RSS]   {source_name}: {len(unique_articles)} unique articles found")
            
            # Store in DB
            async with AsyncSession_() as db:
                source_id = await get_or_create_source(db, domain, source_name)
                
                for art in unique_articles:
                    if source_count >= limit_per_source:
                        break
                    
                    try:
                        # Skip if URL already in DB
                        existing = await db.execute(select(Article).where(Article.url == art["url"]))
                        if existing.scalar_one_or_none():
                            continue
                        
                        # Skip articles with very little text
                        text = art.get("text", "")
                        if len(text) < min_text_length:
                            continue
                        
                        # Extract author(s) — split compound names like "A Smith, B Jones"
                        author_id = None
                        author_name = art.get("author")
                        if author_name:
                            try:
                                from app.pipelines.gdelt_ingest import split_author_names
                                names = split_author_names(author_name)
                                for i, name in enumerate(names):
                                    aid = await get_or_create_author(db, name, source_id)
                                    if i == 0:
                                        author_id = aid
                            except Exception as ae:
                                print(f"[RSS] Author create failed: {ae}")

                        article = Article(
                            source_id=source_id,
                            author_id=author_id,
                            url=art["url"],
                            title=art["title"][:500],
                            published_at=art.get("published_at") or datetime.now(timezone.utc),
                            section=guess_section(art["title"], art["url"]),
                            raw_text=text[:50000],
                            word_count=len(text.split()),
                            tags=[guess_section(art["title"], art["url"])],
                        )
                        db.add(article)
                        await db.commit()
                        await db.refresh(article)

                        # Store full text in MinIO, clear from Postgres
                        try:
                            from app.services.minio_service import store_article_text, ensure_bucket
                            from sqlalchemy import update as sql_update
                            await ensure_bucket()
                            minio_key = await store_article_text(str(article.id), text[:200000])
                            if minio_key:
                                await db.execute(
                                    sql_update(Article)
                                    .where(Article.id == article.id)
                                    .values(minio_key=minio_key, raw_text=None)
                                )
                                await db.commit()
                        except Exception as me:
                            print(f"[RSS] MinIO store failed (non-critical): {me}")

                        source_count += 1
                        total_ingested += 1
                        
                    except Exception as e:
                        print(f"[RSS]   Error storing article: {e}")
                        await db.rollback()
                        continue
            
            results[source_name] = source_count
            print(f"[RSS]   {source_name}: stored {source_count} new articles")
    
    print(f"[RSS] Done. Total ingested: {total_ingested}")
    return {"total": total_ingested, "by_source": results}
