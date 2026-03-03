"""
Settings router — /api/settings
Provides CRUD for the app_settings key-value table and Celery concurrency control.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.core.database import AsyncSessionLocal
from app.models import AppSetting
from app.services.logging_service import get_logger, init_logging_from_db

router = APIRouter()


# ── Dependency ─────────────────────────────────────────────────────────────────

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# ── Schemas ────────────────────────────────────────────────────────────────────

class SettingUpdate(BaseModel):
    value: str


class LogSettingsUpdate(BaseModel):
    log_level: str            # "debug" | "info" | "error"
    log_output: str           # "file" | "splunk" | "both"
    log_dir: str
    splunk_hec_url: str = ""
    splunk_hec_token: str = ""
    splunk_hec_index: str = "media_metrics"


class CeleryScaleRequest(BaseModel):
    concurrency: int


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/")
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Return all settings as {key: {value, description}}."""
    result = await db.execute(select(AppSetting).order_by(AppSetting.key))
    settings = result.scalars().all()
    # Mask the Splunk token if set
    out = {}
    for s in settings:
        val = s.value
        if s.key == "splunk_hec_token" and val:
            val = "••••••••"  # masked
        out[s.key] = {"value": val, "description": s.description}
    return out


@router.put("/{key}")
async def update_setting(
    key: str,
    body: SettingUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a single setting by key, then reload logging if applicable."""
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    setting.value = body.value
    await db.commit()
    # Reload logging whenever any log-related setting changes
    if key.startswith("log_") or key.startswith("splunk_"):
        await init_logging_from_db()
    return {"key": key, "value": body.value, "updated": True}


@router.post("/log")
async def update_log_settings(
    body: LogSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Batch-update all logging settings in one call, then reload logger."""
    updates = {
        "log_level":        body.log_level,
        "log_output":       body.log_output,
        "log_dir":          body.log_dir,
        "splunk_hec_url":   body.splunk_hec_url,
        "splunk_hec_index": body.splunk_hec_index,
    }
    # Only overwrite the token if a non-masked value was provided
    if body.splunk_hec_token and body.splunk_hec_token != "••••••••":
        updates["splunk_hec_token"] = body.splunk_hec_token

    result = await db.execute(select(AppSetting))
    settings_map = {s.key: s for s in result.scalars().all()}

    for k, v in updates.items():
        if k in settings_map:
            settings_map[k].value = v

    await db.commit()
    await init_logging_from_db()

    log = get_logger()
    log.info(
        "settings_updated",
        changed_keys=list(updates.keys()),
        log_level=body.log_level,
        log_output=body.log_output,
    )
    return {"updated": list(updates.keys())}


@router.post("/celery/scale")
async def scale_celery(
    body: CeleryScaleRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Adjust the running Celery worker's pool concurrency.

    Uses Celery's pool_grow / pool_shrink control broadcasts, which take
    effect on the live worker without a restart.  Also persists the target
    to app_settings so restarts pick it up.

    Note: with Ollama as a serial LLM backend, concurrency > 2-3 rarely
    helps analysis speed but is useful for testing the task queue.
    """
    if body.concurrency < 1 or body.concurrency > 16:
        raise HTTPException(400, "concurrency must be between 1 and 16")

    result = await db.execute(
        select(AppSetting).where(AppSetting.key == "celery_concurrency")
    )
    setting = result.scalar_one_or_none()
    current = int(setting.value) if setting else 1

    # Send Celery control message
    delta = body.concurrency - current
    try:
        from app.worker import celery_app
        if delta > 0:
            celery_app.control.pool_grow(delta)
        elif delta < 0:
            celery_app.control.pool_shrink(abs(delta))
    except Exception as exc:
        raise HTTPException(500, f"Celery control error: {exc}")

    # Persist
    if setting:
        setting.value = str(body.concurrency)
        await db.commit()

    get_logger().info(
        "celery_concurrency_changed",
        previous=current,
        new=body.concurrency,
        delta=delta,
    )
    return {
        "concurrency": body.concurrency,
        "previous": current,
        "delta": delta,
    }


@router.get("/celery/status")
async def celery_status():
    """Return current Celery worker info (active tasks, pool size)."""
    try:
        from app.worker import celery_app
        inspect = celery_app.control.inspect(timeout=2.0)
        active = inspect.active() or {}
        stats  = inspect.stats() or {}
        workers = []
        for name, worker_stats in stats.items():
            pool = worker_stats.get("pool", {})
            workers.append({
                "name": name,
                "concurrency": pool.get("max-concurrency", "?"),
                "processes": pool.get("processes", []),
                "active_tasks": len(active.get(name, [])),
            })
        return {"workers": workers}
    except Exception as exc:
        return {"workers": [], "error": str(exc)}
