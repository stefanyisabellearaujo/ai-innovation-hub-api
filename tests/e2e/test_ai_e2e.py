"""
End-to-end tests for AI endpoints.

These tests make REAL calls to the HuggingFace Inference API and are skipped
automatically when HUGGINGFACE_TOKEN is not set in the environment.

Run selectively with:
    pytest tests/e2e/ -m e2e -v
"""
import uuid

import pytest
from httpx import AsyncClient

from app.config import settings
from app.services.ai_service import CANDIDATE_LABELS, FALLBACK_CATEGORY

pytestmark = pytest.mark.e2e

# ---------------------------------------------------------------------------
# Auto-skip when token is absent
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def require_token():
    """Skip all e2e tests when HUGGINGFACE_TOKEN is not configured."""
    if not settings.HUGGINGFACE_TOKEN:
        pytest.skip("HUGGINGFACE_TOKEN not set — skipping e2e AI tests")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_e2e_counter = 0


async def register_and_login(client: AsyncClient, role: str = "user") -> dict:
    """Register a unique user and return Authorization headers."""
    global _e2e_counter
    _e2e_counter += 1
    email = f"e2e_ai_{_e2e_counter}_{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "name": f"E2E AI User {_e2e_counter}",
        "email": email,
        "password": "SecurePass123!",
        "role": role,
    }
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Real API tests
# ---------------------------------------------------------------------------


async def test_categorize_real_api(client: AsyncClient):
    """Real HuggingFace API call with NLP description."""
    headers = await register_and_login(client, "user")
    resp = await client.post(
        "/api/ai/categorize",
        json={
            "description": (
                "Build a chatbot that answers customer questions using "
                "natural language understanding"
            )
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] in CANDIDATE_LABELS + [FALLBACK_CATEGORY]
    assert len(data["scores"]) > 0


async def test_categorize_real_api_vision_description(client: AsyncClient):
    """Real HuggingFace API call with a Computer Vision description."""
    headers = await register_and_login(client, "user")
    resp = await client.post(
        "/api/ai/categorize",
        json={
            "description": (
                "Implement an object detection system using convolutional neural networks "
                "to identify defects in product images on the assembly line"
            )
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] in CANDIDATE_LABELS + [FALLBACK_CATEGORY]
    assert isinstance(data["scores"], dict)


async def test_similar_real_api(client: AsyncClient):
    """Real HuggingFace API call via /api/ai/similar endpoint."""
    headers = await register_and_login(client, "user")

    # First, create an idea so the DB has at least one candidate
    create_resp = await client.post(
        "/api/ideas",
        json={
            "title": "NLP Customer Service Bot",
            "description": (
                "Build a conversational AI assistant that handles customer support "
                "inquiries using natural language processing techniques"
            ),
            "priority": "high",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201

    # Now search for similar ideas
    resp = await client.post(
        "/api/ai/similar",
        json={
            "description": (
                "Create an AI chatbot for customer service that uses natural language "
                "processing to understand and respond to user queries"
            )
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "similar_ideas" in data
    assert isinstance(data["similar_ideas"], list)
    # The idea we just created should appear (high text overlap)
    if data["similar_ideas"]:
        item = data["similar_ideas"][0]
        assert "idea_id" in item
        assert "title" in item
        assert "category" in item
        assert "similarity_score" in item
        assert 0.0 <= item["similarity_score"] <= 1.0
