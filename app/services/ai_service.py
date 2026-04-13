import asyncio
import logging
from typing import Any
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

HUGGINGFACE_API_URL = "https://router.huggingface.co/hf-inference/models/facebook/bart-large-mnli"

CANDIDATE_LABELS = [
    "Natural Language Processing",
    "Computer Vision",
    "Process Automation",
    "Data Analytics",
    "Generative AI",
]

FALLBACK_CATEGORY = "Other"
TIMEOUT_SECONDS = 10.0
RETRY_DELAY_SECONDS = 2.0
MAX_CONCURRENT_REQUESTS = 5

_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "through", "during",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "shall", "can", "need", "dare", "ought", "used", "this", "that", "these",
    "those", "it", "its", "we", "i", "you", "he", "she", "they", "my", "your",
    "our", "their", "not", "no", "nor", "so", "yet", "both", "either", "neither",
}


async def categorize_idea(description: str) -> dict[str, Any]:
    """
    Classify an idea description using HuggingFace zero-shot classification.

    Returns dict with keys:
      - category (str): top label, or FALLBACK_CATEGORY on any failure
      - scores (dict[str, float]): label->score map, or empty dict on failure

    Never raises — always returns a valid dict.
    """
    if not settings.HUGGINGFACE_TOKEN:
        logger.critical("HUGGINGFACE_TOKEN is not set — skipping AI categorization")
        return {"category": FALLBACK_CATEGORY, "scores": {}}

    headers = {"Authorization": f"Bearer {settings.HUGGINGFACE_TOKEN}"}
    payload = {
        "inputs": description,
        "parameters": {"candidate_labels": CANDIDATE_LABELS},
    }

    async with _semaphore:
        return await _call_with_retry(headers, payload)


async def _call_with_retry(headers: dict, payload: dict) -> dict[str, Any]:
    """Call HuggingFace API with one retry on 503 (cold start)."""
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.post(HUGGINGFACE_API_URL, headers=headers, json=payload)

            if response.status_code == 503:
                if attempt == 0:
                    logger.warning("HuggingFace 503 (cold start), retrying in %ss", RETRY_DELAY_SECONDS)
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue
                else:
                    logger.error("HuggingFace 503 on retry — using fallback")
                    return {"category": FALLBACK_CATEGORY, "scores": {}}

            if response.status_code == 429:
                logger.warning("HuggingFace rate limit (429) — using fallback")
                return {"category": FALLBACK_CATEGORY, "scores": {}}

            if response.status_code in (401, 403):
                logger.error("HuggingFace auth error (%s) — check token", response.status_code)
                return {"category": FALLBACK_CATEGORY, "scores": {}}

            if not response.is_success:
                logger.error("HuggingFace unexpected status %s", response.status_code)
                return {"category": FALLBACK_CATEGORY, "scores": {}}

            data = response.json()

            # New router.huggingface.co format: [{"label": str, "score": float}, ...]
            # Old api-inference format: {"labels": [...], "scores": [...]}
            if isinstance(data, list):
                sorted_data = sorted(data, key=lambda x: x["score"], reverse=True)
                scores_map = {item["label"]: item["score"] for item in sorted_data}
                top_label = sorted_data[0]["label"]
            else:
                labels: list[str] = data["labels"]
                scores_list: list[float] = data["scores"]
                scores_map = dict(zip(labels, scores_list))
                top_label = labels[0]

            return {"category": top_label, "scores": scores_map}

        except httpx.TimeoutException:
            logger.error("HuggingFace request timed out after %ss", TIMEOUT_SECONDS)
            return {"category": FALLBACK_CATEGORY, "scores": {}}
        except (KeyError, TypeError, ValueError) as e:
            logger.error("HuggingFace malformed response: %s", e)
            return {"category": FALLBACK_CATEGORY, "scores": {}}
        except Exception as e:
            logger.error("HuggingFace unexpected error: %s", e)
            return {"category": FALLBACK_CATEGORY, "scores": {}}

    return {"category": FALLBACK_CATEGORY, "scores": {}}


def _tokenize(text: str) -> list[str]:
    """Lowercase, extract alphanumeric tokens, remove stopwords and single-char tokens."""
    import re
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def _compute_similarity(text_a: str, text_b: str) -> float:
    """Compute Sorensen-Dice similarity coefficient between two texts."""
    tokens_a = set(_tokenize(text_a))
    tokens_b = set(_tokenize(text_b))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    return (2 * len(intersection)) / (len(tokens_a) + len(tokens_b))


async def find_similar_ideas(
    description: str,
    title: str = "",
    db=None,
    exclude_id=None,
) -> list[dict]:
    """
    Find similar ideas using a two-pass strategy:

    Pass 1 — category match: ideas with the same AI-assigned category,
              scored by description similarity.
    Pass 2 — keyword match: ALL ideas scored by combined title+description
              similarity, used when Pass 1 returns fewer than 3 results.

    This handles ideas created before AI was working (wrong/Other category)
    and short descriptions that don't match well on content alone.

    Returns up to 5 results with similarity_score >= 0.25, sorted descending.
    """
    from sqlalchemy import select
    from app.models.idea import Idea

    if db is None:
        return []

    logger.info("AI similar — title=%r desc_length=%d", title[:50] if title else "", len(description))

    # Combined text for comparison (title carries more signal)
    input_text = f"{title} {title} {description}".strip()

    # Phase 1: categorize the input
    ai_result = await categorize_idea(description or title)
    category = ai_result["category"]

    logger.info("AI similar — category assigned: %s", category)

    # Phase 2: fetch ALL ideas (we score and filter in Python)
    query = select(Idea)
    if exclude_id is not None:
        query = query.where(Idea.id != exclude_id)
    result = await db.execute(query)
    all_ideas = result.scalars().all()

    # Phase 3: score each idea
    # Score = weighted average of title similarity and description similarity
    # Title similarity is weighted higher because it captures the intent better
    scored = []
    for idea in all_ideas:
        idea_text = f"{idea.title} {idea.title} {idea.description or ''}".strip()
        content_score = _compute_similarity(input_text, idea_text)

        # Bonus when category matches (AI agreement)
        if category != FALLBACK_CATEGORY and idea.category == category:
            final_score = min(1.0, content_score + 0.15)
        else:
            final_score = content_score

        if final_score >= 0.25:
            scored.append({
                "idea_id": idea.id,
                "title": idea.title,
                "category": idea.category or FALLBACK_CATEGORY,
                "similarity_score": round(final_score, 2),
            })

    scored.sort(key=lambda x: x["similarity_score"], reverse=True)
    top = scored[:5]

    logger.info("AI similar — found %d above threshold, returning %d", len(scored), len(top))
    return top
