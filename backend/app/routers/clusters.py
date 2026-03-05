"""
Story Clusters API

POST /run     — trigger clustering job
GET  /        — list all clusters (sorted by article_count desc)
GET  /{id}    — cluster detail with member articles
"""
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.database import get_db
from app.models import StoryCluster, StoryClusterArticle, Article, Source, AnalysisResult
import uuid

router = APIRouter()


@router.post("/run")
async def run_clustering(
    background_tasks: BackgroundTasks,
    similarity_threshold: float = 0.78,
    days_window: int = 5,
    min_cluster_size: int = 2,
):
    """
    Trigger story clustering in the background.
    Clears and rebuilds all cluster data.
    """
    background_tasks.add_task(
        _run_bg, similarity_threshold, days_window, min_cluster_size
    )
    return {
        "status": "started",
        "similarity_threshold": similarity_threshold,
        "days_window": days_window,
        "min_cluster_size": min_cluster_size,
    }


async def _run_bg(similarity_threshold: float, days_window: int, min_cluster_size: int):
    from app.pipelines.story_clustering import run_clustering
    result = await run_clustering(similarity_threshold, days_window, min_cluster_size)
    print(f"[Clusters] Job complete: {result}")


@router.get("/")
async def list_clusters(
    limit: int = 50,
    offset: int = 0,
    min_sources: int = 1,
    db: AsyncSession = Depends(get_db),
):
    """List story clusters ordered by article count. Filter by min number of sources."""
    q = (
        select(StoryCluster)
        .order_by(desc(StoryCluster.article_count), desc(StoryCluster.date_end))
        .offset(offset)
        .limit(limit)
    )
    if min_sources > 1:
        q = q.where(StoryCluster.source_count >= min_sources)

    result = await db.execute(q)
    clusters = result.scalars().all()

    total_result = await db.execute(select(func.count(StoryCluster.id)))
    total = total_result.scalar() or 0

    # Load unique source names per cluster (for display in list view)
    cluster_ids = [c.id for c in clusters]
    sources_by_cluster: dict[str, list[str]] = {str(c.id): [] for c in clusters}
    if cluster_ids:
        src_result = await db.execute(
            select(StoryClusterArticle.cluster_id, Source.name)
            .join(Article, StoryClusterArticle.article_id == Article.id)
            .join(Source, Article.source_id == Source.id)
            .where(StoryClusterArticle.cluster_id.in_(cluster_ids))
            .distinct()
        )
        for row in src_result.all():
            cid = str(row.cluster_id)
            if cid in sources_by_cluster:
                sources_by_cluster[cid].append(row.name)

    return {
        "total": total,
        "clusters": [
            {**_cluster_dict(c), "sources": sorted(sources_by_cluster.get(str(c.id), []))}
            for c in clusters
        ],
    }


@router.get("/by-article/{article_id}")
async def cluster_for_article(article_id: str, db: AsyncSession = Depends(get_db)):
    """Return the cluster (if any) that contains the given article."""
    result = await db.execute(
        select(StoryCluster)
        .join(StoryClusterArticle, StoryCluster.id == StoryClusterArticle.cluster_id)
        .where(StoryClusterArticle.article_id == uuid.UUID(article_id))
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        return None
    return _cluster_dict(cluster)


@router.get("/{cluster_id}")
async def get_cluster(cluster_id: str, db: AsyncSession = Depends(get_db)):
    """Cluster detail: metadata + all member articles with their analysis."""
    result = await db.execute(
        select(StoryCluster).where(StoryCluster.id == uuid.UUID(cluster_id))
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        from fastapi import HTTPException
        raise HTTPException(404, "Cluster not found")

    # Fetch member articles + analysis
    members_result = await db.execute(
        select(
            StoryClusterArticle.similarity_score,
            Article.id,
            Article.title,
            Article.url,
            Article.published_at,
            Source.name.label("source_name"),
            AnalysisResult.political_lean,
            AnalysisResult.sentiment_score,
            AnalysisResult.sentiment_label,
            AnalysisResult.primary_topic,
        )
        .join(Article, StoryClusterArticle.article_id == Article.id)
        .outerjoin(Source, Article.source_id == Source.id)
        .outerjoin(AnalysisResult, Article.id == AnalysisResult.article_id)
        .where(StoryClusterArticle.cluster_id == cluster.id)
        .order_by(Article.published_at.desc().nullslast())
    )
    member_rows = members_result.all()

    # Deduplicate by article_id (pick row with analysis data when available)
    seen: dict[str, dict] = {}
    for r in member_rows:
        aid = str(r.id)
        if aid not in seen or (seen[aid]["political_lean"] is None and r.political_lean is not None):
            seen[aid] = {
                "id": aid,
                "title": r.title,
                "url": r.url,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "source_name": r.source_name,
                "political_lean": r.political_lean,
                "sentiment_score": r.sentiment_score,
                "sentiment_label": r.sentiment_label,
                "primary_topic": r.primary_topic,
                "similarity_score": r.similarity_score,
            }

    articles = list(seen.values())

    # Compute per-source breakdown
    from collections import defaultdict
    src_groups: dict[str, list] = defaultdict(list)
    for a in articles:
        src_groups[a["source_name"] or "Unknown"].append(a)

    per_source = []
    for src_name, arts in sorted(src_groups.items()):
        leans = [a["political_lean"] for a in arts if a["political_lean"] is not None]
        per_source.append({
            "source_name": src_name,
            "article_count": len(arts),
            "analyzed_count": len(leans),
            "avg_lean": round(sum(leans) / len(leans), 3) if leans else None,
            "min_lean": round(min(leans), 3) if leans else None,
            "max_lean": round(max(leans), 3) if leans else None,
        })
    # Sort by avg_lean (left to right)
    per_source.sort(key=lambda x: (x["avg_lean"] is None, x["avg_lean"] or 0))

    # Bias divergence: spread between most-left and most-right analyzed sources
    analyzed_avgs = [s["avg_lean"] for s in per_source if s["avg_lean"] is not None]
    bias_divergence = round(max(analyzed_avgs) - min(analyzed_avgs), 3) if len(analyzed_avgs) >= 2 else None

    return {
        **_cluster_dict(cluster),
        "articles": articles,
        "per_source": per_source,
        "bias_divergence": bias_divergence,
    }


def _cluster_dict(c: StoryCluster) -> dict:
    def _f(v): return round(float(v), 3) if v is not None else None
    return {
        "id": str(c.id),
        "topic_label": c.topic_label,
        "article_count": c.article_count,
        "source_count": c.source_count,
        "avg_lean": _f(c.avg_lean),
        "avg_sentiment": _f(c.avg_sentiment),
        "date_start": c.date_start.isoformat() if c.date_start else None,
        "date_end": c.date_end.isoformat() if c.date_end else None,
        "similarity_threshold": c.similarity_threshold,
        "representative_id": str(c.representative_id) if c.representative_id else None,
    }
