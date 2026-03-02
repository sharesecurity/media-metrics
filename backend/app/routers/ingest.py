from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from app.pipelines.gdelt_ingest import ingest_gdelt_sample
from typing import Optional

router = APIRouter()

class IngestRequest(BaseModel):
    source: str = "gdelt"  # gdelt, url, file
    limit: int = 100
    date: Optional[str] = None  # YYYY-MM-DD

@router.post("/start")
async def start_ingest(req: IngestRequest, background_tasks: BackgroundTasks):
    """Start a data ingestion job."""
    if req.source == "gdelt":
        background_tasks.add_task(ingest_gdelt_sample, req.limit, req.date)
        return {"status": "started", "source": "gdelt", "limit": req.limit}
    return {"error": f"Unknown source: {req.source}"}

@router.get("/status")
async def ingest_status():
    """Simple status check — in future hook into celery."""
    return {"status": "idle"}
