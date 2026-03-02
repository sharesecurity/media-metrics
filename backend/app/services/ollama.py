import httpx
from typing import Optional
from app.core.config import settings

OLLAMA_URL = settings.ollama_url

async def get_embedding(text: str) -> list[float]:
    """Get embedding vector from Ollama nomic-embed-text."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{OLLAMA_URL}/api/embeddings", json={
            "model": settings.ollama_embed_model,
            "prompt": text[:8192]  # nomic limit
        })
        r.raise_for_status()
        return r.json()["embedding"]

async def chat(prompt: str, system: Optional[str] = None, model: Optional[str] = None) -> str:
    """Send a chat prompt to Ollama, return response text."""
    m = model or settings.ollama_chat_model
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=300.0) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json={
            "model": m,
            "messages": messages,
            "stream": False
        })
        r.raise_for_status()
        return r.json()["message"]["content"]
