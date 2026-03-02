"""
Bias Analysis Pipeline
Uses local Ollama (deepseek-r1:8b) + VADER sentiment + textstat for readability.
"""

import httpx
import json
import re
import uuid
from datetime import datetime, timezone
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import textstat
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from app.config import settings
from app.models import Article, AnalysisResult

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,       # re-validate connections before use
    pool_recycle=300,         # recycle connections every 5 min
    pool_size=5,
    max_overflow=10,
)
AsyncSession_ = async_sessionmaker(engine, expire_on_commit=False)

vader = SentimentIntensityAnalyzer()

BIAS_PROMPT = """Analyze the political bias of this news article. 
Rate it on a scale from -1.0 (strongly left-leaning) to 1.0 (strongly right-leaning), where 0.0 is neutral/balanced.

Consider:
- Word choice and loaded language
- Which perspectives are given more prominence  
- What facts are emphasized vs omitted
- Whose voices are quoted
- Framing of issues

Respond ONLY with valid JSON (no explanation outside JSON):
{
  "political_lean": <float -1.0 to 1.0>,
  "confidence": <float 0.0 to 1.0>,
  "primary_topic": "<string>",
  "key_indicators": ["<indicator1>", "<indicator2>"],
  "framing_notes": "<brief explanation>"
}

Article:
"""

def parse_json_from_llm(text: str) -> dict:
    """Extract JSON from LLM output, handling <think> tags from deepseek-r1."""
    # Remove <think>...</think> blocks (deepseek-r1 reasoning)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Find JSON block
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception as e:
            print(f"[Bias] JSON parse error: {e}, raw text: {match.group()[:200]}")
    return {}

async def analyze_article_bias(article_id: str, analysis_type: str = "full"):
    """Run full bias analysis on an article."""
    async with AsyncSession_() as db:
        result = await db.execute(
            select(Article).where(Article.id == uuid.UUID(article_id))
        )
        article = result.scalar_one_or_none()
        if not article:
            print(f"[Bias] Article {article_id} not found")
            return

        text = article.raw_text or article.title or ""
        if not text.strip():
            print(f"[Bias] Article {article_id} has no text")
            return

        print(f"[Bias] Analyzing article: {article.title[:60]}...")

        # 1. VADER Sentiment (fast, rule-based)
        vader_scores = vader.polarity_scores(text)
        sentiment_score = vader_scores['compound']
        sentiment_label = (
            "positive" if sentiment_score > 0.05
            else "negative" if sentiment_score < -0.05
            else "neutral"
        )

        # 2. Readability
        try:
            reading_level = textstat.flesch_kincaid_grade(text)
            avg_sentence_length = textstat.avg_sentence_length(text)
        except Exception as e:
            print(f"[Bias] Readability error: {e}")
            reading_level = None
            avg_sentence_length = None

        # 3. LLM Bias Analysis (Ollama deepseek-r1:8b)
        llm_result = {}
        try:
            truncated_text = text[:3000]  # keep within context window
            payload = {
                "model": settings.ollama_model,
                "messages": [{"role": "user", "content": BIAS_PROMPT + truncated_text}],
                "stream": False,
            }
            print(f"[Bias] Calling Ollama at {settings.ollama_base_url} with model {settings.ollama_model}")
            async with httpx.AsyncClient(timeout=180) as client:
                resp = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json=payload
                )
                print(f"[Bias] Ollama response status: {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    raw_content = data.get("message", {}).get("content", "")
                    print(f"[Bias] LLM raw (first 300 chars): {raw_content[:300]}")
                    llm_result = parse_json_from_llm(raw_content)
                    print(f"[Bias] LLM parsed result: {llm_result}")
                else:
                    print(f"[Bias] Ollama non-200: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            print(f"[Bias] LLM error ({type(e).__name__}): {e}")

        # 4. Store results
        try:
            analysis = AnalysisResult(
                article_id=uuid.UUID(article_id),
                analyzed_at=datetime.now(timezone.utc),
                model_used=f"vader+{settings.ollama_model}",
                analysis_type="full",
                sentiment_score=sentiment_score,
                sentiment_label=sentiment_label,
                subjectivity=None,
                political_lean=llm_result.get("political_lean"),
                political_confidence=llm_result.get("confidence"),
                primary_topic=llm_result.get("primary_topic"),
                reading_level=reading_level,
                avg_sentence_length=avg_sentence_length,
                raw_analysis={
                    "vader": vader_scores,
                    "llm": llm_result,
                }
            )
            db.add(analysis)
            await db.commit()
            print(f"[Bias] ✓ Analysis saved for {article_id}")
        except Exception as e:
            print(f"[Bias] DB save error ({type(e).__name__}): {e}")
            await db.rollback()
