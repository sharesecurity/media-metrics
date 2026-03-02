from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from app.pipelines.gdelt_ingest import ingest_gdelt_sample
from app.pipelines.rss_ingest import ingest_rss_feeds, RSS_FEEDS
from app.pipelines.scraper import scrape_missing_articles, SCRAPER_STATUS
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models import Article, AnalysisResult

router = APIRouter()

class IngestRequest(BaseModel):
    source: str = "rss"  # rss, gdelt, embedded, scrape
    limit: int = 20
    date: Optional[str] = None  # YYYY-MM-DD (for gdelt)
    sources: Optional[List[str]] = None  # filter to specific outlets (for rss)
    concurrency: int = 5  # parallel scrape workers
    auto_analyze: bool = True  # automatically queue analysis after ingest

@router.post("/start")
async def start_ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    """Start a data ingestion job. Set auto_analyze=true to automatically queue bias analysis for new articles."""
    if req.source == "rss":
        if req.auto_analyze:
            background_tasks.add_task(_ingest_then_analyze_rss, req.limit, req.sources)
        else:
            background_tasks.add_task(ingest_rss_feeds, req.limit, req.sources)
        return {
            "status": "started",
            "source": "rss",
            "limit_per_source": req.limit,
            "auto_analyze": req.auto_analyze,
            "outlets": req.sources or list(RSS_FEEDS.keys()),
        }
    elif req.source == "scrape":
        if req.auto_analyze:
            background_tasks.add_task(_scrape_then_analyze, req.limit, req.concurrency)
        else:
            background_tasks.add_task(scrape_missing_articles, req.limit, 150, req.concurrency)
        return {
            "status": "started",
            "source": "scrape",
            "limit": req.limit,
            "concurrency": req.concurrency,
            "auto_analyze": req.auto_analyze,
            "message": "Scraping full text for articles missing raw_text. Check backend logs for progress.",
        }
    elif req.source == "gdelt":
        if req.auto_analyze:
            background_tasks.add_task(_ingest_then_analyze_gdelt, req.limit, req.date)
        else:
            background_tasks.add_task(ingest_gdelt_sample, req.limit, req.date)
        return {"status": "started", "source": "gdelt", "limit": req.limit, "auto_analyze": req.auto_analyze}
    elif req.source == "embedded":
        from app.pipelines.gdelt_ingest import ingest_embedded_sample
        if req.auto_analyze:
            background_tasks.add_task(_ingest_then_analyze_embedded, req.limit)
        else:
            background_tasks.add_task(ingest_embedded_sample, req.limit)
        return {"status": "started", "source": "embedded", "auto_analyze": req.auto_analyze}
    return {"error": f"Unknown source: {req.source}"}

async def _queue_unanalyzed():
    """Queue bias analysis for all articles that don't yet have analysis results."""
    from app.core.database import AsyncSessionLocal
    from app.models import Article, AnalysisResult
    from app.pipelines.bias_analyzer import analyze_article_bias
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        analyzed_ids = select(AnalysisResult.article_id)
        result = await db.execute(
            select(Article.id).where(~Article.id.in_(analyzed_ids)).limit(200)
        )
        ids = [str(r.id) for r in result.all()]
    print(f"[Ingest] Auto-queuing analysis for {len(ids)} new articles")
    for aid in ids:
        await analyze_article_bias(aid, "full")

async def _scrape_then_analyze(limit: int, concurrency: int):
    await scrape_missing_articles(limit, 150, concurrency)
    await _queue_unanalyzed()

async def _ingest_then_analyze_rss(limit: int, sources):
    await ingest_rss_feeds(limit, sources)
    await _queue_unanalyzed()

async def _ingest_then_analyze_gdelt(limit: int, date):
    await ingest_gdelt_sample(limit, date)
    await _queue_unanalyzed()

async def _ingest_then_analyze_embedded(limit: int):
    from app.pipelines.gdelt_ingest import ingest_embedded_sample
    await ingest_embedded_sample(limit)
    await _queue_unanalyzed()

@router.get("/status")
async def ingest_status(db: AsyncSession = Depends(get_db)):
    """Return scraper + analysis pipeline status."""
    # Count articles without text (still need scraping)
    needs_scrape = await db.execute(
        select(func.count(Article.id))
        .where(Article.raw_text.is_(None))
        .where(Article.minio_key.is_(None))
        .where(Article.url.isnot(None))
    )
    needs_scrape_count = needs_scrape.scalar() or 0

    # Count unanalyzed articles
    analyzed_ids = select(AnalysisResult.article_id)
    needs_analysis = await db.execute(
        select(func.count(Article.id)).where(~Article.id.in_(analyzed_ids))
    )
    needs_analysis_count = needs_analysis.scalar() or 0

    return {
        "scraper": {**SCRAPER_STATUS, "needs_scrape": needs_scrape_count},
        "analysis": {"needs_analysis": needs_analysis_count},
    }

@router.get("/sources")
async def list_sources():
    """List available RSS sources for ingestion."""
    return {
        "rss_sources": list(RSS_FEEDS.keys()),
        "total": len(RSS_FEEDS),
    }
