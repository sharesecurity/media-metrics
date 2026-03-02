from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, update
from app.database import get_db
from app.models import Article, Source, Author, AnalysisResult
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

router = APIRouter()

class ArticleOut(BaseModel):
    id: str
    title: str
    url: Optional[str]
    published_at: Optional[datetime]
    section: Optional[str]
    word_count: Optional[int]
    source_name: Optional[str]
    author_name: Optional[str]
    sentiment_score: Optional[float]
    political_lean: Optional[float]

    class Config:
        from_attributes = True

@router.get("/", response_model=list[ArticleOut])
async def list_articles(
    skip: int = 0,
    limit: int = 50,
    source_id: Optional[str] = None,
    section: Optional[str] = None,
    author_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    # Use a subquery to get only the latest analysis result per article
    latest_analysis = (
        select(
            AnalysisResult.article_id,
            AnalysisResult.sentiment_score,
            AnalysisResult.political_lean,
        )
        .distinct(AnalysisResult.article_id)
        .order_by(AnalysisResult.article_id, desc(AnalysisResult.analyzed_at))
        .subquery()
    )
    q = (
        select(
            Article.id, Article.title, Article.url, Article.published_at,
            Article.section, Article.word_count,
            Source.name.label("source_name"),
            Author.name.label("author_name"),
            latest_analysis.c.sentiment_score,
            latest_analysis.c.political_lean,
        )
        .outerjoin(Source, Article.source_id == Source.id)
        .outerjoin(Author, Article.author_id == Author.id)
        .outerjoin(latest_analysis, Article.id == latest_analysis.c.article_id)
        .order_by(desc(Article.published_at))
        .offset(skip)
        .limit(limit)
    )
    if source_id:
        q = q.where(Article.source_id == uuid.UUID(source_id))
    if section:
        q = q.where(Article.section == section)
    if author_id:
        q = q.where(Article.author_id == uuid.UUID(author_id))

    result = await db.execute(q)
    rows = result.all()
    return [ArticleOut(
        id=str(r.id), title=r.title, url=r.url,
        published_at=r.published_at, section=r.section,
        word_count=r.word_count, source_name=r.source_name,
        author_name=r.author_name, sentiment_score=r.sentiment_score,
        political_lean=r.political_lean
    ) for r in rows]

@router.get("/stats")
async def article_stats(db: AsyncSession = Depends(get_db)):
    total = await db.scalar(select(func.count()).select_from(Article))
    analyzed = await db.scalar(
        select(func.count(func.distinct(AnalysisResult.article_id))).select_from(AnalysisResult)
    )
    by_source = await db.execute(
        select(Source.name, func.count(Article.id).label("count"))
        .join(Article, Article.source_id == Source.id)
        .group_by(Source.name)
        .order_by(desc("count"))
    )
    return {
        "total_articles": total,
        "analyzed_articles": analyzed,
        "by_source": [{"source": r.name, "count": r.count} for r in by_source]
    }

@router.post("/migrate-to-minio")
async def migrate_to_minio(
    background_tasks: BackgroundTasks,
    limit: int = 500,
    db: AsyncSession = Depends(get_db)
):
    """
    Batch migrate article raw_text from Postgres into MinIO.
    Sets minio_key on each article and clears raw_text from Postgres.
    Runs in background. Safe to call multiple times (skips already-migrated).
    """
    result = await db.execute(
        select(Article.id)
        .where(Article.raw_text.isnot(None))
        .where(Article.minio_key.is_(None))
        .limit(limit)
    )
    ids = [str(r.id) for r in result.all()]
    background_tasks.add_task(_do_migrate, ids)
    return {"status": "started", "count": len(ids)}

async def _do_migrate(article_ids: list[str]):
    from app.services.minio_service import store_article_text, ensure_bucket
    from app.core.database import AsyncSessionLocal

    await ensure_bucket()
    async with AsyncSessionLocal() as db:
        for article_id in article_ids:
            try:
                result = await db.execute(select(Article).where(Article.id == uuid.UUID(article_id)))
                article = result.scalar_one_or_none()
                if not article or not article.raw_text:
                    continue
                key = await store_article_text(article_id, article.raw_text)
                if key:
                    await db.execute(
                        update(Article)
                        .where(Article.id == uuid.UUID(article_id))
                        .values(minio_key=key, raw_text=None)
                    )
                    await db.commit()
            except Exception as e:
                print(f"[Migrate] Error for {article_id}: {e}")
                await db.rollback()

@router.get("/{article_id}")
async def get_article(article_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Article)
        .where(Article.id == uuid.UUID(article_id))
    )
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(404, "Article not found")

    # Fetch source and author names
    source_name = None
    author_name = None
    if article.source_id:
        sr = await db.execute(select(Source).where(Source.id == article.source_id))
        src = sr.scalar_one_or_none()
        source_name = src.name if src else None
    if article.author_id:
        ar = await db.execute(select(Author).where(Author.id == article.author_id))
        auth = ar.scalar_one_or_none()
        author_name = auth.name if auth else None

    analysis = await db.execute(
        select(AnalysisResult).where(AnalysisResult.article_id == article.id)
    )
    analyses = analysis.scalars().all()

    # Fetch text: MinIO first, fall back to Postgres raw_text
    text = article.raw_text
    if article.minio_key and not text:
        try:
            from app.services.minio_service import get_article_text
            text = await get_article_text(article.minio_key)
        except Exception as e:
            print(f"[Articles] MinIO fetch failed: {e}")

    return {
        "id": str(article.id),
        "title": article.title,
        "url": article.url,
        "raw_text": text,
        "minio_key": article.minio_key,
        "published_at": article.published_at,
        "section": article.section,
        "word_count": article.word_count,
        "tags": article.tags,
        "source_name": source_name,
        "author_id": str(article.author_id) if article.author_id else None,
        "author_name": author_name,
        "analyses": [
            {
                "type": a.analysis_type,
                "political_lean": a.political_lean,
                "sentiment_score": a.sentiment_score,
                "sentiment_label": a.sentiment_label,
                "subjectivity": a.subjectivity,
                "reading_level": a.reading_level,
                "primary_topic": a.primary_topic,
                "raw_analysis": a.raw_analysis,
                "analyzed_at": a.analyzed_at,
                "model_used": a.model_used,
            }
            for a in analyses
        ]
    }
