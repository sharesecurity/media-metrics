from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.database import get_db
from app.models import Article, Source
from typing import Optional
import uuid

router = APIRouter()

@router.get("/")
async def search_articles(
    q: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """Full-text search using ilike on title and raw_text."""
    from sqlalchemy import desc
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

@router.get("/semantic")
async def semantic_search(
    q: str,
    limit: int = 10,
    source: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Semantic similarity search using Qdrant vector store.
    Embeds the query with nomic-embed-text, searches Qdrant,
    then enriches results with full article data from PostgreSQL.
    Falls back to full-text search if Qdrant is unavailable.
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    # 1. Generate query embedding via Ollama
    embedding = None
    try:
        from app.services.ollama import get_embedding
        embedding = await get_embedding(q.strip())
    except Exception as e:
        print(f"[SemanticSearch] Embedding error: {e}")

    # 2. Search Qdrant
    if embedding:
        try:
            from app.services.vector_store import search_similar, ensure_collection
            await ensure_collection()
            qdrant_results = await search_similar(embedding, limit=limit, source_filter=source)

            if qdrant_results:
                # Enrich with PostgreSQL data
                article_ids = [uuid.UUID(r.id) for r in qdrant_results]
                db_result = await db.execute(
                    select(Article, Source.name.label("source_name"))
                    .outerjoin(Source, Article.source_id == Source.id)
                    .where(Article.id.in_(article_ids))
                )
                db_rows = {str(row.Article.id): row for row in db_result.all()}

                enriched = []
                for r in qdrant_results:
                    db_row = db_rows.get(str(r.id))
                    payload = r.payload or {}
                    enriched.append({
                        "id": str(r.id),
                        "score": round(r.score, 4),
                        "title": db_row.Article.title if db_row else payload.get("title", ""),
                        "source_name": db_row.source_name if db_row else payload.get("source_name", ""),
                        "published_at": db_row.Article.published_at if db_row else None,
                        "url": db_row.Article.url if db_row else None,
                        "section": db_row.Article.section if db_row else payload.get("section", ""),
                        "political_lean": payload.get("political_lean"),
                        "sentiment_label": payload.get("sentiment_label"),
                        "primary_topic": payload.get("primary_topic"),
                    })
                return {"results": enriched, "method": "semantic", "query": q}

        except Exception as e:
            print(f"[SemanticSearch] Qdrant search error: {e}")

    # 3. Fallback: keyword search
    print("[SemanticSearch] Falling back to keyword search")
    from sqlalchemy import desc
    result = await db.execute(
        select(
            Article.id, Article.title, Article.published_at, Article.url,
            Source.name.label("source_name"), Article.section
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
    return {
        "results": [
            {
                "id": str(r.id),
                "score": None,
                "title": r.title,
                "source_name": r.source_name,
                "published_at": r.published_at,
                "url": r.url,
                "section": r.section,
                "political_lean": None,
                "sentiment_label": None,
                "primary_topic": None,
            }
            for r in rows
        ],
        "method": "keyword_fallback",
        "query": q,
    }
