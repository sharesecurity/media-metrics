from fastapi import APIRouter
from pydantic import BaseModel
from app.config import settings
import httpx

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    context: str = ""  # optional data context

@router.post("/ask")
async def chat_ask(req: ChatRequest):
    """Send a question to the local Ollama LLM about the data."""
    system_prompt = """You are a helpful data analyst assistant for Media Metrics, 
a news bias analysis platform. You help users understand patterns in news coverage, 
bias metrics, and media trends. Be concise and data-focused."""

    user_content = req.message
    if req.context:
        user_content = f"Context data:\n{req.context}\n\nQuestion: {req.message}"

    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json=payload
        )
        data = resp.json()

    return {"response": data.get("message", {}).get("content", "No response")}
