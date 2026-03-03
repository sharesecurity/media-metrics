from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models import Article, AnalysisResult, Source, Author
from app.pipelines.bias_analyzer import analyze_article_bias
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid

def _dispatch(article_id: str, analysis_type: str = "full") -> str:
    """
    Dispatch a bias-analysis job.
    Uses Celery if Redis is reachable; falls back to a direct asyncio call
    (wrapped in a BackgroundTask) if Celery is unavailable.
    Returns the Celery task ID if dispatched, else "background".
    """
    try:
        from app.tasks import analyze_article_task
        result = analyze_article_task.delay(article_id, analysis_type)
        return result.id
    except Exception:
        # Redis unreachable — keep the old behaviour so the server still works
        import asyncio, threading
        threading.Thread(
            target=asyncio.run,
            args=(analyze_article_bias(article_id, analysis_type),),
            daemon=True,
        ).start()
        return "background"

router = APIRouter()

class AnalyzeRequest(BaseModel):
    article_id: str
    analysis_type: str = "full"  # full, bias, sentiment, topics

@router.post("/run")
async def run_analysis(
    req: AnalyzeRequest,
    db: AsyncSession = Depends(get_db)
):
    """Trigger analysis on a specific article."""
    article_id = uuid.UUID(req.article_id)
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        return {"error": "Article not found"}

    task_id = _dispatch(str(article.id), req.analysis_type)
    return {"status": "queued", "article_id": req.article_id, "task_id": task_id}

@router.post("/run-all")
async def run_all_unanalyzed(
    limit: int = 500,
    db: AsyncSession = Depends(get_db)
):
    """Queue analysis for unanalyzed articles that have text. Default limit 500.
    Excludes stub articles (word_count < 50) — section pages / bare headlines.
    """
    analyzed_ids = select(AnalysisResult.article_id)
    result = await db.execute(
        select(Article.id)
        .where(~Article.id.in_(analyzed_ids))
        .where(
            (Article.raw_text.is_not(None)) | (Article.minio_key.is_not(None))
        )
        # Skip stub articles — they waste Ollama calls and skew results
        .where(
            (Article.word_count.is_(None)) | (Article.word_count >= 50)
        )
        .limit(limit)
    )
    ids = [str(r.id) for r in result.all()]
    task_ids = [_dispatch(aid, "full") for aid in ids]
    return {"status": "queued", "count": len(ids), "task_ids": task_ids}

@router.get("/results/{article_id}")
async def get_analysis_results(article_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AnalysisResult)
        .where(AnalysisResult.article_id == uuid.UUID(article_id))
        .order_by(AnalysisResult.analyzed_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "type": r.analysis_type,
            "political_lean": r.political_lean,
            "sentiment_score": r.sentiment_score,
            "sentiment_label": r.sentiment_label,
            "subjectivity": r.subjectivity,
            "primary_topic": r.primary_topic,
            "model_used": r.model_used,
            "analyzed_at": r.analyzed_at,
            "raw_analysis": r.raw_analysis,
        }
        for r in rows
    ]

@router.post("/force-reanalyze")
async def force_reanalyze_all(
    db: AsyncSession = Depends(get_db)
):
    """Re-queue ALL articles for analysis (overwrites existing results)."""
    result = await db.execute(select(Article.id).limit(200))
    ids = [str(r.id) for r in result.all()]
    task_ids = [_dispatch(aid, "full") for aid in ids]
    return {"status": "queued", "count": len(ids), "task_ids": task_ids}

@router.post("/rebuild-embeddings")
async def rebuild_qdrant_embeddings(
    db: AsyncSession = Depends(get_db),
):
    """
    Re-generate Qdrant embeddings for all articles that already have analysis results.
    Much faster than force-reanalyze because it skips the LLM step.
    """
    result = await db.execute(
        select(Article.id, AnalysisResult.article_id)
        .join(AnalysisResult, Article.id == AnalysisResult.article_id)
        .distinct(Article.id)
        .limit(200)
    )
    ids = list({str(r[0]) for r in result.all()})
    try:
        from app.tasks import rebuild_embeddings_task
        task = rebuild_embeddings_task.delay(ids)
        return {"status": "started", "count": len(ids), "task_id": task.id}
    except Exception:
        import asyncio, threading
        threading.Thread(target=asyncio.run, args=(_rebuild_embeddings_bg(ids),), daemon=True).start()
        return {"status": "started", "count": len(ids), "task_id": "background"}

async def _rebuild_embeddings_bg(article_ids: list[str]):
    from app.core.database import AsyncSessionLocal
    from app.pipelines.bias_analyzer import _generate_embedding, _upsert_to_qdrant
    from app.models import Source
    async with AsyncSessionLocal() as db:
        for aid in article_ids:
            try:
                result = await db.execute(
                    select(Article, Source.name.label("source_name"))
                    .outerjoin(Source, Article.source_id == Source.id)
                    .where(Article.id == uuid.UUID(aid))
                )
                row = result.one_or_none()
                if not row:
                    continue
                article, source_name = row

                ar = await db.execute(
                    select(AnalysisResult)
                    .where(AnalysisResult.article_id == uuid.UUID(aid))
                    .order_by(AnalysisResult.analyzed_at.desc())
                    .limit(1)
                )
                analysis = ar.scalar_one_or_none()
                if not analysis:
                    continue

                # Get text
                text = article.raw_text or ""
                if article.minio_key and not text:
                    try:
                        from app.services.minio_service import get_article_text
                        text = await get_article_text(article.minio_key) or ""
                    except Exception:
                        pass
                if not text:
                    text = article.title or ""

                embedding = await _generate_embedding(text[:2048])
                if embedding:
                    await _upsert_to_qdrant(aid, embedding, {
                        "title": article.title,
                        "source": source_name,
                        "political_lean": analysis.political_lean,
                        "sentiment": analysis.sentiment_score,
                    })
                    print(f"[Embed] ✓ {article.title[:50]}")
                else:
                    print(f"[Embed] ✗ embedding failed for {aid}")
            except Exception as e:
                print(f"[Embed] Error for {aid}: {e}")

@router.get("/trends")
async def get_trends(
    source_id: Optional[str] = None,
    metric: str = "political_lean",
    db: AsyncSession = Depends(get_db)
):
    """Get trend data for a metric over time, optionally filtered to one source."""
    from sqlalchemy import func
    from app.models import Source

    q = (
        select(
            func.date_trunc('month', Article.published_at).label('month'),
            func.avg(getattr(AnalysisResult, metric)).label('avg_value'),
            func.count().label('count')
        )
        .join(AnalysisResult, Article.id == AnalysisResult.article_id)
        .where(Article.published_at.isnot(None))
        .group_by('month')
        .order_by('month')
    )
    if source_id:
        q = q.where(Article.source_id == uuid.UUID(source_id))

    result = await db.execute(q)
    rows = result.all()
    return [
        {"month": r.month.isoformat() if r.month else None, "value": r.avg_value, "count": r.count}
        for r in rows
    ]

@router.get("/trends/by-source")
async def get_trends_by_source(
    metric: str = "political_lean",
    db: AsyncSession = Depends(get_db)
):
    """
    Trend data grouped by both month and source — one data point per source per month.
    Use this to draw a multi-line chart with one line per news outlet.
    """
    from sqlalchemy import func
    from app.models import Source

    result = await db.execute(
        select(
            func.date_trunc('month', Article.published_at).label('month'),
            Source.name.label('source_name'),
            func.avg(getattr(AnalysisResult, metric)).label('avg_value'),
            func.count().label('count')
        )
        .join(AnalysisResult, Article.id == AnalysisResult.article_id)
        .join(Source, Article.source_id == Source.id)
        .where(Article.published_at.isnot(None))
        .group_by('month', Source.name)
        .order_by('month', Source.name)
    )
    rows = result.all()
    return [
        {
            "month": r.month.isoformat() if r.month else None,
            "source_name": r.source_name,
            "value": float(r.avg_value) if r.avg_value is not None else None,
            "count": r.count,
        }
        for r in rows
    ]


@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """
    Poll the status of a Celery task by ID.
    Statuses: PENDING | STARTED | SUCCESS | FAILURE | RETRY | REVOKED
    """
    if task_id == "background":
        return {"task_id": task_id, "status": "BACKGROUND", "result": None}
    try:
        from celery.result import AsyncResult
        from app.worker import celery_app
        result = AsyncResult(task_id, app=celery_app)
        return {
            "task_id": task_id,
            "status": result.status,
            "result": str(result.result) if result.ready() else None,
        }
    except Exception as exc:
        return {"task_id": task_id, "status": "UNKNOWN", "error": str(exc)}


@router.get("/queue-stats")
async def queue_stats():
    """
    Live counts of active and reserved tasks from all workers, plus raw Redis
    queue depth (true backlog regardless of prefetch settings).
    Returns zeroes if no workers are connected.
    """
    import os
    redis_backlog = 0
    try:
        import redis as _redis
        r = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        redis_backlog = r.llen("default") or 0
    except Exception:
        pass

    try:
        from app.worker import celery_app
        inspect = celery_app.control.inspect(timeout=2.0)
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        return {
            "workers": list(active.keys()),
            "active": sum(len(v) for v in active.values()),
            "queued": sum(len(v) for v in reserved.values()),
            "redis_backlog": redis_backlog,
        }
    except Exception as exc:
        return {"workers": [], "active": 0, "queued": 0, "redis_backlog": redis_backlog, "error": str(exc)}


@router.get("/source-summary")
async def source_summary(db: AsyncSession = Depends(get_db)):
    """
    Per-source aggregate stats from analysis results.
    Returns avg lean, avg sentiment, avg reading level, article count, analyzed count.
    """
    result = await db.execute(
        select(
            Source.id,
            Source.name,
            Source.political_lean.label("baseline_lean"),
            func.count(Article.id).label("article_count"),
            func.count(AnalysisResult.id).label("analyzed_count"),
            func.avg(AnalysisResult.political_lean).label("avg_lean"),
            func.avg(AnalysisResult.sentiment_score).label("avg_sentiment"),
            func.avg(AnalysisResult.reading_level).label("avg_reading_level"),
            func.avg(AnalysisResult.subjectivity).label("avg_subjectivity"),
        )
        .outerjoin(Article, Article.source_id == Source.id)
        .outerjoin(AnalysisResult, AnalysisResult.article_id == Article.id)
        .group_by(Source.id, Source.name, Source.political_lean)
        .order_by(func.avg(AnalysisResult.political_lean))
    )
    rows = result.all()

    def _f(v): return round(float(v), 3) if v is not None else None

    return [
        {
            "id": str(r.id),
            "name": r.name,
            "baseline_lean": r.baseline_lean,
            "article_count": r.article_count,
            "analyzed_count": r.analyzed_count,
            "avg_lean": _f(r.avg_lean),
            "avg_sentiment": _f(r.avg_sentiment),
            "avg_reading_level": _f(r.avg_reading_level),
            "avg_subjectivity": _f(r.avg_subjectivity),
        }
        for r in rows
    ]


@router.get("/by-demographic")
async def by_demographic(
    group_by: str = "gender",  # gender | ethnicity
    db: AsyncSession = Depends(get_db),
):
    """Avg political lean and sentiment grouped by author gender or ethnicity."""
    if group_by not in ("gender", "ethnicity"):
        return {"error": "group_by must be 'gender' or 'ethnicity'"}

    group_col = Author.gender if group_by == "gender" else Author.ethnicity

    result = await db.execute(
        select(
            group_col.label("group_value"),
            func.count(Article.id).label("article_count"),
            func.count(AnalysisResult.id).label("analyzed_count"),
            func.avg(AnalysisResult.political_lean).label("avg_lean"),
            func.avg(AnalysisResult.sentiment_score).label("avg_sentiment"),
            func.avg(AnalysisResult.reading_level).label("avg_reading_level"),
        )
        .join(Article, Article.author_id == Author.id)
        .join(AnalysisResult, AnalysisResult.article_id == Article.id)
        .group_by(group_col)
        .order_by(func.avg(AnalysisResult.political_lean))
    )
    rows = result.all()

    def _f(v): return round(float(v), 3) if v is not None else None

    return [
        {
            "group": r.group_value or "unknown",
            "article_count": r.article_count,
            "analyzed_count": r.analyzed_count,
            "avg_lean": _f(r.avg_lean),
            "avg_sentiment": _f(r.avg_sentiment),
            "avg_reading_level": _f(r.avg_reading_level),
        }
        for r in rows
    ]


@router.get("/by-demographic/by-source")
async def by_demographic_by_source(
    group_by: str = "gender",
    db: AsyncSession = Depends(get_db),
):
    """
    Cross-dimensional: avg political lean grouped by author demographic AND outlet.
    E.g. male vs female authors at each news outlet.
    """
    if group_by not in ("gender", "ethnicity"):
        return {"error": "group_by must be 'gender' or 'ethnicity'"}

    group_col = Author.gender if group_by == "gender" else Author.ethnicity

    result = await db.execute(
        select(
            Source.name.label("source_name"),
            group_col.label("group_value"),
            func.count(Article.id).label("article_count"),
            func.avg(AnalysisResult.political_lean).label("avg_lean"),
            func.avg(AnalysisResult.sentiment_score).label("avg_sentiment"),
        )
        .join(Article, Article.author_id == Author.id)
        .join(Source, Article.source_id == Source.id)
        .join(AnalysisResult, AnalysisResult.article_id == Article.id)
        .where(group_col.isnot(None))
        .group_by(Source.name, group_col)
        .order_by(Source.name, group_col)
    )
    rows = result.all()

    def _f(v): return round(float(v), 3) if v is not None else None

    return [
        {
            "source_name": r.source_name,
            "group": r.group_value,
            "article_count": r.article_count,
            "avg_lean": _f(r.avg_lean),
            "avg_sentiment": _f(r.avg_sentiment),
        }
        for r in rows
    ]
