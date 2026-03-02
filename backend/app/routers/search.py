from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.database import get_db
from app.models import Article, Source, Author
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

@router.get("/")
async def search_articles(
    q: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """Full-text search using pg_trgm similarity on title."""
    from sqlalchemy import func, desc
    result = await db.execute(
        select(
            Article.id, Article.title, Article.published_at, Article.url,
            Source.name.label("source_name")
        )
        .outerjoin(Source, Article.source_id == Source.id)
        .where(
            or_(
                Article.title.ilike(f"%{q}%"),
                Article.raw_text.ilike(f"%{q}%"),
            )
        )
        .order_by(desc(Article.published_at))
        .limit(limit)
    )
    rows = result.all()
    return [
        {"id": str(r.id), "title": r.title, "published_at": r.published_at,
         "url": r.url, "source_name": r.source_name}
        for r in rows
    ]
