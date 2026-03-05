"""
Story Clustering Pipeline

Groups articles covering the same underlying news story by combining:
  1. Embedding cosine similarity (via Qdrant nearest-neighbor search)
  2. Publication date proximity (configurable window, default ±5 days)

Algorithm:
  - Scroll all Qdrant points to get IDs + payloads
  - For each point, query its K nearest neighbours (score > threshold)
  - Post-filter by time window using published_at from payload
  - Build adjacency graph → find connected components (union-find)
  - Persist clusters ≥ min_size to PostgreSQL (story_clusters + bridge)
  - Clear old clusters before writing new ones
"""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func, delete
from app.config import settings
from app.models import StoryCluster, StoryClusterArticle, Article, AnalysisResult, Source

QDRANT_URL = settings.qdrant_url if hasattr(settings, "qdrant_url") else "http://qdrant:6333"
COLLECTION = "articles"

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSession_ = async_sessionmaker(engine, expire_on_commit=False)


# ── Union-Find ─────────────────────────────────────────────────────────────────

class UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        if x not in self.parent:
            self.parent[x] = x
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def groups(self) -> dict[str, list[str]]:
        g: dict[str, list[str]] = defaultdict(list)
        for x in self.parent:
            g[self.find(x)].append(x)
        return dict(g)


# ── Qdrant helpers ─────────────────────────────────────────────────────────────

async def _scroll_all_points(client: httpx.AsyncClient) -> list[dict]:
    """Scroll all points from Qdrant and return list of {id, payload}."""
    points = []
    offset = None
    while True:
        body = {"limit": 500, "with_payload": True, "with_vector": False}
        if offset:
            body["offset"] = offset
        r = await client.post(f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll", json=body)
        if r.status_code != 200:
            print(f"[Cluster] Qdrant scroll error: {r.status_code}")
            break
        data = r.json().get("result", {})
        batch = data.get("points", [])
        points.extend(batch)
        offset = data.get("next_page_offset")
        if offset is None:
            break
    return points


async def _search_similar(
    client: httpx.AsyncClient,
    point_id: str,
    limit: int = 30,
    score_threshold: float = 0.78,
) -> list[dict]:
    """Find nearest neighbours for a given point ID using Qdrant recommend API."""
    r = await client.post(
        f"{QDRANT_URL}/collections/{COLLECTION}/points/recommend",
        json={
            "positive": [point_id],
            "limit": limit,
            "score_threshold": score_threshold,
            "with_payload": False,
            "with_vector": False,
        },
    )
    if r.status_code != 200:
        return []
    return r.json().get("result", [])


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def run_clustering(
    similarity_threshold: float = 0.78,
    days_window: int = 5,
    min_cluster_size: int = 2,
) -> dict:
    """
    Run story clustering and persist results.
    Returns summary stats dict.
    """
    print(f"[Cluster] Starting (threshold={similarity_threshold}, window=±{days_window}d)")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Fetch all embedded articles from Qdrant
        all_points = await _scroll_all_points(client)
        if not all_points:
            print("[Cluster] No points in Qdrant — run analysis first")
            return {"status": "no_data", "clusters": 0, "articles": 0}

        print(f"[Cluster] {len(all_points)} points in Qdrant")

        # Build id → published_at map from payloads
        pub_dates: dict[str, datetime | None] = {}
        for p in all_points:
            payload = p.get("payload") or {}
            pa = payload.get("published_at")
            try:
                pub_dates[p["id"]] = datetime.fromisoformat(pa) if pa else None
            except Exception:
                pub_dates[p["id"]] = None

        # 2. For each point, find similar neighbours and build graph
        uf = UnionFind()
        edge_scores: dict[tuple[str, str], float] = {}

        # Ensure all IDs are registered in union-find
        for p in all_points:
            uf.find(p["id"])

        sem = asyncio.Semaphore(8)

        async def process_point(pid: str):
            async with sem:
                neighbours = await _search_similar(client, pid, limit=25, score_threshold=similarity_threshold)
                for nb in neighbours:
                    nid = nb["id"]
                    score = nb.get("score", 0.0)
                    # Apply time window filter
                    d1 = pub_dates.get(pid)
                    d2 = pub_dates.get(nid)
                    if d1 and d2:
                        diff = abs((d1 - d2).total_seconds()) / 86400.0
                        if diff > days_window:
                            continue
                    uf.union(pid, nid)
                    key = (min(pid, nid), max(pid, nid))
                    if key not in edge_scores or edge_scores[key] < score:
                        edge_scores[key] = score

        await asyncio.gather(*[process_point(p["id"]) for p in all_points])

        # 3. Get connected components
        raw_groups = uf.groups()
        clusters = {root: members for root, members in raw_groups.items()
                    if len(members) >= min_cluster_size}

        print(f"[Cluster] Found {len(clusters)} raw clusters with ≥{min_cluster_size} articles")

        # 4. Enrich cluster stats from Postgres
        async with AsyncSession_() as db:
            # Clear old clusters
            await db.execute(delete(StoryCluster))
            await db.commit()

            saved = 0
            total_members = 0

            for root, member_ids in clusters.items():
                if len(member_ids) < min_cluster_size:
                    continue

                # Get article + analysis data
                article_ids_uuid = []
                for mid in member_ids:
                    try:
                        article_ids_uuid.append(uuid.UUID(mid))
                    except Exception:
                        pass

                if not article_ids_uuid:
                    continue

                art_result = await db.execute(
                    select(
                        Article.id,
                        Article.title,
                        Article.published_at,
                        Article.source_id,
                    )
                    .where(Article.id.in_(article_ids_uuid))
                )
                articles_rows = art_result.all()
                if not articles_rows:
                    continue

                # Get analysis data
                analysis_result = await db.execute(
                    select(
                        AnalysisResult.article_id,
                        AnalysisResult.political_lean,
                        AnalysisResult.sentiment_score,
                    )
                    .distinct(AnalysisResult.article_id)
                    .where(AnalysisResult.article_id.in_(article_ids_uuid))
                    .order_by(AnalysisResult.article_id)
                )
                analysis_map = {str(r.article_id): r for r in analysis_result.all()}

                leans = [analysis_map[str(a.id)].political_lean
                         for a in articles_rows if str(a.id) in analysis_map
                         and analysis_map[str(a.id)].political_lean is not None]
                sentiments = [analysis_map[str(a.id)].sentiment_score
                              for a in articles_rows if str(a.id) in analysis_map
                              and analysis_map[str(a.id)].sentiment_score is not None]
                pub_dates_local = [a.published_at for a in articles_rows if a.published_at]
                source_ids = {str(a.source_id) for a in articles_rows if a.source_id}

                # Bias divergence: per-source avg leans → max - min spread
                lean_by_source: dict[str, list[float]] = defaultdict(list)
                for a in articles_rows:
                    if str(a.id) in analysis_map and analysis_map[str(a.id)].political_lean is not None:
                        lean_by_source[str(a.source_id)].append(analysis_map[str(a.id)].political_lean)
                src_avgs = [sum(v) / len(v) for v in lean_by_source.values() if v]
                bias_divergence_val = round(max(src_avgs) - min(src_avgs), 3) if len(src_avgs) >= 2 else None

                # Pick representative = most-recently published
                rep = max(articles_rows, key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc))

                cluster_obj = StoryCluster(
                    representative_id=rep.id,
                    topic_label=rep.title[:120] if rep.title else None,
                    article_count=len(articles_rows),
                    avg_lean=sum(leans) / len(leans) if leans else None,
                    avg_sentiment=sum(sentiments) / len(sentiments) if sentiments else None,
                    source_count=len(source_ids),
                    date_start=min(pub_dates_local) if pub_dates_local else None,
                    date_end=max(pub_dates_local) if pub_dates_local else None,
                    similarity_threshold=similarity_threshold,
                    bias_divergence=bias_divergence_val,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(cluster_obj)
                await db.flush()  # get cluster_obj.id

                for a in articles_rows:
                    # Best similarity score for this article to any cluster member
                    best_score = max(
                        (edge_scores.get((min(str(a.id), str(b.id)), max(str(a.id), str(b.id))), 0.0)
                         for b in articles_rows if b.id != a.id),
                        default=0.0,
                    )
                    db.add(StoryClusterArticle(
                        cluster_id=cluster_obj.id,
                        article_id=a.id,
                        similarity_score=round(best_score, 4),
                    ))
                    total_members += 1

                await db.commit()
                saved += 1

            print(f"[Cluster] Saved {saved} clusters, {total_members} total memberships")
            return {
                "status": "ok",
                "clusters_found": len(clusters),
                "clusters_saved": saved,
                "articles_in_clusters": total_members,
                "qdrant_points": len(all_points),
            }
