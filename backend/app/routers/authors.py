from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from app.database import get_db
from app.models import Author, Article, AnalysisResult, Source
from app.services.demographics import infer_demographics, infer_ethnicity_with_confidence
from typing import Optional
import uuid as _uuid

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


@router.post("/fix-compound")
async def fix_compound_authors(background_tasks: BackgroundTasks):
    """
    Backfill: find Author records whose name contains multiple people
    (e.g. "Evan Halper, Rachel Siegel") and split them into individual
    Author records.  Articles that pointed to the compound Author are
    re-assigned to the first individual.  The compound record is deleted.
    """
    background_tasks.add_task(_do_fix_compound)
    return {"status": "started"}


async def _do_fix_compound():
    """
    Background task — two-pass cleanup of Author records:
      Pass 1: remove records whose name is an organisation byline
              (e.g. "NPR Washington Desk", "Associated Press").
      Pass 2: split compound names into individual Author records
              (e.g. "Evan Halper, Rachel Siegel" → two rows).
    """
    import re
    from app.core.database import AsyncSessionLocal
    from app.pipelines.gdelt_ingest import split_author_names, get_or_create_author, _is_org_byline

    fixed = 0
    removed_orgs = 0
    skipped = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Author))
        all_authors = result.scalars().all()

        # Pass 1 — remove org-byline authors
        for author in all_authors:
            if not author.name:
                continue
            if _is_org_byline(author.name):
                print(f"[fix-compound] Removing org byline '{author.name}'")
                await db.execute(
                    update(Article).where(Article.author_id == author.id).values(author_id=None)
                )
                await db.execute(delete(Author).where(Author.id == author.id))
                await db.commit()
                removed_orgs += 1

        # Refresh list after deletions
        result = await db.execute(select(Author))
        all_authors = result.scalars().all()

        # Pass 2 — split compound names
        for author in all_authors:
            if not author.name:
                continue
            names = split_author_names(author.name)
            # Only act when there are 2+ valid individual names
            if len(names) < 2:
                skipped += 1
                continue

            print(f"[fix-compound] Splitting '{author.name}' → {names}")

            # Create / fetch individual Author records
            individual_ids = []
            for name in names:
                aid = await get_or_create_author(db, name, author.source_id)
                individual_ids.append(aid)

            first_id = individual_ids[0]

            # Re-point all articles that used the compound author to the first individual
            await db.execute(
                update(Article)
                .where(Article.author_id == author.id)
                .values(author_id=first_id)
            )

            # Delete the compound Author record (no articles point to it now)
            await db.execute(
                delete(Author).where(Author.id == author.id)
            )

            await db.commit()
            fixed += 1

    # Pass 3 — mirror cleanup into the people table
    from app.models import Person, PersonOrganization
    try:
        async with AsyncSessionLocal() as db:
            people_result = await db.execute(select(Person))
            all_people = people_result.scalars().all()
            removed_people = 0
            for person in all_people:
                if not person.full_name:
                    continue
                if _is_org_byline(person.full_name) or len(split_author_names(person.full_name)) >= 2:
                    print(f"[fix-compound] Removing bad person record '{person.full_name}'")
                    await db.execute(
                        delete(PersonOrganization).where(PersonOrganization.person_id == person.id)
                    )
                    await db.execute(delete(Person).where(Person.id == person.id))
                    await db.commit()
                    removed_people += 1
            if removed_people:
                print(f"[fix-compound] Removed {removed_people} bad person records from people table")
    except Exception as e:
        print(f"[fix-compound] people table cleanup error: {e}")

    print(f"[fix-compound] Done — removed {removed_orgs} org bylines, split {fixed} compound authors, skipped {skipped} clean ones")
