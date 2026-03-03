from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.database import get_db
from app.models import Source, Article, Author, AnalysisResult
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter()

@router.get("/")
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).order_by(Source.name))
    sources = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "domain": s.domain,
            "country": s.country,
            "political_lean": s.political_lean,
        }
        for s in sources
    ]


@router.get("/{source_id}")
async def get_source(source_id: str, db: AsyncSession = Depends(get_db)):
    """Detailed stats for a single source."""
    result = await db.execute(
        select(Source).where(Source.id == uuid.UUID(source_id))
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    sid = source.id

    # Article counts
    counts = await db.execute(
        select(
            func.count(Article.id).label("total"),
            func.count(Article.id).filter(
                (Article.raw_text.isnot(None)) | (Article.minio_key.isnot(None))
            ).label("scraped"),
            func.count(Article.id).filter(
                Article.extra["scrape_failed"].astext == "true"
            ).label("scrape_failed"),
        ).where(Article.source_id == sid)
    )
    c = counts.one()

    # Analysis aggregate
    analysis_agg = await db.execute(
        select(
            func.count(AnalysisResult.id).label("analyzed"),
            func.avg(AnalysisResult.political_lean).label("avg_lean"),
            func.avg(AnalysisResult.sentiment_score).label("avg_sentiment"),
            func.avg(AnalysisResult.reading_level).label("avg_reading_level"),
        )
        .join(Article, AnalysisResult.article_id == Article.id)
        .where(Article.source_id == sid)
    )
    agg = analysis_agg.one()

    def _f(v): return round(float(v), 3) if v is not None else None

    # Top authors
    authors_result = await db.execute(
        select(
            Author.id,
            Author.name,
            Author.gender,
            Author.ethnicity,
            func.count(Article.id).label("article_count"),
        )
        .join(Article, Article.author_id == Author.id)
        .where(Article.source_id == sid)
        .group_by(Author.id, Author.name, Author.gender, Author.ethnicity)
        .order_by(desc(func.count(Article.id)))
        .limit(10)
    )
    authors = authors_result.all()

    # Recent articles with analysis
    latest_analysis = (
        select(
            AnalysisResult.article_id,
            AnalysisResult.political_lean,
            AnalysisResult.sentiment_score,
        )
        .distinct(AnalysisResult.article_id)
        .order_by(AnalysisResult.article_id, desc(AnalysisResult.analyzed_at))
        .subquery()
    )
    recent_result = await db.execute(
        select(
            Article.id, Article.title, Article.url, Article.published_at,
            Article.word_count,
            Author.name.label("author_name"),
            latest_analysis.c.political_lean,
            latest_analysis.c.sentiment_score,
        )
        .outerjoin(Author, Article.author_id == Author.id)
        .outerjoin(latest_analysis, Article.id == latest_analysis.c.article_id)
        .where(Article.source_id == sid)
        .order_by(desc(Article.published_at))
        .limit(20)
    )
    recent = recent_result.all()

    return {
        "id": str(source.id),
        "name": source.name,
        "domain": source.domain,
        "country": source.country,
        "political_lean": source.political_lean,
        "stats": {
            "total": c.total,
            "scraped": c.scraped,
            "scrape_failed": c.scrape_failed,
            "analyzed": agg.analyzed,
            "scrape_rate": round(c.scraped / c.total, 3) if c.total else 0,
            "analysis_rate": round(agg.analyzed / c.scraped, 3) if c.scraped else 0,
        },
        "avg_lean": _f(agg.avg_lean),
        "avg_sentiment": _f(agg.avg_sentiment),
        "avg_reading_level": _f(agg.avg_reading_level),
        "top_authors": [
            {
                "id": str(a.id),
                "name": a.name,
                "gender": a.gender,
                "ethnicity": a.ethnicity,
                "article_count": a.article_count,
            }
            for a in authors
        ],
        "recent_articles": [
            {
                "id": str(r.id),
                "title": r.title,
                "url": r.url,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "word_count": r.word_count,
                "author_name": r.author_name,
                "political_lean": _f(r.political_lean),
                "sentiment_score": _f(r.sentiment_score),
            }
            for r in recent
        ],
    }
