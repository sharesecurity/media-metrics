#!/usr/bin/env python3
"""
Standalone batch analyzer — bypasses FastAPI, talks directly to DB + Ollama.
No connection pool issues. Safe concurrency via semaphore.

Usage:
    python3 scripts/direct_analyze.py              # all unanalyzed, concurrency=2
    python3 scripts/direct_analyze.py --concurrency 1 --min-text 50
"""
import asyncio
import argparse
import json
import re
import uuid
import httpx
import psycopg2
from datetime import datetime, timezone

# Config
DB_DSN = "host=localhost port=5434 dbname=media_metrics user=media password=media_metrics_2024"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "deepseek-r1:8b"

BIAS_PROMPT = """Analyze the political bias of this news article.
Rate it on a scale from -1.0 (strongly left-leaning) to 1.0 (strongly right-leaning), where 0.0 is neutral/balanced.

Consider word choice, framing, which voices are quoted, what facts are emphasized.

Respond ONLY with valid JSON:
{
  "political_lean": <float -1.0 to 1.0>,
  "confidence": <float 0.0 to 1.0>,
  "primary_topic": "<string>",
  "framing_notes": "<brief explanation>"
}

Article:
"""

def get_unanalyzed(min_text=100):
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()
    cur.execute("""
        SELECT a.id, a.title, a.raw_text
        FROM articles a
        LEFT JOIN analysis_results ar ON a.id = ar.article_id
        WHERE ar.id IS NULL AND LENGTH(a.raw_text) >= %s
        ORDER BY LENGTH(a.raw_text) DESC
    """, (min_text,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def save_result(article_id, sentiment_score, sentiment_label, political_lean, 
                political_confidence, primary_topic, raw_analysis):
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO analysis_results 
            (id, article_id, analyzed_at, model_used, analysis_type,
             sentiment_score, sentiment_label, political_lean, political_confidence,
             primary_topic, raw_analysis)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (
        str(uuid.uuid4()), str(article_id),
        datetime.now(timezone.utc), f"vader+{OLLAMA_MODEL}", "full",
        sentiment_score, sentiment_label, political_lean, political_confidence,
        primary_topic, json.dumps(raw_analysis)
    ))
    conn.commit()
    cur.close()
    conn.close()

def vader_sentiment(text):
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        vader = SentimentIntensityAnalyzer()
        scores = vader.polarity_scores(text)
        compound = scores['compound']
        label = "positive" if compound > 0.05 else "negative" if compound < -0.05 else "neutral"
        return compound, label, scores
    except Exception:
        return 0.0, "neutral", {}

def parse_llm_json(text):
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return {}

async def call_ollama(text, client):
    truncated = text[:3000]
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": BIAS_PROMPT + truncated}],
        "stream": False,
    }
    resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload,
                              timeout=httpx.Timeout(300.0, connect=10.0))
    if resp.status_code == 200:
        return parse_llm_json(resp.json().get("message", {}).get("content", ""))
    return {}

async def process_article(row, sem, idx, total, client):
    article_id, title, raw_text = row
    async with sem:
        try:
            # VADER
            sentiment_score, sentiment_label, vader_scores = vader_sentiment(raw_text or "")
            # Ollama
            llm = await call_ollama(raw_text or "", client)
            # Save
            save_result(
                article_id=article_id,
                sentiment_score=sentiment_score,
                sentiment_label=sentiment_label,
                political_lean=llm.get("political_lean"),
                political_confidence=llm.get("confidence"),
                primary_topic=llm.get("primary_topic"),
                raw_analysis={"vader": vader_scores, "llm": llm}
            )
            lean = llm.get("political_lean", "?")
            topic = llm.get("primary_topic", "")[:30]
            print(f"[{idx}/{total}] ✅ {str(article_id)[:8]}... lean={lean} topic={topic}")
            print(f"         {title[:60]}", flush=True)
        except Exception as e:
            print(f"[{idx}/{total}] ❌ {str(article_id)[:8]}... ERROR: {e}", flush=True)

async def main(concurrency=2, min_text=100):
    print(f"=== Direct Analyzer | concurrency={concurrency} model={OLLAMA_MODEL} ===")
    print(f"Started: {datetime.now().strftime('%H:%M:%S')}\n")

    rows = get_unanalyzed(min_text)
    total = len(rows)
    print(f"Found {total} unanalyzed articles with >={min_text} chars\n")
    if not rows:
        print("Nothing to do!")
        return

    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient() as client:
        tasks = [process_article(row, sem, i+1, total, client) for i, row in enumerate(rows)]
        await asyncio.gather(*tasks)

    print(f"\n=== Done | {datetime.now().strftime('%H:%M:%S')} ===")
    # Print summary
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM analysis_results")
    count = cur.fetchone()[0]
    cur.close(); conn.close()
    print(f"Total analyzed in DB: {count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=2,
                        help="Parallel Ollama calls. Ollama processes 1 at a time, rest queue.")
    parser.add_argument("--min-text", type=int, default=100,
                        help="Min text length to analyze (default 100)")
    args = parser.parse_args()
    asyncio.run(main(args.concurrency, args.min_text))
