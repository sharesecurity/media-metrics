# Compatibility shim — all config lives in app.core.config
from app.core.config import settings, get_settings

__all__ = ["settings", "get_settings"]
