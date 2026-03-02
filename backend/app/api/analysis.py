from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.db import Article, Analysis
from app.services.bias import analyze_bias
from app.services.ollama import get_embedding
from app.services.vector_store import upsert_article, search_similar
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter(prefix="/analyze", tags=["analysis"])

class AnalyzeRequest(BaseModel):
    article_id: str
    method: str = "combined"  # lexical | llm | combined

class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    source_filter: Optional[str] = None

@router.post("/bias")
async def run_bias_analysis(req: AnalyzeRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Article).where(Article.id == uuid.UUID(req.article_id)))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(404, "Article not found")

    bias_result = await analyze_bias(article.title, article.content or "", method=req.method)

    analysis = Analysis(
        article_id=article.id,
        analysis_type="bias",
        model_used=f"ollama/{req.method}",
        result=bias_result
    )
    db.add(analysis)
    await db.commit()
    return {"article_id": req.article_id, "bias_analysis": bias_result}

@router.post("/embed")
async def embed_article(article_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Article).where(Article.id == uuid.UUID(article_id)))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(404, "Article not found")

    text = f"{article.title}\n\n{(article.content or '')[:4000]}"
    embedding = await get_embedding(text)
    await upsert_article(str(article.id), embedding, {
        "title": article.title,
        "url": article.url,
        "source_id": article.source_id
    })
    return {"status": "embedded", "vector_dim": len(embedding)}

@router.post("/search")
async def semantic_search(req: SearchRequest):
    embedding = await get_embedding(req.query)
    results = await search_similar(embedding, limit=req.limit, source_filter=req.source_filter)
    return [
        {"id": r.id, "score": r.score, "title": r.payload.get("title"), "url": r.payload.get("url")}
        for r in results
    ]
