from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import BiasMethod, Article, AnalysisResult
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import uuid

router = APIRouter()


class BiasMethodCreate(BaseModel):
    name: str
    description: Optional[str] = None
    prompt_template: Optional[str] = None
    is_active: bool = True


class BiasMethodUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    prompt_template: Optional[str] = None
    is_active: Optional[bool] = None


def _serialize(m: BiasMethod) -> dict:
    return {
        "id": str(m.id),
        "name": m.name,
        "description": m.description,
        "prompt_template": m.prompt_template,
        "is_active": m.is_active,
        "created_at": m.created_at,
        "modified_at": m.modified_at,
    }


@router.get("/")
async def list_bias_methods(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BiasMethod).order_by(BiasMethod.name))
    return [_serialize(m) for m in result.scalars().all()]


@router.get("/{method_id}")
async def get_bias_method(method_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BiasMethod).where(BiasMethod.id == uuid.UUID(method_id)))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Bias method not found")
    return _serialize(m)


@router.post("/")
async def create_bias_method(body: BiasMethodCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    m = BiasMethod(
        name=body.name,
        description=body.description,
        prompt_template=body.prompt_template,
        is_active=body.is_active,
        created_at=now,
        modified_at=now,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _serialize(m)


@router.put("/{method_id}")
async def update_bias_method(
    method_id: str, body: BiasMethodUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(BiasMethod).where(BiasMethod.id == uuid.UUID(method_id)))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Bias method not found")

    if body.name is not None:
        m.name = body.name
    if body.description is not None:
        m.description = body.description
    if body.prompt_template is not None:
        m.prompt_template = body.prompt_template
    if body.is_active is not None:
        m.is_active = body.is_active
    m.modified_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(m)
    return _serialize(m)


@router.delete("/{method_id}")
async def delete_bias_method(method_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BiasMethod).where(BiasMethod.id == uuid.UUID(method_id)))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Bias method not found")
    await db.delete(m)
    await db.commit()
    return {"status": "deleted", "id": method_id}


@router.post("/{method_id}/toggle")
async def toggle_bias_method(method_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BiasMethod).where(BiasMethod.id == uuid.UUID(method_id)))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Bias method not found")
    m.is_active = not m.is_active
    m.modified_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(m)
    return _serialize(m)


class MultiCompareRequest(BaseModel):
    article_id: str
    method_ids: Optional[List[str]] = None  # None = all active methods

@router.post("/compare")
async def multi_method_compare(
    req: MultiCompareRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Run multiple bias methods on a single article and return all results side-by-side.
    Each method uses its custom prompt_template if set, otherwise the default prompt.
    Calls Ollama synchronously (no background task) so results return immediately.
    """
    # Get article
    art_result = await db.execute(select(Article).where(Article.id == uuid.UUID(req.article_id)))
    article = art_result.scalar_one_or_none()
    if not article:
        raise HTTPException(404, "Article not found")

    # Get article text
    text = article.raw_text or ""
    if article.minio_key and not text:
        try:
            from app.services.minio_service import get_article_text
            text = await get_article_text(article.minio_key) or ""
        except Exception:
            pass
    if not text:
        text = article.title or ""

    # Get methods to run
    if req.method_ids:
        method_q = await db.execute(
            select(BiasMethod).where(BiasMethod.id.in_([uuid.UUID(mid) for mid in req.method_ids]))
        )
    else:
        method_q = await db.execute(
            select(BiasMethod).where(BiasMethod.is_active == True)
        )
    methods = method_q.scalars().all()
    if not methods:
        raise HTTPException(400, "No active bias methods found")

    # Run each method
    from app.core.config import settings
    from app.pipelines.bias_analyzer import parse_json_from_llm, BIAS_PROMPT
    import httpx
    results = []
    truncated = text[:3000]

    for method in methods:
        prompt = (method.prompt_template or BIAS_PROMPT) + truncated
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                resp = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json={
                        "model": settings.ollama_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                    }
                )
            if resp.status_code == 200:
                raw = resp.json().get("message", {}).get("content", "")
                parsed = parse_json_from_llm(raw)
            else:
                parsed = {"error": f"Ollama {resp.status_code}"}
        except Exception as e:
            parsed = {"error": str(e)}

        results.append({
            "method_id": str(method.id),
            "method_name": method.name,
            "political_lean": parsed.get("political_lean"),
            "confidence": parsed.get("confidence"),
            "primary_topic": parsed.get("primary_topic"),
            "framing_notes": parsed.get("framing_notes"),
            "key_indicators": parsed.get("key_indicators", []),
            "error": parsed.get("error"),
        })

    return {
        "article_id": req.article_id,
        "article_title": article.title,
        "methods_run": len(results),
        "results": results,
    }

