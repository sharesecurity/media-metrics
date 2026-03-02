"""
Bias analysis service.
Implements multiple bias detection methods that can be combined or used independently.
"""
import re
import json
from typing import Optional
from app.services.ollama import chat

# Simple word lists for lexical bias detection
EMOTIONALLY_CHARGED_WORDS = {
    "positive": ["champion", "hero", "triumph", "brilliant", "stellar", "outstanding"],
    "negative": ["radical", "extremist", "thug", "mob", "regime", "puppet", "cronies", "elite"],
}

HEDGE_WORDS = ["allegedly", "reportedly", "claimed", "according to", "sources say", "some say"]

async def analyze_bias(title: str, content: str, method: str = "llm") -> dict:
    """
    Run bias analysis on an article. Returns structured result dict.
    method: 'llm' | 'lexical' | 'combined'
    """
    result = {}

    if method in ("lexical", "combined"):
        result["lexical"] = _lexical_bias(content)

    if method in ("llm", "combined"):
        result["llm"] = await _llm_bias(title, content)

    # Aggregate score 0-10 (0=none, 10=extreme)
    scores = []
    if "lexical" in result:
        scores.append(result["lexical"]["score"])
    if "llm" in result:
        scores.append(result["llm"].get("bias_score", 5))
    result["aggregate_score"] = round(sum(scores) / len(scores), 2) if scores else None

    return result


def _lexical_bias(text: str) -> dict:
    """Simple rule-based lexical bias scoring."""
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    total_words = len(words) or 1

    neg_hits = [w for w in EMOTIONALLY_CHARGED_WORDS["negative"] if w in text_lower]
    pos_hits = [w for w in EMOTIONALLY_CHARGED_WORDS["positive"] if w in text_lower]
    hedge_hits = [h for h in HEDGE_WORDS if h in text_lower]

    charged_ratio = (len(neg_hits) + len(pos_hits)) / total_words * 1000  # per 1000 words
    score = min(10, charged_ratio * 2)

    return {
        "score": round(score, 2),
        "negative_words_found": neg_hits,
        "positive_words_found": pos_hits,
        "hedge_words_found": hedge_hits,
        "charged_ratio_per_1000": round(charged_ratio, 3),
    }


async def _llm_bias(title: str, content: str) -> dict:
    """Use local LLM to assess bias. Returns structured JSON."""
    snippet = content[:3000]  # keep it fast
    system = """You are a media bias analyst. Analyze the given article for bias.
Return ONLY valid JSON with these exact keys:
- bias_score: integer 0-10 (0=neutral, 10=extremely biased)
- political_lean: one of "left", "center-left", "center", "center-right", "right", "unknown"
- framing: brief description of how the story is framed (1-2 sentences)
- loaded_language: list of loaded/emotional phrases found (max 5)
- missing_perspectives: list of viewpoints that seem absent (max 3)
- summary: one sentence overall bias assessment"""

    prompt = f"Title: {title}\n\nArticle excerpt:\n{snippet}"

    try:
        raw = await chat(prompt, system=system)
        # Extract JSON even if model adds preamble
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        return {"error": str(e), "bias_score": 5, "political_lean": "unknown"}

    return {"raw_response": raw, "bias_score": 5, "political_lean": "unknown"}
