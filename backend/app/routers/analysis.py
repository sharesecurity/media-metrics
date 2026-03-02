from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Article, AnalysisResult
from app.pipelines.bias_analyzer import analyze_article_bias
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid

router = APIRouter()

class AnalyzeRequest(BaseModel):
    article_id: str
    analysis_type: str = "full"  # full, bias, sentiment, topics

@router.post("/run")
async def run_analysis(
    req: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Trigger analysis on a specific article."""
    article_id = uuid.UUID(req.article_id)
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        return {"error": "Article not found"}

    background_tasks.add_task(analyze_article_bias, str(article.id), req.analysis_type)
    return {"status": "queued", "article_id": req.article_id}

@router.post("/run-all")
async def run_all_unanalyzed(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Queue analysis for all articles that haven't been analyzed yet."""
    analyzed_ids = select(AnalysisResult.article_id)
    result = await db.execute(
        select(Article.id).where(~Article.id.in_(analyzed_ids)).limit(100)
    )
    ids = [str(r.id) for r in result.all()]
    for aid in ids:
        background_tasks.add_task(analyze_article_bias, aid, "full")
    return {"status": "queued", "count": len(ids)}

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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Re-queue ALL articles for analysis (overwrites existing results)."""
    result = await db.execute(select(Article.id).limit(200))
    ids = [str(r.id) for r in result.all()]
    for aid in ids:
        background_tasks.add_task(analyze_article_bias, aid, "full")
    return {"status": "queued", "count": len(ids)}

@router.post("/rebuild-embeddings")
async def rebuild_qdrant_embeddings(
    background_tasks: BackgroundTasks,
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
    background_tasks.add_task(_rebuild_embeddings_bg, ids)
    return {"status": "started", "count": len(ids)}

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
