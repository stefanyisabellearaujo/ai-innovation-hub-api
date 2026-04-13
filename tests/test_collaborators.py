"""
Integration tests for the Collaborators API (M3).

Tests exercise POST /api/ideas/{idea_id}/collaborators (join)
and DELETE /api/ideas/{idea_id}/collaborators (leave).
"""
import uuid

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_user_counter = 0


async def register_and_login(client: AsyncClient, role: str = "user") -> dict:
    """Register a new unique user and return Authorization headers."""
    global _user_counter
    _user_counter += 1
    email = f"collab_user_{_user_counter}_{uuid.uuid4().hex[:6]}@example.com"

    payload = {
        "name": f"Collab User {_user_counter}",
        "email": email,
        "password": "SecurePass123!",
        "role": role,
    }
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text

    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_test_idea(client: AsyncClient, headers: dict, title: str = "Collab Test Idea") -> dict:
    """Helper to create an idea and return the response JSON."""
    response = await client.post(
        "/api/ideas",
        json={"title": title, "description": "A detailed description for collaboration tests"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_developer_joins_idea_returns_201_with_contributor_role(client: AsyncClient):
    """A developer can join an idea and the response includes role='contributor'."""
    user_headers = await register_and_login(client, role="user")
    dev_headers = await register_and_login(client, role="developer")
    idea = await create_test_idea(client, user_headers)

    response = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=dev_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "contributor"
    assert data["idea_id"] == idea["id"]
    assert "joined_at" in data


@pytest.mark.asyncio
async def test_developer_joins_same_idea_twice_returns_409(client: AsyncClient):
    """Joining the same idea twice returns 409 Conflict."""
    user_headers = await register_and_login(client, role="user")
    dev_headers = await register_and_login(client, role="developer")
    idea = await create_test_idea(client, user_headers)

    r1 = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=dev_headers)
    assert r1.status_code == 201

    r2 = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=dev_headers)
    assert r2.status_code == 409
    assert "Already a collaborator" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_user_cannot_join_idea_returns_403(client: AsyncClient):
    """A user (non-developer) cannot join an idea as collaborator; expects 403."""
    user_headers = await register_and_login(client, role="user")
    idea = await create_test_idea(client, user_headers)

    response = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_join_idea_returns_403(client: AsyncClient):
    """An admin cannot join an idea as collaborator; expects 403."""
    user_headers = await register_and_login(client, role="user")
    admin_headers = await register_and_login(client, role="admin")
    idea = await create_test_idea(client, user_headers)

    response = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=admin_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_max_3_collaborators_enforced(client: AsyncClient):
    """The 4th developer trying to join a fully-collaborated idea gets 409."""
    user_headers = await register_and_login(client, role="user")
    idea = await create_test_idea(client, user_headers)

    for _ in range(3):
        dev_headers = await register_and_login(client, role="developer")
        r = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=dev_headers)
        assert r.status_code == 201

    # 4th developer should be rejected
    extra_dev_headers = await register_and_login(client, role="developer")
    r4 = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=extra_dev_headers)
    assert r4.status_code == 409
    assert "Limite" in r4.json()["detail"] or "atingido" in r4.json()["detail"]


@pytest.mark.asyncio
async def test_developer_leaves_idea_returns_204(client: AsyncClient):
    """A developer who joined an idea can leave it; expects 204."""
    user_headers = await register_and_login(client, role="user")
    dev_headers = await register_and_login(client, role="developer")
    idea = await create_test_idea(client, user_headers)

    join_r = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=dev_headers)
    assert join_r.status_code == 201

    leave_r = await client.delete(f"/api/ideas/{idea['id']}/collaborators", headers=dev_headers)
    assert leave_r.status_code == 204


@pytest.mark.asyncio
async def test_leave_when_not_collaborator_returns_404(client: AsyncClient):
    """Trying to leave an idea you never joined returns 404."""
    user_headers = await register_and_login(client, role="user")
    dev_headers = await register_and_login(client, role="developer")
    idea = await create_test_idea(client, user_headers)

    response = await client.delete(f"/api/ideas/{idea['id']}/collaborators", headers=dev_headers)
    assert response.status_code == 404
    assert "Not a collaborator" in response.json()["detail"]


@pytest.mark.asyncio
async def test_join_non_existent_idea_returns_404(client: AsyncClient):
    """Joining a non-existent idea returns 404."""
    dev_headers = await register_and_login(client, role="developer")
    fake_id = str(uuid.uuid4())

    response = await client.post(f"/api/ideas/{fake_id}/collaborators", headers=dev_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_leave_non_existent_idea_returns_404(client: AsyncClient):
    """Leaving a non-existent idea returns 404."""
    dev_headers = await register_and_login(client, role="developer")
    fake_id = str(uuid.uuid4())

    response = await client.delete(f"/api/ideas/{fake_id}/collaborators", headers=dev_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_developer_can_rejoin_after_leaving(client: AsyncClient):
    """A developer who left an idea can join again."""
    user_headers = await register_and_login(client, role="user")
    dev_headers = await register_and_login(client, role="developer")
    idea = await create_test_idea(client, user_headers)

    await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=dev_headers)
    await client.delete(f"/api/ideas/{idea['id']}/collaborators", headers=dev_headers)

    rejoin_r = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=dev_headers)
    assert rejoin_r.status_code == 201
