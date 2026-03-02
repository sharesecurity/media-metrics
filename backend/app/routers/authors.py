from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models import Author

router = APIRouter()

@router.get("/")
async def list_authors(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Author).order_by(Author.name).limit(200))
    authors = result.scalars().all()
    return [
        {"id": str(a.id), "name": a.name, "gender": a.gender}
        for a in authors
    ]
