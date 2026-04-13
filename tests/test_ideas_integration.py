"""
Integration tests for the Ideas CRUD API (M2).

These tests exercise the full HTTP stack against an in-memory SQLite database
using the fixtures defined in conftest.py.
"""
import uuid

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_user_counter = 0


async def register_and_login(client: AsyncClient, role: str = "user") -> dict:
    """
    Register a new user with the given role and return Authorization headers.

    A unique email is generated per call so tests remain independent.
    """
    global _user_counter
    _user_counter += 1
    email = f"testuser_{_user_counter}_{uuid.uuid4().hex[:6]}@example.com"

    payload = {
        "name": f"Test User {_user_counter}",
        "email": email,
        "password": "SecurePass123!",
        "role": role,
    }
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text

    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_test_idea(
    client: AsyncClient,
    headers: dict,
    title: str = "Test Idea",
    description: str = "A detailed description of the test idea",
    priority: str = "medium",
) -> dict:
    """Helper to create an idea and return the response JSON."""
    response = await client.post(
        "/api/ideas",
        json={"title": title, "description": description, "priority": priority},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Create idea tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_creates_idea_returns_201_with_category(client: AsyncClient):
    """A user with the 'user' role can create an idea; response includes category."""
    headers = await register_and_login(client, role="user")
    response = await client.post(
        "/api/ideas",
        json={
            "title": "Automate reporting",
            "description": "Use AI to automate monthly expense reports",
            "priority": "high",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Automate reporting"
    assert data["status"] == "idea"
    assert data["priority"] == "high"
    assert "category" in data  # may be None or a string, must be present in payload
    assert "id" in data
    assert "author" in data


@pytest.mark.asyncio
async def test_developer_creates_idea_returns_201(client: AsyncClient):
    """A developer role user can create an idea."""
    headers = await register_and_login(client, role="developer")
    response = await client.post(
        "/api/ideas",
        json={
            "title": "Build recommendation engine",
            "description": "Implement collaborative filtering for product recommendations",
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "idea"


@pytest.mark.asyncio
async def test_admin_creates_idea_returns_403(client: AsyncClient):
    """Admins are not allowed to create ideas."""
    headers = await register_and_login(client, role="admin")
    response = await client.post(
        "/api/ideas",
        json={
            "title": "Admin idea",
            "description": "Admins should not be able to create ideas",
        },
        headers=headers,
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# List ideas tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_ideas_no_filters_returns_paginated_response(client: AsyncClient):
    """GET /api/ideas returns a valid paginated response structure."""
    headers = await register_and_login(client, role="user")
    # Create a couple of ideas so the list is non-empty
    await create_test_idea(client, headers, title="Idea Alpha")
    await create_test_idea(client, headers, title="Idea Beta")

    response = await client.get("/api/ideas", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "per_page" in data
    assert "pages" in data
    assert isinstance(data["items"], list)
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_list_ideas_with_status_filter(client: AsyncClient):
    """Filtering by status returns only ideas with that status."""
    headers = await register_and_login(client, role="user")
    await create_test_idea(client, headers, title="Status Filter Idea")

    response = await client.get("/api/ideas?status=idea", headers=headers)
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["status"] == "idea"


@pytest.mark.asyncio
async def test_list_ideas_with_search_filter(client: AsyncClient):
    """Search filter returns only ideas whose title or description matches."""
    headers = await register_and_login(client, role="user")
    unique_keyword = f"xqz{uuid.uuid4().hex[:8]}"
    await create_test_idea(
        client,
        headers,
        title=f"Unique {unique_keyword} Idea",
        description="Generic description",
    )

    response = await client.get(f"/api/ideas?search={unique_keyword}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert any(unique_keyword in item["title"] for item in data["items"])


@pytest.mark.asyncio
async def test_list_ideas_per_page_exceeds_100_returns_422(client: AsyncClient):
    """Requesting more than 100 items per page is rejected with 422."""
    headers = await register_and_login(client, role="user")
    response = await client.get("/api/ideas?per_page=101", headers=headers)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Get idea by ID tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_idea_by_valid_id_returns_200(client: AsyncClient):
    """GET /api/ideas/{id} returns the idea for a valid UUID."""
    headers = await register_and_login(client, role="user")
    created = await create_test_idea(client, headers, title="Detail Test Idea")
    idea_id = created["id"]

    response = await client.get(f"/api/ideas/{idea_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == idea_id
    assert data["title"] == "Detail Test Idea"


@pytest.mark.asyncio
async def test_get_idea_by_invalid_id_returns_404(client: AsyncClient):
    """GET /api/ideas/{id} returns 404 for a non-existent UUID."""
    headers = await register_and_login(client, role="user")
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/ideas/{fake_id}", headers=headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update idea tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_author_updates_own_idea_returns_200(client: AsyncClient):
    """The author can update their own idea's title and description."""
    headers = await register_and_login(client, role="user")
    created = await create_test_idea(client, headers)
    idea_id = created["id"]

    response = await client.put(
        f"/api/ideas/{idea_id}",
        json={"title": "Updated Title", "description": "Updated description content here"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_non_author_updates_idea_returns_403(client: AsyncClient):
    """A user who is neither author nor collaborator cannot update the idea."""
    author_headers = await register_and_login(client, role="user")
    other_headers = await register_and_login(client, role="user")

    created = await create_test_idea(client, author_headers)
    idea_id = created["id"]

    response = await client.put(
        f"/api/ideas/{idea_id}",
        json={"title": "Unauthorized Update"},
        headers=other_headers,
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Delete idea tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_author_deletes_own_idea_returns_204(client: AsyncClient):
    """The author can delete their own idea."""
    headers = await register_and_login(client, role="user")
    created = await create_test_idea(client, headers, title="To Be Deleted")
    idea_id = created["id"]

    response = await client.delete(f"/api/ideas/{idea_id}", headers=headers)
    assert response.status_code == 204

    # Verify it's gone
    get_response = await client.get(f"/api/ideas/{idea_id}", headers=headers)
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_non_author_deletes_idea_returns_403(client: AsyncClient):
    """A non-author cannot delete another user's idea."""
    author_headers = await register_and_login(client, role="user")
    other_headers = await register_and_login(client, role="user")

    created = await create_test_idea(client, author_headers, title="Protected Idea")
    idea_id = created["id"]

    response = await client.delete(f"/api/ideas/{idea_id}", headers=other_headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Status transition tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_status_transition_idea_to_evaluation_returns_200(client: AsyncClient):
    """Transitioning from 'idea' to 'evaluation' is a valid workflow step."""
    headers = await register_and_login(client, role="user")
    created = await create_test_idea(client, headers)
    idea_id = created["id"]
    assert created["status"] == "idea"

    response = await client.put(
        f"/api/ideas/{idea_id}",
        json={"status": "evaluation"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "evaluation"


@pytest.mark.asyncio
async def test_invalid_status_transition_idea_to_completed_returns_422(client: AsyncClient):
    """Transitioning directly from 'idea' to 'completed' is not allowed."""
    headers = await register_and_login(client, role="user")
    created = await create_test_idea(client, headers)
    idea_id = created["id"]
    assert created["status"] == "idea"

    response = await client.put(
        f"/api/ideas/{idea_id}",
        json={"status": "completed"},
        headers=headers,
    )
    assert response.status_code == 422
