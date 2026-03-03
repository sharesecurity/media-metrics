from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import init_db
from app.routers import articles, analysis, sources, authors, ingest, search, chat, bias_methods, entities

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Ensure MinIO bucket exists on startup (non-critical)
    try:
        from app.services.minio_service import ensure_bucket
        await ensure_bucket()
    except Exception as e:
        print(f"[Startup] MinIO bucket init failed (non-critical): {e}")
    yield

app = FastAPI(
    title="Media Metrics API",
    description="News bias analysis and media metrics platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(articles.router, prefix="/api/articles", tags=["articles"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["analysis"])
app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
app.include_router(authors.router, prefix="/api/authors", tags=["authors"])
app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(bias_methods.router, prefix="/api/bias-methods", tags=["bias-methods"])
app.include_router(entities.router, prefix="/api/entities", tags=["entities"])

@app.get("/health")
async def health():
    return {"status": "ok", "service": "media-metrics-backend"}
