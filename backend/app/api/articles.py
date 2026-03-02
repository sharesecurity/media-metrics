from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.core.database import get_db
from app.models.db import Article, Source, Author, Analysis
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter(prefix="/articles", tags=["articles"])

class ArticleCreate(BaseModel):
    source_name: str
    title: str
    url: Optional[str] = None
    content: str
    author_name: Optional[str] = None
    published_at: Optional[str] = None
    section: Optional[str] = None

@router.get("/")
async def list_articles(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=500),
    offset: int = 0,
    source: Optional[str] = None
):
    q = select(Article, Source.name.label("source_name")).join(Source, isouter=True)
    if source:
        q = q.where(Source.name.ilike(f"%{source}%"))
    q = q.order_by(desc(Article.published_at)).limit(limit).offset(offset)
    result = await db.execute(q)
    rows = result.all()
    return [
        {
            "id": str(a.id),
            "title": a.title,
            "url": a.url,
            "published_at": a.published_at,
            "word_count": a.word_count,
            "source": sn,
            "section": a.section,
        }
        for a, sn in rows
    ]

@router.get("/{article_id}")
async def get_article(article_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Article).where(Article.id == uuid.UUID(article_id)))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(404, "Article not found")
    # Get analyses
    analyses_result = await db.execute(select(Analysis).where(Analysis.article_id == article.id))
    analyses = analyses_result.scalars().all()
    return {
        "id": str(article.id),
        "title": article.title,
        "content": article.content,
        "url": article.url,
        "published_at": article.published_at,
        "word_count": article.word_count,
        "section": article.section,
        "analyses": [{"type": a.analysis_type, "result": a.result, "model": a.model_used} for a in analyses]
    }

@router.get("/stats/summary")
async def stats_summary(db: AsyncSession = Depends(get_db)):
    total = await db.execute(select(func.count()).select_from(Article))
    by_source = await db.execute(
        select(Source.name, func.count(Article.id))
        .join(Article, isouter=True)
        .group_by(Source.name)
        .order_by(desc(func.count(Article.id)))
    )
    return {
        "total_articles": total.scalar(),
        "by_source": [{"source": r[0], "count": r[1]} for r in by_source.all()]
    }
