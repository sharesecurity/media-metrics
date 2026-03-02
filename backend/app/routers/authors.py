from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from app.database import get_db
from app.models import Author, Article, Source
from app.services.demographics import infer_demographics

router = APIRouter()

@router.get("/")
async def list_authors(db: AsyncSession = Depends(get_db)):
    # Join with Source to get source name, count articles
    result = await db.execute(
        select(Author, Source.name.label("source_name"))
        .outerjoin(Source, Author.source_id == Source.id)
        .order_by(Author.name)
        .limit(500)
    )
    rows = result.all()
    return [
        {
            "id": str(a.id),
            "name": a.name,
            "gender": a.gender,
            "ethnicity": a.ethnicity,
            "source_id": str(a.source_id) if a.source_id else None,
            "source_name": source_name,
        }
        for a, source_name in rows
    ]

@router.get("/demographics/summary")
async def demographics_summary(db: AsyncSession = Depends(get_db)):
    """Return counts broken down by gender and ethnicity."""
    result = await db.execute(select(Author).limit(500))
    authors = result.scalars().all()

    gender_counts: dict[str, int] = {}
    ethnicity_counts: dict[str, int] = {}
    for a in authors:
        g = a.gender or "unknown"
        e = a.ethnicity or "unknown"
        gender_counts[g] = gender_counts.get(g, 0) + 1
        ethnicity_counts[e] = ethnicity_counts.get(e, 0) + 1

    return {
        "total_authors": len(authors),
        "by_gender": gender_counts,
        "by_ethnicity": ethnicity_counts,
    }

@router.post("/infer-demographics")
async def infer_all_demographics(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Run demographic inference (gender + ethnicity) for all authors that
    don't already have both fields set. Runs in the background.
    """
    result = await db.execute(
        select(Author).where(
            (Author.gender.is_(None)) | (Author.ethnicity.is_(None))
        ).limit(1000)
    )
    authors = result.scalars().all()
    ids = [str(a.id) for a in authors]
    background_tasks.add_task(_do_infer, ids)
    return {"status": "started", "count": len(ids)}

async def _do_infer(author_ids: list[str]):
    from app.core.database import AsyncSessionLocal
    import uuid
    async with AsyncSessionLocal() as db:
        for aid in author_ids:
            try:
                result = await db.execute(
                    select(Author).where(Author.id == uuid.UUID(aid))
                )
                author = result.scalar_one_or_none()
                if not author:
                    continue
                demo = infer_demographics(author.name)
                await db.execute(
                    update(Author)
                    .where(Author.id == uuid.UUID(aid))
                    .values(
                        gender=demo["gender"] or author.gender,
                        ethnicity=demo["ethnicity"] or author.ethnicity,
                    )
                )
                await db.commit()
                print(f"[Demographics] {author.name} → gender={demo['gender']}, ethnicity={demo['ethnicity']}")
            except Exception as e:
                print(f"[Demographics] Error for {aid}: {e}")
                await db.rollback()

@router.get("/{author_id}")
async def get_author(author_id: str, db: AsyncSession = Depends(get_db)):
    import uuid
    result = await db.execute(
        select(Author).where(Author.id == uuid.UUID(author_id))
    )
    author = result.scalar_one_or_none()
    if not author:
        from fastapi import HTTPException
        raise HTTPException(404, "Author not found")

    # Count articles
    art_result = await db.execute(
        select(Article).where(Article.author_id == author.id)
    )
    articles = art_result.scalars().all()

    return {
        "id": str(author.id),
        "name": author.name,
        "gender": author.gender,
        "ethnicity": author.ethnicity,
        "source_id": str(author.source_id) if author.source_id else None,
        "article_count": len(articles),
    }
