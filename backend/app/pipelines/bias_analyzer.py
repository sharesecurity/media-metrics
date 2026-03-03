"""
Bias Analysis Pipeline
Uses local Ollama (deepseek-r1:8b) + VADER sentiment + textstat for readability.
After analysis, generates a nomic-embed-text embedding and stores it in Qdrant.
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
from app.models import Article, AnalysisResult, Source, ArticleProvenance, Organization

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
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

# Wire service attribution patterns: (pattern, confidence, org_slug)
# Ordered from highest to lowest confidence signals.
_WIRE_PATTERNS = [
    # Dateline abbreviations — very high confidence
    (r'\(AP\)',        0.95, "ap"),
    (r'\(Reuters\)',   0.95, "reuters"),
    (r'\(AFP\)',       0.95, "afp"),
    (r'\(Bloomberg\)', 0.95, "bloomberg"),
    (r'\(UPI\)',       0.95, "upi"),
    # Full name in first 500 chars — high confidence
    (r'The Associated Press',      0.90, "ap"),
    (r'By Reuters Staff',          0.90, "reuters"),
    (r'By The Associated Press',   0.90, "ap"),
    (r'Agence France-Presse',      0.90, "afp"),
    # Reuters "Reporting by X; Editing by Y" footer pattern
    (r'Reporting by .{0,80};\s*[Ee]diting by', 0.90, "reuters"),
    # Softer attribution phrases
    (r'according to (?:the )?Associated Press', 0.75, "ap"),
    (r'according to Reuters',                   0.75, "reuters"),
    (r'via (?:the )?Associated Press',          0.75, "ap"),
    (r'via Reuters',                            0.75, "reuters"),
    (r'originally published by (?:the )?AP',   0.75, "ap"),
]

def detect_wire_attribution(text: str) -> list[dict]:
    """
    Scan article text for wire service attribution patterns.
    Returns a list of matches: [{wire_slug, confidence, attribution_text, match_start}].
    Checks full text for datelines; restricts softer phrases to first 1000 chars.
    """
    matches = []
    seen_slugs: set[str] = set()
    first_1000 = text[:1000]

    for pattern, confidence, slug in _WIRE_PATTERNS:
        # Softer phrases (confidence < 0.90) only checked in opening text
        search_text = first_1000 if confidence < 0.90 else text
        m = re.search(pattern, search_text, re.IGNORECASE)
        if m and slug not in seen_slugs:
            matches.append({
                "wire_slug": slug,
                "confidence": confidence,
                "attribution_text": m.group(0),
            })
            seen_slugs.add(slug)
    return matches


def parse_json_from_llm(text: str) -> dict:
    """Extract JSON from LLM output, handling <think> tags from deepseek-r1."""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception as e:
            print(f"[Bias] JSON parse error: {e}, raw text: {match.group()[:200]}")
    return {}

async def _generate_embedding(text: str) -> list[float] | None:
    """Generate a nomic-embed-text embedding via Ollama. Returns None on failure."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{settings.ollama_base_url}/api/embeddings",
                json={"model": settings.ollama_embed_model, "prompt": text[:8192]},
            )
            if r.status_code == 200:
                return r.json().get("embedding")
            print(f"[Bias] Embedding non-200: {r.status_code}")
    except Exception as e:
        print(f"[Bias] Embedding error: {e}")
    return None

async def _upsert_to_qdrant(article_id: str, embedding: list[float], payload: dict):
    """Upsert article embedding + metadata to Qdrant. Silently fails if Qdrant unavailable."""
    try:
        from app.services.vector_store import ensure_collection, upsert_article
        await ensure_collection()
        await upsert_article(article_id, embedding, payload)
        print(f"[Bias] ✓ Qdrant upsert for {article_id}")
    except Exception as e:
        print(f"[Bias] Qdrant upsert failed (non-critical): {e}")

async def analyze_article_bias(article_id: str, analysis_type: str = "full"):
    """Run full bias analysis on an article, then index it in Qdrant."""
    async with AsyncSession_() as db:
        result = await db.execute(
            select(Article, Source.name.label("source_name"))
            .outerjoin(Source, Article.source_id == Source.id)
            .where(Article.id == uuid.UUID(article_id))
        )
        row = result.one_or_none()
        if not row:
            print(f"[Bias] Article {article_id} not found")
            return
        article, source_name = row

        # Prefer MinIO text, fall back to Postgres raw_text, then title
        text = article.raw_text or ""
        if article.minio_key and not text:
            try:
                from app.services.minio_service import get_article_text
                text = await get_article_text(article.minio_key) or ""
            except Exception as e:
                print(f"[Bias] MinIO fetch failed: {e}")
        if not text:
            text = article.title or ""
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
            truncated_text = text[:3000]
            payload_llm = {
                "model": settings.ollama_model,
                "messages": [{"role": "user", "content": BIAS_PROMPT + truncated_text}],
                "stream": False,
            }
            print(f"[Bias] Calling Ollama at {settings.ollama_base_url} with model {settings.ollama_model}")
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
                resp = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json=payload_llm
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
            import traceback
            print(f"[Bias] LLM error ({type(e).__name__}): {e!r}")
            print(traceback.format_exc())

        # 4. Store results in PostgreSQL
        political_lean = llm_result.get("political_lean")
        try:
            analysis = AnalysisResult(
                article_id=uuid.UUID(article_id),
                analyzed_at=datetime.now(timezone.utc),
                model_used=f"vader+{settings.ollama_model}",
                analysis_type="full",
                sentiment_score=sentiment_score,
                sentiment_label=sentiment_label,
                subjectivity=None,
                political_lean=political_lean,
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
            return  # If we can't save analysis, skip Qdrant too

        # 5. Provenance detection — regex scan for wire service attribution
        wire_hits = detect_wire_attribution(text)
        if wire_hits:
            try:
                # Look up org IDs for detected wire services (cached per session)
                org_result = await db.execute(
                    select(Organization.id, Organization.slug)
                    .where(Organization.slug.in_([h["wire_slug"] for h in wire_hits]))
                )
                slug_to_id = {row.slug: row.id for row in org_result}

                for hit in wire_hits:
                    org_id = slug_to_id.get(hit["wire_slug"])
                    prov = ArticleProvenance(
                        article_id=uuid.UUID(article_id),
                        provenance_type="wire_pickup",
                        wire_service_id=org_id,
                        confidence=hit["confidence"],
                        detection_method="explicit_attribution",
                        attribution_text=hit["attribution_text"],
                        detected_at=datetime.now(timezone.utc),
                    )
                    db.add(prov)
                await db.commit()
                slugs = [h["wire_slug"] for h in wire_hits]
                print(f"[Bias] ✓ Provenance detected: {slugs} for {article_id}")
            except Exception as e:
                print(f"[Bias] Provenance save error: {e}")
                await db.rollback()

        # 6. Generate embedding and index in Qdrant
        embed_text = f"{article.title}\n\n{text[:2000]}"
        embedding = await _generate_embedding(embed_text)
        if embedding:
            qdrant_payload = {
                "article_id": article_id,
                "title": article.title,
                "source_name": source_name or "",
                "section": article.section or "",
                "published_at": article.published_at.isoformat() if article.published_at else None,
                "political_lean": political_lean,
                "sentiment_score": sentiment_score,
                "sentiment_label": sentiment_label,
                "primary_topic": llm_result.get("primary_topic", ""),
            }
            await _upsert_to_qdrant(article_id, embedding, qdrant_payload)
        else:
            print(f"[Bias] Skipping Qdrant (no embedding generated)")
