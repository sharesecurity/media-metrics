from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from app.database import get_db
from app.models import Author, Article, AnalysisResult, Source
from app.services.demographics import infer_demographics, infer_ethnicity_with_confidence
from typing import Optional

router = APIRouter()

@router.get("/")
async def list_authors(db: AsyncSession = Depends(get_db)):
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

@router.get("/comparison")
async def author_comparison(
    source_id: Optional[str] = Query(None),
    min_articles: int = Query(1),
    db: AsyncSession = Depends(get_db),
):
    """
    Return authors with avg political lean across their analyzed articles.
    Useful for side-by-side comparison across authors and outlets.
    """
    import uuid

    # avg lean, article count, analyzed count per author
    q = (
        select(
            Author.id,
            Author.name,
            Author.gender,
            Author.ethnicity,
            Source.name.label("source_name"),
            func.count(Article.id).label("article_count"),
            func.count(AnalysisResult.id).label("analyzed_count"),
            func.avg(AnalysisResult.political_lean).label("avg_lean"),
            func.avg(AnalysisResult.sentiment_score).label("avg_sentiment"),
        )
        .outerjoin(Source, Author.source_id == Source.id)
        .outerjoin(Article, Article.author_id == Author.id)
        .outerjoin(AnalysisResult, AnalysisResult.article_id == Article.id)
        .group_by(Author.id, Author.name, Author.gender, Author.ethnicity, Source.name)
        .having(func.count(Article.id) >= min_articles)
        .order_by(func.avg(AnalysisResult.political_lean))
    )

    if source_id:
        try:
            sid = uuid.UUID(source_id)
            q = q.where(Author.source_id == sid)
        except ValueError:
            pass

    result = await db.execute(q)
    rows = result.all()

    return [
        {
            "id": str(r.id),
            "name": r.name,
            "gender": r.gender,
            "ethnicity": r.ethnicity,
            "source_name": r.source_name,
            "article_count": r.article_count,
            "analyzed_count": r.analyzed_count,
            "avg_lean": round(float(r.avg_lean), 3) if r.avg_lean is not None else None,
            "avg_sentiment": round(float(r.avg_sentiment), 3) if r.avg_sentiment is not None else None,
        }
        for r in rows
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


@router.post("/re-infer-ethnicity")
async def re_infer_all_ethnicity(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Force-rerun ethnicity inference for ALL authors using the full Census
    2010 surname list (162K surnames). Overwrites existing ethnicity values.
    Useful after upgrading from the old ~200-surname lookup to the full dataset.
    """
    result = await db.execute(select(Author).limit(2000))
    authors = result.scalars().all()
    ids = [str(a.id) for a in authors]
    background_tasks.add_task(_do_reinfer_ethnicity, ids)
    return {"status": "started", "count": len(ids)}


async def _do_reinfer_ethnicity(author_ids: list[str]):
    """Re-infer ethnicity for all given authors using the full Census dataset."""
    from app.core.database import AsyncSessionLocal
    import uuid
    updated = 0
    async with AsyncSessionLocal() as db:
        for aid in author_ids:
            try:
                result = await db.execute(
                    select(Author).where(Author.id == uuid.UUID(aid))
                )
                author = result.scalar_one_or_none()
                if not author:
                    continue
                ethnicity, confidence = infer_ethnicity_with_confidence(author.name)
                await db.execute(
                    update(Author)
                    .where(Author.id == uuid.UUID(aid))
                    .values(ethnicity=ethnicity)
                )
                await db.commit()
                updated += 1
                if updated % 10 == 0:
                    print(f"[Re-infer] Updated {updated}/{len(author_ids)} authors…")
            except Exception as e:
                print(f"[Re-infer] Error for {aid}: {e}")
                await db.rollback()
    print(f"[Re-infer] Done — updated ethnicity for {updated} authors")

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
        select(Author, Source.name.label("source_name"))
        .outerjoin(Source, Author.source_id == Source.id)
        .where(Author.id == uuid.UUID(author_id))
    )
    row = result.first()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "Author not found")
    author, source_name = row

    # Count articles
    art_result = await db.execute(
        select(func.count(Article.id)).where(Article.author_id == author.id)
    )
    article_count = art_result.scalar() or 0

    return {
        "id": str(author.id),
        "name": author.name,
        "gender": author.gender,
        "ethnicity": author.ethnicity,
        "source_id": str(author.source_id) if author.source_id else None,
        "source_name": source_name,
        "article_count": article_count,
    }
