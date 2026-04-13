"""
Unit tests for app/services/ai_service.py.

All HuggingFace HTTP calls are mocked — no network required.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import app.services.ai_service as ai_service
from app.services.ai_service import (
    FALLBACK_CATEGORY,
    _compute_similarity,
    _tokenize,
    categorize_idea,
    find_similar_ideas,
)

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_LABELS = [
    "Natural Language Processing",
    "Computer Vision",
    "Process Automation",
    "Data Analytics",
    "Generative AI",
]

VALID_SCORES = [0.8, 0.1, 0.04, 0.03, 0.03]


def make_mock_response(status_code: int, json_data: dict | None = None):
    """Create a mock httpx response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.is_success = 200 <= status_code < 300
    mock.json.return_value = json_data or {}
    return mock


def make_async_client_cm(response):
    """
    Build a mock that behaves as `async with httpx.AsyncClient(...) as client:`.

    client.post(...) returns `response`.
    """
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# categorize_idea — success / HTTP error paths
# ---------------------------------------------------------------------------


async def test_categorize_success():
    """200 response with valid labels/scores → correct category returned."""
    resp = make_mock_response(
        200,
        {"labels": VALID_LABELS, "scores": VALID_SCORES},
    )
    with (
        patch("app.services.ai_service.settings") as mock_settings,
        patch("app.services.ai_service.httpx.AsyncClient", return_value=make_async_client_cm(resp)),
    ):
        mock_settings.HUGGINGFACE_TOKEN = "test-token"
        result = await categorize_idea("Build a chatbot using NLP")

    assert result["category"] == "Natural Language Processing"
    assert result["scores"]["Natural Language Processing"] == pytest.approx(0.8)
    assert set(result["scores"].keys()) == set(VALID_LABELS)


async def test_categorize_503_retry_success():
    """First call returns 503, second call returns 200 → success on retry."""
    resp_503 = make_mock_response(503)
    resp_200 = make_mock_response(
        200,
        {"labels": VALID_LABELS, "scores": VALID_SCORES},
    )

    call_count = 0

    async def fake_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return resp_503
        return resp_200

    mock_client = AsyncMock()
    mock_client.post = fake_post
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.ai_service.settings") as mock_settings,
        patch("app.services.ai_service.httpx.AsyncClient", return_value=cm),
        patch("app.services.ai_service.asyncio.sleep", new=AsyncMock()),
    ):
        mock_settings.HUGGINGFACE_TOKEN = "test-token"
        result = await categorize_idea("some description")

    assert result["category"] == "Natural Language Processing"
    assert call_count == 2


async def test_categorize_503_retry_failure():
    """Both attempts return 503 → fallback category."""
    resp_503 = make_mock_response(503)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp_503)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.ai_service.settings") as mock_settings,
        patch("app.services.ai_service.httpx.AsyncClient", return_value=cm),
        patch("app.services.ai_service.asyncio.sleep", new=AsyncMock()),
    ):
        mock_settings.HUGGINGFACE_TOKEN = "test-token"
        result = await categorize_idea("some description")

    assert result["category"] == FALLBACK_CATEGORY
    assert result["scores"] == {}


async def test_categorize_429_fallback():
    """429 rate-limit → fallback immediately, no retry."""
    resp = make_mock_response(429)

    with (
        patch("app.services.ai_service.settings") as mock_settings,
        patch("app.services.ai_service.httpx.AsyncClient", return_value=make_async_client_cm(resp)),
    ):
        mock_settings.HUGGINGFACE_TOKEN = "test-token"
        result = await categorize_idea("some description")

    assert result["category"] == FALLBACK_CATEGORY
    assert result["scores"] == {}


async def test_categorize_401_fallback():
    """401 auth error → fallback."""
    resp = make_mock_response(401)

    with (
        patch("app.services.ai_service.settings") as mock_settings,
        patch("app.services.ai_service.httpx.AsyncClient", return_value=make_async_client_cm(resp)),
    ):
        mock_settings.HUGGINGFACE_TOKEN = "test-token"
        result = await categorize_idea("some description")

    assert result["category"] == FALLBACK_CATEGORY
    assert result["scores"] == {}


async def test_categorize_timeout():
    """httpx.TimeoutException → fallback."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.ai_service.settings") as mock_settings,
        patch("app.services.ai_service.httpx.AsyncClient", return_value=cm),
    ):
        mock_settings.HUGGINGFACE_TOKEN = "test-token"
        result = await categorize_idea("some description")

    assert result["category"] == FALLBACK_CATEGORY
    assert result["scores"] == {}


async def test_categorize_malformed_response():
    """Response JSON missing 'labels' key → fallback (KeyError handled)."""
    resp = make_mock_response(200, {"unexpected": "data"})

    with (
        patch("app.services.ai_service.settings") as mock_settings,
        patch("app.services.ai_service.httpx.AsyncClient", return_value=make_async_client_cm(resp)),
    ):
        mock_settings.HUGGINGFACE_TOKEN = "test-token"
        result = await categorize_idea("some description")

    assert result["category"] == FALLBACK_CATEGORY
    assert result["scores"] == {}


async def test_categorize_missing_token():
    """No HUGGINGFACE_TOKEN set → immediate fallback, no HTTP call made."""
    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.HUGGINGFACE_TOKEN = ""
        result = await categorize_idea("some description")

    assert result["category"] == FALLBACK_CATEGORY
    assert result["scores"] == {}


# ---------------------------------------------------------------------------
# _compute_similarity / _tokenize
# ---------------------------------------------------------------------------


def test_compute_similarity_identical():
    """Identical texts → similarity == 1.0."""
    text = "build a machine learning pipeline for image recognition"
    assert _compute_similarity(text, text) == pytest.approx(1.0)


def test_compute_similarity_no_overlap():
    """Completely different words → similarity == 0.0."""
    assert _compute_similarity("apple banana cherry", "dog cat elephant") == pytest.approx(0.0)


def test_compute_similarity_partial():
    """Partial word overlap → 0 < similarity < 1."""
    score = _compute_similarity(
        "machine learning for image recognition",
        "image recognition using deep learning algorithms",
    )
    assert 0.0 < score < 1.0


def test_compute_similarity_empty():
    """Empty string → similarity == 0.0."""
    assert _compute_similarity("", "some text here") == pytest.approx(0.0)
    assert _compute_similarity("some text here", "") == pytest.approx(0.0)
    assert _compute_similarity("", "") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# find_similar_ideas
# ---------------------------------------------------------------------------


async def test_find_similar_empty_db():
    """Empty DB (no candidates) → empty list returned."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.HUGGINGFACE_TOKEN = ""  # forces fallback category
        result = await find_similar_ideas("build an NLP chatbot", mock_db)

    assert result == []


async def test_find_similar_below_threshold():
    """Candidates with similarity < 0.5 are excluded from results."""
    # Create a mock idea with very different description
    mock_idea = MagicMock()
    mock_idea.id = uuid.uuid4()
    mock_idea.title = "Completely Unrelated Idea"
    mock_idea.description = "This topic has absolutely nothing similar"
    mock_idea.category = "Other"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_idea]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.services.ai_service.settings") as mock_settings:
        mock_settings.HUGGINGFACE_TOKEN = ""
        # Use a description that shares zero content with the mock idea's description
        result = await find_similar_ideas(
            "quantum physics research laboratory experiments",
            mock_db,
        )

    assert result == []
