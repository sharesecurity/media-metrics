from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://media:media_metrics_2024@postgres:5432/media_metrics"

    # Qdrant vector DB
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333

    # MinIO object storage
    minio_host: str = "minio"
    minio_port: int = 9000
    minio_access_key: str = "media_metrics"
    minio_secret_key: str = "media_metrics_2024"
    minio_bucket: str = "articles"

    # Ollama (native on host, reached via host.docker.internal from Docker)
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_chat_model: str = "deepseek-r1:8b"

    # Convenience aliases
    @property
    def ollama_base_url(self) -> str:
        return self.ollama_url

    @property
    def ollama_model(self) -> str:
        return self.ollama_chat_model

    # Anthropic (optional fallback)
    anthropic_api_key: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
