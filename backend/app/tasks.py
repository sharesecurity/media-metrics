"""
Celery tasks for Media Metrics.

Each task is a sync wrapper around an async pipeline function.
asyncio.run() is safe here because Celery workers run in their own processes
and each task gets a fresh event loop.
"""
import asyncio
from app.worker import celery_app


@celery_app.task(
    bind=True,
    name="app.tasks.analyze_article",
    max_retries=2,
    default_retry_delay=30,
)
def analyze_article_task(self, article_id: str, analysis_type: str = "full"):
    """
    Run bias analysis on a single article.
    Calls the async pipeline via asyncio.run().
    Retries up to 2 times on failure (30s delay).
    """
    try:
        from app.pipelines.bias_analyzer import analyze_article_bias
        asyncio.run(analyze_article_bias(article_id, analysis_type))
        return {"status": "done", "article_id": article_id}
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.tasks.scheduled_rss_ingest",
)
def scheduled_rss_ingest():
    """
    Celery Beat scheduled task: fetch RSS feeds then dispatch analysis
    for any new articles that don't yet have results.
    Runs every 6 hours (configured in worker.py beat_schedule).
    """
    async def _run():
        from app.pipelines.rss_ingest import ingest_rss_feeds
        from app.core.database import AsyncSessionLocal
        from app.models import Article, AnalysisResult
        from sqlalchemy import select

        print("[Beat] Starting scheduled RSS ingest…")
        await ingest_rss_feeds(limit=10)  # up to 10 articles per outlet

        async with AsyncSessionLocal() as db:
            analyzed_ids = select(AnalysisResult.article_id)
            result = await db.execute(
                select(Article.id).where(~Article.id.in_(analyzed_ids)).limit(200)
            )
            ids = [str(r.id) for r in result.all()]

        print(f"[Beat] Dispatching analysis for {len(ids)} unanalyzed articles")
        for aid in ids:
            analyze_article_task.delay(aid, "full")

        return len(ids)

    count = asyncio.run(_run())
    return {"status": "done", "queued_analysis": count}


@celery_app.task(
    bind=True,
    name="app.tasks.rebuild_embeddings",
    max_retries=1,
    default_retry_delay=60,
)
def rebuild_embeddings_task(self, article_ids: list):
    """
    Rebuild Qdrant embeddings for a list of already-analyzed articles.
    Skips the LLM step — much faster than full re-analysis.
    """
    try:
        from app.routers.analysis import _rebuild_embeddings_bg
        asyncio.run(_rebuild_embeddings_bg(article_ids))
        return {"status": "done", "count": len(article_ids)}
    except Exception as exc:
        raise self.retry(exc=exc)
