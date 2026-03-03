"""
Vector storage service using Qdrant.
"""
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from app.core.config import settings
import uuid

COLLECTION = "articles"
VECTOR_SIZE = 768  # nomic-embed-text output size


def get_client() -> AsyncQdrantClient:
    """Always return a fresh client so it is bound to the current event loop.
    The singleton pattern caused 'Event loop is closed' errors in Celery workers
    because the client held connections from the previous asyncio.run() loop."""
    return AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

async def ensure_collection():
    client = get_client()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    if COLLECTION not in names:
        await client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
        )

async def upsert_article(article_id: str, embedding: list[float], payload: dict):
    client = get_client()
    await client.upsert(
        collection_name=COLLECTION,
        points=[PointStruct(id=str(article_id), vector=embedding, payload=payload)]
    )

async def search_similar(embedding: list[float], limit: int = 10, source_filter: str = None):
    client = get_client()
    filt = None
    if source_filter:
        filt = Filter(must=[FieldCondition(key="source_name", match=MatchValue(value=source_filter))])
    results = await client.search(
        collection_name=COLLECTION,
        query_vector=embedding,
        limit=limit,
        query_filter=filt,
        with_payload=True
    )
    return results
