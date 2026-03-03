"""
Entity Graph API — organizations, people, and seeding endpoints.

Seeding (POST /api/entities/seed) creates Organization and Person records
from existing sources/authors data and wires up the bridge FK columns.
"""
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.database import get_db
from app.models import (
    Source, Author, Organization, Person,
    Article, AnalysisResult, PersonOrganization,
)
import re
import uuid

router = APIRouter()


# ── Seeding ───────────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Convert a name to a url-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    return s[:80]


async def _seed_entities(db: AsyncSession) -> dict:
    """
    One-time seeding: create Organization records from sources and
    Person records from authors, then link them via bridge FK columns.
    Returns counts of created/linked records.
    """
    stats = {"orgs_created": 0, "orgs_linked": 0, "people_created": 0, "people_linked": 0}

    # ── Seed organizations from sources ──────────────────────────────────────
    sources_result = await db.execute(
        select(Source).where(Source.org_id.is_(None))
    )
    sources = sources_result.scalars().all()

    for src in sources:
        # Check if organization already exists by name or domain
        existing = await db.execute(
            select(Organization).where(
                (Organization.name == src.name) |
                (Organization.domain == src.domain)
            )
        )
        org = existing.scalar_one_or_none()

        if not org:
            slug = _slugify(src.name)
            # Ensure slug uniqueness
            slug_check = await db.execute(
                select(Organization).where(Organization.slug == slug)
            )
            if slug_check.scalar_one_or_none():
                slug = slug + "-" + str(src.id)[:8]

            org = Organization(
                name=src.name,
                slug=slug,
                org_type="publisher",
                domain=src.domain,
                country=src.country or "US",
                political_lean=src.political_lean,
            )
            db.add(org)
            await db.flush()  # get org.id
            stats["orgs_created"] += 1

        # Link source → organization
        src.org_id = org.id
        stats["orgs_linked"] += 1

    await db.commit()

    # ── Seed people from authors ──────────────────────────────────────────────
    authors_result = await db.execute(
        select(Author).where(Author.person_id.is_(None))
    )
    authors = authors_result.scalars().all()

    for author in authors:
        # Check if person already exists by full_name
        existing = await db.execute(
            select(Person).where(Person.full_name == author.name)
        )
        person = existing.scalar_one_or_none()

        if not person:
            slug = _slugify(author.name)
            slug_check = await db.execute(
                select(Person).where(Person.slug == slug)
            )
            if slug_check.scalar_one_or_none():
                slug = slug + "-" + str(author.id)[:8]

            person = Person(
                full_name=author.name,
                slug=slug,
                gender=author.gender,
                ethnicity=author.ethnicity,
                byline_variants=[author.name],
            )
            db.add(person)
            await db.flush()
            stats["people_created"] += 1

            # If author has a source, create a person_organization entry
            if author.source_id:
                src_result = await db.execute(
                    select(Source).where(Source.id == author.source_id)
                )
                src = src_result.scalar_one_or_none()
                if src and src.org_id:
                    affiliation = PersonOrganization(
                        person_id=person.id,
                        org_id=src.org_id,
                        role="reporter",
                        confidence=0.8,
                        source="author_record",
                    )
                    db.add(affiliation)

        # Link author → person
        author.person_id = person.id
        stats["people_linked"] += 1

    await db.commit()
    return stats


@router.post("/seed")
async def seed_entities(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Seed Organization and Person records from existing sources/authors.
    Only processes records not yet linked (idempotent).
    """
    stats = await _seed_entities(db)
    return {
        "status": "ok",
        "message": "Seeding complete",
        **stats,
    }


# ── Organizations ─────────────────────────────────────────────────────────────

@router.get("/organizations")
async def list_organizations(
    org_type: str = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Organization).order_by(Organization.name)
    if org_type:
        q = q.where(Organization.org_type == org_type)
    result = await db.execute(q)
    orgs = result.scalars().all()
    return [_org_dict(o) for o in orgs]


@router.get("/organizations/{org_id}")
async def get_organization(org_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Organization).where(Organization.id == uuid.UUID(org_id))
    )
    org = result.scalar_one_or_none()
    if not org:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Organization not found")

    # Count articles published by sources linked to this org
    articles_result = await db.execute(
        select(func.count(Article.id))
        .join(Source, Article.source_id == Source.id)
        .where(Source.org_id == org.id)
    )
    article_count = articles_result.scalar() or 0

    # Get avg political lean
    lean_result = await db.execute(
        select(func.avg(AnalysisResult.political_lean))
        .join(Article, AnalysisResult.article_id == Article.id)
        .join(Source, Article.source_id == Source.id)
        .where(Source.org_id == org.id)
    )
    avg_lean = lean_result.scalar()

    # Get people affiliated with this org
    people_result = await db.execute(
        select(Person, PersonOrganization)
        .join(PersonOrganization, Person.id == PersonOrganization.person_id)
        .where(PersonOrganization.org_id == org.id)
        .order_by(PersonOrganization.valid_from.desc().nullsfirst())
        .limit(50)
    )
    people_rows = people_result.all()

    return {
        **_org_dict(org),
        "article_count": article_count,
        "avg_political_lean": round(avg_lean, 3) if avg_lean is not None else None,
        "people": [
            {
                **_person_dict(p),
                "role": po.role,
                "beat": po.beat,
                "valid_from": po.valid_from.isoformat() if po.valid_from else None,
                "valid_to": po.valid_to.isoformat() if po.valid_to else None,
                "confidence": po.confidence,
            }
            for p, po in people_rows
        ],
    }


# ── People ────────────────────────────────────────────────────────────────────

@router.get("/people")
async def list_people(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Person).order_by(Person.full_name).limit(limit).offset(offset)
    )
    people = result.scalars().all()
    total_result = await db.execute(select(func.count(Person.id)))
    total = total_result.scalar() or 0
    return {"total": total, "people": [_person_dict(p) for p in people]}


@router.get("/people/{person_id}")
async def get_person(person_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Person).where(Person.id == uuid.UUID(person_id))
    )
    person = result.scalar_one_or_none()
    if not person:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Person not found")

    # Career history
    career_result = await db.execute(
        select(PersonOrganization, Organization)
        .join(Organization, PersonOrganization.org_id == Organization.id)
        .where(PersonOrganization.person_id == person.id)
        .order_by(PersonOrganization.valid_from.asc().nullslast())
    )
    career_rows = career_result.all()

    # Article stats (via author link)
    author_result = await db.execute(
        select(Author).where(Author.person_id == person.id)
    )
    authors = author_result.scalars().all()
    author_ids = [a.id for a in authors]

    article_count = 0
    avg_lean = None
    if author_ids:
        ac_result = await db.execute(
            select(func.count(Article.id)).where(Article.author_id.in_(author_ids))
        )
        article_count = ac_result.scalar() or 0

        lean_result = await db.execute(
            select(func.avg(AnalysisResult.political_lean))
            .join(Article, AnalysisResult.article_id == Article.id)
            .where(Article.author_id.in_(author_ids))
        )
        avg_lean = lean_result.scalar()

    return {
        **_person_dict(person),
        "article_count": article_count,
        "avg_political_lean": round(avg_lean, 3) if avg_lean is not None else None,
        "career": [
            {
                "org_id": str(po.org_id),
                "org_name": org.name,
                "org_slug": org.slug,
                "role": po.role,
                "beat": po.beat,
                "valid_from": po.valid_from.isoformat() if po.valid_from else None,
                "valid_to": po.valid_to.isoformat() if po.valid_to else None,
                "confidence": po.confidence,
                "source": po.source,
            }
            for po, org in career_rows
        ],
        "linked_author_ids": [str(a.id) for a in authors],
    }


# ── Provenance Summary ────────────────────────────────────────────────────────

@router.get("/provenance/summary")
async def provenance_summary(db: AsyncSession = Depends(get_db)):
    """Aggregate provenance stats: how many articles attributed to each wire service."""
    result = await db.execute(
        select(
            Organization.name,
            Organization.slug,
            func.count(text("article_provenance.id")).label("article_count"),
            func.avg(text("article_provenance.confidence")).label("avg_confidence"),
        )
        .join(text("article_provenance"), text("article_provenance.wire_service_id = organizations.id"))
        .group_by(Organization.id, Organization.name, Organization.slug)
        .order_by(func.count(text("article_provenance.id")).desc())
    )
    rows = result.all()
    return [
        {
            "org_name": r.name,
            "org_slug": r.slug,
            "article_count": r.article_count,
            "avg_confidence": round(r.avg_confidence, 3) if r.avg_confidence else None,
        }
        for r in rows
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _org_dict(o: Organization) -> dict:
    return {
        "id": str(o.id),
        "name": o.name,
        "slug": o.slug,
        "org_type": o.org_type,
        "domain": o.domain,
        "country": o.country,
        "political_lean": o.political_lean,
        "founding_year": o.founding_year,
        "wikipedia_url": o.wikipedia_url,
    }


def _person_dict(p: Person) -> dict:
    return {
        "id": str(p.id),
        "full_name": p.full_name,
        "slug": p.slug,
        "gender": p.gender,
        "ethnicity": p.ethnicity,
        "birth_year": p.birth_year,
        "wikipedia_url": p.wikipedia_url,
        "byline_variants": p.byline_variants or [],
    }
