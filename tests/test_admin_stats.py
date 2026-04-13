"""
Integration tests for GET /api/admin/stats (M5).
"""
import uuid

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_counter = 0


async def register_and_login(client: AsyncClient, role: str = "user") -> dict:
    """Register a new unique user and return Authorization headers."""
    global _counter
    _counter += 1
    email = f"stats_user_{_counter}_{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "name": f"Stats User {_counter}",
        "email": email,
        "password": "SecurePass123!",
        "role": role,
    }
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_idea(
    client: AsyncClient,
    headers: dict,
    title: str = "Test Idea",
    status: str | None = None,
) -> dict:
    """Create an idea and optionally advance its status."""
    payload: dict = {"title": title, "description": "A description for stats tests"}
    response = await client.post("/api/ideas", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    idea = response.json()

    if status and status != "idea":
        transitions = ["evaluation", "development", "completed", "archived"]
        for step in transitions:
            update_resp = await client.put(
                f"/api/ideas/{idea['id']}",
                json={"status": step},
                headers=headers,
            )
            assert update_resp.status_code == 200, update_resp.text
            idea = update_resp.json()
            if step == status:
                break

    return idea


# ---------------------------------------------------------------------------
# Tests — role access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_gets_stats_returns_200(client: AsyncClient):
    """Admin user can access GET /api/admin/stats and gets a 200 with correct structure."""
    admin_headers = await register_and_login(client, role="admin")

    response = await client.get("/api/admin/stats", headers=admin_headers)
    assert response.status_code == 200, response.text

    data = response.json()
    assert "total_ideas" in data
    assert "ideas_by_status" in data
    assert "ideas_by_category" in data
    assert "active_collaborators" in data

    assert isinstance(data["total_ideas"], int)
    assert isinstance(data["ideas_by_status"], dict)
    assert isinstance(data["ideas_by_category"], dict)
    assert isinstance(data["active_collaborators"], int)


@pytest.mark.asyncio
async def test_non_admin_user_gets_stats_returns_403(client: AsyncClient):
    """A regular user cannot access GET /api/admin/stats; expects 403."""
    user_headers = await register_and_login(client, role="user")
    response = await client.get("/api/admin/stats", headers=user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_developer_gets_stats_returns_403(client: AsyncClient):
    """A developer cannot access GET /api/admin/stats; expects 403."""
    dev_headers = await register_and_login(client, role="developer")
    response = await client.get("/api/admin/stats", headers=dev_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_gets_stats_returns_401(client: AsyncClient):
    """An unauthenticated request to GET /api/admin/stats returns 401."""
    response = await client.get("/api/admin/stats")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Tests — stats correctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_total_ideas_reflects_created_ideas(client: AsyncClient):
    """total_ideas increments correctly when ideas are created."""
    admin_headers = await register_and_login(client, role="admin")
    user_headers = await register_and_login(client, role="user")

    # Baseline
    before = (await client.get("/api/admin/stats", headers=admin_headers)).json()["total_ideas"]

    await create_idea(client, user_headers, title="Stats Idea A")
    await create_idea(client, user_headers, title="Stats Idea B")

    after = (await client.get("/api/admin/stats", headers=admin_headers)).json()["total_ideas"]
    assert after == before + 2


@pytest.mark.asyncio
async def test_stats_ideas_by_status_counts_correctly(client: AsyncClient):
    """ideas_by_status groups ideas correctly by their status value."""
    admin_headers = await register_and_login(client, role="admin")
    user_headers = await register_and_login(client, role="user")

    # Create an idea (default status = 'idea')
    await create_idea(client, user_headers, title="Status Count Idea")

    data = (await client.get("/api/admin/stats", headers=admin_headers)).json()
    # There must be at least one idea with status 'idea'
    assert data["ideas_by_status"].get("idea", 0) >= 1


@pytest.mark.asyncio
async def test_stats_ideas_by_category_counts_correctly(client: AsyncClient):
    """ideas_by_category groups ideas correctly — categories are set by the AI service."""
    admin_headers = await register_and_login(client, role="admin")
    user_headers = await register_and_login(client, role="user")

    # Create 2 ideas (category is auto-assigned by AI; when token missing, defaults to "Other")
    idea1 = await create_idea(client, user_headers, title="Cat Idea 1")
    idea2 = await create_idea(client, user_headers, title="Cat Idea 2")

    # The category assigned by the AI service (or "Other" when token is unset)
    assigned_category = idea1["category"]

    data = (await client.get("/api/admin/stats", headers=admin_headers)).json()
    # Both ideas share the same auto-assigned category; count must be >= 2
    assert data["ideas_by_category"].get(assigned_category, 0) >= 2


@pytest.mark.asyncio
async def test_stats_ideas_by_category_excludes_null_categories(client: AsyncClient):
    """ideas_by_category does not include a None/null key."""
    admin_headers = await register_and_login(client, role="admin")
    user_headers = await register_and_login(client, role="user")

    # Ideas without category (category=None by default)
    await create_idea(client, user_headers, title="No Cat Idea")

    data = (await client.get("/api/admin/stats", headers=admin_headers)).json()
    assert None not in data["ideas_by_category"]
    assert "null" not in data["ideas_by_category"]


@pytest.mark.asyncio
async def test_stats_active_collaborators_counts_correctly(client: AsyncClient):
    """active_collaborators counts distinct users who have at least one collaboration."""
    admin_headers = await register_and_login(client, role="admin")
    user_headers = await register_and_login(client, role="user")
    dev_headers = await register_and_login(client, role="developer")

    # Baseline count
    before = (await client.get("/api/admin/stats", headers=admin_headers)).json()[
        "active_collaborators"
    ]

    # Create idea and have the developer join
    idea = await create_idea(client, user_headers, title="Collab Stats Idea")
    join_resp = await client.post(
        f"/api/ideas/{idea['id']}/collaborators", headers=dev_headers
    )
    assert join_resp.status_code == 201, join_resp.text

    after = (await client.get("/api/admin/stats", headers=admin_headers)).json()[
        "active_collaborators"
    ]
    assert after == before + 1


@pytest.mark.asyncio
async def test_stats_active_collaborators_counts_distinct_users(client: AsyncClient):
    """A developer joining multiple ideas counts as 1 active collaborator, not multiple."""
    admin_headers = await register_and_login(client, role="admin")
    user_headers = await register_and_login(client, role="user")
    dev_headers = await register_and_login(client, role="developer")

    idea1 = await create_idea(client, user_headers, title="Distinct Collab Idea 1")
    idea2 = await create_idea(client, user_headers, title="Distinct Collab Idea 2")

    before = (await client.get("/api/admin/stats", headers=admin_headers)).json()[
        "active_collaborators"
    ]

    r1 = await client.post(f"/api/ideas/{idea1['id']}/collaborators", headers=dev_headers)
    r2 = await client.post(f"/api/ideas/{idea2['id']}/collaborators", headers=dev_headers)
    assert r1.status_code == 201
    assert r2.status_code == 201

    after = (await client.get("/api/admin/stats", headers=admin_headers)).json()[
        "active_collaborators"
    ]
    # Developer joined 2 ideas but counts as 1 distinct collaborator
    assert after == before + 1
