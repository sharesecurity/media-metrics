# Compatibility shim — all DB setup lives in app.core.database
from app.core.database import Base, engine, AsyncSessionLocal, init_db, get_db

__all__ = ["Base", "engine", "AsyncSessionLocal", "init_db", "get_db"]
