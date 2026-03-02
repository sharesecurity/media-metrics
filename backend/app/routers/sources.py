from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Source
from pydantic import BaseModel
from typing import Optional

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
