"""
Structured logging service for Media Metrics.

Provides a singleton MediaMetricsLogger that emits JSON-formatted log records to:
  - A rotating log file  (when log_output = "file" or "both")
  - A Splunk HEC server  (when log_output = "splunk" or "both")

Log levels: debug | info | error
Each record is a JSON object with UTC timestamp + event + arbitrary kwargs.

Usage:
    from app.services.logging_service import get_logger
    log = get_logger()
    log.info("article_ingested", article_id=str(aid), source="Daily Mail", url=url)
    log.error("analysis_failed", article_id=str(aid), error=str(e), duration_ms=1234)

Call log.configure(...) at startup (or after a settings change) to apply the
current settings.  It is safe to call configure() multiple times; old handlers
are cleanly removed before new ones are attached.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


# ── JSON formatter ─────────────────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    """Emit every log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
        }
        # Merge any extra fields attached by the caller
        if hasattr(record, "_mm_extra"):
            obj.update(record._mm_extra)
        # Fallback: include the plain message if no _mm_extra
        if "event" not in obj:
            obj["message"] = record.getMessage()
        return json.dumps(obj, default=str)


# ── Splunk HEC handler ─────────────────────────────────────────────────────────

class _SplunkHECHandler(logging.Handler):
    """
    Non-blocking Splunk HEC log handler.

    Records are enqueued to an in-memory queue (max 1 000 entries).
    A daemon thread drains the queue and POSTs to the HEC endpoint.
    Failures are silently discarded so logging never blocks the pipeline.
    """

    def __init__(self, url: str, token: str, index: str = "media_metrics"):
        super().__init__()
        self.url = url
        self.token = token
        self.index = index
        self._q: queue.Queue = queue.Queue(maxsize=1_000)
        self._thread = threading.Thread(target=self._drain, daemon=True, name="splunk-hec")
        self._thread.start()

    # ---- logging.Handler interface -------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._q.put_nowait(record)
        except queue.Full:
            pass  # drop silently — never block the caller

    # ---- background drainer --------------------------------------------------

    def _drain(self) -> None:
        import httpx  # local import so the module loads even if httpx absent

        session = httpx.Client(timeout=5.0)
        while True:
            record = self._q.get()
            try:
                payload = {
                    "time": time.time(),
                    "event": json.loads(self.format(record)),
                    "sourcetype": "_json",
                    "index": self.index,
                }
                session.post(
                    self.url,
                    json=payload,
                    headers={"Authorization": f"Splunk {self.token}"},
                )
            except Exception:
                pass  # never crash the drainer


# ── Singleton logger ───────────────────────────────────────────────────────────

_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info":  logging.INFO,
    "error": logging.ERROR,
}


class MediaMetricsLogger:
    """
    Singleton structured logger.

    Thread-safe — configure() can be called from the FastAPI lifespan
    or from any async endpoint without locks (GIL protects handler list swap).
    """

    _instance: Optional["MediaMetricsLogger"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._inner = logging.getLogger("media_metrics")
        self._inner.setLevel(logging.DEBUG)   # actual gating done per-handler
        self._inner.propagate = False
        self._active_handlers: list[logging.Handler] = []
        self._configured = False

    # ---- singleton access ----------------------------------------------------

    @classmethod
    def get(cls) -> "MediaMetricsLogger":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ---- configuration -------------------------------------------------------

    def configure(
        self,
        level: str = "info",
        output: str = "file",
        log_dir: str = "/app/logs",
        splunk_url: str = "",
        splunk_token: str = "",
        splunk_index: str = "media_metrics",
    ) -> None:
        """
        (Re-)configure handlers.  Safe to call multiple times — existing
        handlers are removed before the new ones are attached.
        """
        log_level = _LEVEL_MAP.get(level.lower(), logging.INFO)
        formatter = _JsonFormatter()

        # Remove stale handlers
        for h in self._active_handlers:
            self._inner.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass
        self._active_handlers = []

        # ── File handler ───────────────────────────────────────────────────────
        if output in ("file", "both"):
            try:
                Path(log_dir).mkdir(parents=True, exist_ok=True)
                fh = RotatingFileHandler(
                    f"{log_dir}/media_metrics.log",
                    maxBytes=10_000_000,   # 10 MB per file
                    backupCount=5,
                    encoding="utf-8",
                )
                fh.setFormatter(formatter)
                fh.setLevel(log_level)
                self._inner.addHandler(fh)
                self._active_handlers.append(fh)
            except Exception as exc:
                print(f"[Logger] Could not open log file in '{log_dir}': {exc}")

        # ── Splunk HEC handler ─────────────────────────────────────────────────
        if output in ("splunk", "both") and splunk_url and splunk_token:
            sh = _SplunkHECHandler(splunk_url, splunk_token, splunk_index)
            sh.setFormatter(formatter)
            sh.setLevel(log_level)
            self._inner.addHandler(sh)
            self._active_handlers.append(sh)

        self._inner.setLevel(log_level)
        self._configured = True

    # ---- emit helpers --------------------------------------------------------

    def _emit(self, level: int, event: str, **kwargs) -> None:
        if not self._configured or not self._active_handlers:
            return  # silently skip until configure() has been called
        if not self._inner.isEnabledFor(level):
            return
        record = self._inner.makeRecord(
            self._inner.name, level,
            fn="(pipeline)", lno=0, msg=event, args=(), exc_info=None,
        )
        record._mm_extra = {"event": event, **kwargs}
        self._inner.handle(record)

    def debug(self, event: str, **kwargs) -> None:
        self._emit(logging.DEBUG, event, **kwargs)

    def info(self, event: str, **kwargs) -> None:
        self._emit(logging.INFO, event, **kwargs)

    def error(self, event: str, **kwargs) -> None:
        self._emit(logging.ERROR, event, **kwargs)


# ── Public accessor ────────────────────────────────────────────────────────────

def get_logger() -> MediaMetricsLogger:
    """Return the singleton MediaMetricsLogger."""
    return MediaMetricsLogger.get()


async def init_logging_from_db() -> None:
    """
    Read log settings from app_settings and configure the logger.
    Called once at startup (FastAPI lifespan) and again after any setting change.
    """
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from sqlalchemy import select, text
        from app.config import settings as app_cfg
        from app.models import AppSetting

        engine = create_async_engine(app_cfg.database_url)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as db:
            result = await db.execute(select(AppSetting))
            cfg = {s.key: s.value for s in result.scalars().all()}
        await engine.dispose()

        get_logger().configure(
            level=cfg.get("log_level", "info"),
            output=cfg.get("log_output", "file"),
            log_dir=cfg.get("log_dir", "/app/logs"),
            splunk_url=cfg.get("splunk_hec_url", ""),
            splunk_token=cfg.get("splunk_hec_token", ""),
            splunk_index=cfg.get("splunk_hec_index", "media_metrics"),
        )
        print(f"[Logger] Initialized — level={cfg.get('log_level','info')}, output={cfg.get('log_output','file')}")
    except Exception as exc:
        print(f"[Logger] Could not load settings from DB, using file/info defaults: {exc}")
        get_logger().configure()   # safe defaults
