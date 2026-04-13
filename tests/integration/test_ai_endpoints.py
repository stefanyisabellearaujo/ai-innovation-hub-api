"""
Integration tests for /api/ai endpoints.

HuggingFace HTTP calls are mocked. Tests run against the in-memory SQLite DB
via the `client` fixture defined in conftest.py.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_counter = 0


async def register_and_login(client: AsyncClient, role: str = "user") -> dict:
    """Register a unique user and return Authorization headers."""
    global _counter
    _counter += 1
    email = f"ai_test_{_counter}_{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "name": f"AI Test User {_counter}",
        "email": email,
        "password": "SecurePass123!",
        "role": role,
    }
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def make_mock_response(status_code: int, json_data: dict | None = None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.is_success = 200 <= status_code < 300
    mock.json.return_value = json_data or {}
    return mock


def mock_hf_success(category: str = "Natural Language Processing"):
    """Return a context-manager patch for a successful HF categorize call."""
    labels = [
        category,
        "Computer Vision",
        "Process Automation",
        "Data Analytics",
        "Generative AI",
    ]
    scores = [0.8, 0.1, 0.04, 0.03, 0.03]
    resp = make_mock_response(200, {"labels": labels, "scores": scores})
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def mock_hf_failure():
    """Return a context-manager patch that simulates a HF 503 failure."""
    resp = make_mock_response(503)
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# POST /api/ai/categorize
# ---------------------------------------------------------------------------


async def test_categorize_authenticated(client: AsyncClient):
    """Authenticated request → 200 with category and scores."""
    headers = await register_and_login(client)

    with (
        patch("app.services.ai_service.settings") as mock_settings,
        patch("app.services.ai_service.httpx.AsyncClient", return_value=mock_hf_success()),
    ):
        mock_settings.HUGGINGFACE_TOKEN = "test-token"
        resp = await client.post(
            "/api/ai/categorize",
            json={"description": "Build a chatbot using natural language processing"},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "Natural Language Processing"
    assert isinstance(data["scores"], dict)
    assert len(data["scores"]) > 0


async def test_categorize_unauthenticated(client: AsyncClient):
    """No auth token → 401."""
    resp = await client.post(
        "/api/ai/categorize",
        json={"description": "Some idea description"},
    )
    assert resp.status_code == 401


async def test_categorize_empty_description(client: AsyncClient):
    """Empty description string → 422 validation error."""
    headers = await register_and_login(client)
    resp = await client.post(
        "/api/ai/categorize",
        json={"description": ""},
        headers=headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/ai/similar
# ---------------------------------------------------------------------------


async def test_similar_authenticated(client: AsyncClient):
    """Authenticated request with an idea in DB → 200 with similar_ideas list."""
    headers = await register_and_login(client)

    # Create an idea so there's at least one candidate
    with (
        patch("app.services.ai_service.settings") as mock_settings,
        patch("app.services.ai_service.httpx.AsyncClient", return_value=mock_hf_success()),
    ):
        mock_settings.HUGGINGFACE_TOKEN = "test-token"
        create_resp = await client.post(
            "/api/ideas",
            json={
                "title": "NLP Chatbot",
                "description": "Build a chatbot using natural language processing and machine learning",
                "priority": "high",
            },
            headers=headers,
        )
    assert create_resp.status_code == 201

    # Find similar — mock HF again for the /similar call
    with (
        patch("app.services.ai_service.settings") as mock_settings,
        patch("app.services.ai_service.httpx.AsyncClient", return_value=mock_hf_success()),
    ):
        mock_settings.HUGGINGFACE_TOKEN = "test-token"
        resp = await client.post(
            "/api/ai/similar",
            json={
                "description": "Build a chatbot using natural language processing and machine learning"
            },
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "similar_ideas" in data
    assert isinstance(data["similar_ideas"], list)


async def test_similar_unauthenticated(client: AsyncClient):
    """No auth token → 401."""
    resp = await client.post(
        "/api/ai/similar",
        json={"description": "Some description to find similar ideas for"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Idea creation integrates AI categorization
# ---------------------------------------------------------------------------


async def test_idea_creation_sets_category(client: AsyncClient):
    """Creating an idea calls AI and stores the returned category."""
    headers = await register_and_login(client)

    with (
        patch("app.services.ai_service.settings") as mock_settings,
        patch("app.services.ai_service.httpx.AsyncClient", return_value=mock_hf_success("Generative AI")),
    ):
        mock_settings.HUGGINGFACE_TOKEN = "test-token"
        resp = await client.post(
            "/api/ideas",
            json={
                "title": "Generate images with AI",
                "description": "Use generative AI models to create realistic product images",
                "priority": "medium",
            },
            headers=headers,
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] == "Generative AI"


async def test_idea_creation_succeeds_when_ai_fails(client: AsyncClient):
    """If HuggingFace fails, idea is still created with category='Other'."""
    headers = await register_and_login(client)

    with (
        patch("app.services.ai_service.settings") as mock_settings,
        patch("app.services.ai_service.httpx.AsyncClient", return_value=mock_hf_failure()),
        patch("app.services.ai_service.asyncio.sleep", new=AsyncMock()),
    ):
        mock_settings.HUGGINGFACE_TOKEN = "test-token"
        resp = await client.post(
            "/api/ideas",
            json={
                "title": "Fallback category idea",
                "description": "This idea should get category Other when AI is unavailable",
                "priority": "low",
            },
            headers=headers,
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] == "Other"
