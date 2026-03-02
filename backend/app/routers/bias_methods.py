from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import BiasMethod
from pydantic import BaseModel
from typing import Optional
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
