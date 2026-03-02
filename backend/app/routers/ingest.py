from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from app.pipelines.gdelt_ingest import ingest_gdelt_sample
from app.pipelines.rss_ingest import ingest_rss_feeds, RSS_FEEDS
from app.pipelines.scraper import scrape_missing_articles
from typing import Optional, List

router = APIRouter()

class IngestRequest(BaseModel):
    source: str = "rss"  # rss, gdelt, embedded, scrape
    limit: int = 20
    date: Optional[str] = None  # YYYY-MM-DD (for gdelt)
    sources: Optional[List[str]] = None  # filter to specific outlets (for rss)
    concurrency: int = 5  # parallel scrape workers

@router.post("/start")
async def start_ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    """Start a data ingestion job."""
    if req.source == "rss":
        background_tasks.add_task(ingest_rss_feeds, req.limit, req.sources)
        return {
            "status": "started",
            "source": "rss",
            "limit_per_source": req.limit,
            "outlets": req.sources or list(RSS_FEEDS.keys()),
        }
    elif req.source == "scrape":
        background_tasks.add_task(scrape_missing_articles, req.limit, 150, req.concurrency)
        return {
            "status": "started",
            "source": "scrape",
            "limit": req.limit,
            "concurrency": req.concurrency,
            "message": "Scraping full text for articles missing raw_text. Check backend logs for progress.",
        }
    elif req.source == "gdelt":
        background_tasks.add_task(ingest_gdelt_sample, req.limit, req.date)
        return {"status": "started", "source": "gdelt", "limit": req.limit}
    elif req.source == "embedded":
        from app.pipelines.gdelt_ingest import ingest_embedded_sample
        background_tasks.add_task(ingest_embedded_sample, req.limit)
        return {"status": "started", "source": "embedded"}
    return {"error": f"Unknown source: {req.source}"}

@router.get("/status")
async def ingest_status():
    """Simple status check — in future hook into celery."""
    return {"status": "idle"}

@router.get("/sources")
async def list_sources():
    """List available RSS sources for ingestion."""
    return {
        "rss_sources": list(RSS_FEEDS.keys()),
        "total": len(RSS_FEEDS),
    }
