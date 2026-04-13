"""
Integration tests for the Votes API (M3).

Tests exercise POST /api/ideas/{idea_id}/vote (toggle behaviour).
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
    email = f"votes_user_{_user_counter}_{uuid.uuid4().hex[:6]}@example.com"

    payload = {
        "name": f"Votes User {_user_counter}",
        "email": email,
        "password": "SecurePass123!",
        "role": role,
    }
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text

    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_test_idea(client: AsyncClient, headers: dict, title: str = "Vote Test Idea") -> dict:
    """Helper to create an idea and return the response JSON."""
    response = await client.post(
        "/api/ideas",
        json={"title": title, "description": "A detailed description for voting tests"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_votes_returns_voted_true_and_count_1(client: AsyncClient):
    """A user voting on an idea returns voted=True and votes_count=1."""
    user_headers = await register_and_login(client, role="user")
    idea = await create_test_idea(client, user_headers)

    response = await client.post(f"/api/ideas/{idea['id']}/vote", headers=user_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["voted"] is True
    assert data["votes_count"] == 1


@pytest.mark.asyncio
async def test_user_votes_again_toggles_off(client: AsyncClient):
    """Voting again on an already-voted idea removes the vote (voted=False, count=0)."""
    user_headers = await register_and_login(client, role="user")
    idea = await create_test_idea(client, user_headers)

    # First vote
    r1 = await client.post(f"/api/ideas/{idea['id']}/vote", headers=user_headers)
    assert r1.status_code == 200
    assert r1.json()["voted"] is True
    assert r1.json()["votes_count"] == 1

    # Toggle off
    r2 = await client.post(f"/api/ideas/{idea['id']}/vote", headers=user_headers)
    assert r2.status_code == 200
    assert r2.json()["voted"] is False
    assert r2.json()["votes_count"] == 0


@pytest.mark.asyncio
async def test_developer_can_vote(client: AsyncClient):
    """A developer role user can also vote on ideas."""
    user_headers = await register_and_login(client, role="user")
    dev_headers = await register_and_login(client, role="developer")
    idea = await create_test_idea(client, user_headers)

    response = await client.post(f"/api/ideas/{idea['id']}/vote", headers=dev_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["voted"] is True
    assert data["votes_count"] == 1


@pytest.mark.asyncio
async def test_admin_cannot_vote_returns_403(client: AsyncClient):
    """An admin is not allowed to vote; expects 403."""
    user_headers = await register_and_login(client, role="user")
    admin_headers = await register_and_login(client, role="admin")
    idea = await create_test_idea(client, user_headers)

    response = await client.post(f"/api/ideas/{idea['id']}/vote", headers=admin_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_vote_non_existent_idea_returns_404(client: AsyncClient):
    """Voting on a non-existent idea returns 404."""
    user_headers = await register_and_login(client, role="user")
    fake_id = str(uuid.uuid4())

    response = await client.post(f"/api/ideas/{fake_id}/vote", headers=user_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_votes_count_never_goes_below_zero(client: AsyncClient):
    """The votes_count should be 0 after toggling off from 0 state (handled via max)."""
    user_headers = await register_and_login(client, role="user")
    idea = await create_test_idea(client, user_headers)

    # Vote and then un-vote
    await client.post(f"/api/ideas/{idea['id']}/vote", headers=user_headers)
    r = await client.post(f"/api/ideas/{idea['id']}/vote", headers=user_headers)
    assert r.status_code == 200
    assert r.json()["votes_count"] >= 0


@pytest.mark.asyncio
async def test_multiple_users_vote_on_same_idea(client: AsyncClient):
    """Multiple different users voting increments the count correctly."""
    creator_headers = await register_and_login(client, role="user")
    user2_headers = await register_and_login(client, role="user")
    dev_headers = await register_and_login(client, role="developer")
    idea = await create_test_idea(client, creator_headers)

    r1 = await client.post(f"/api/ideas/{idea['id']}/vote", headers=creator_headers)
    assert r1.json()["votes_count"] == 1

    r2 = await client.post(f"/api/ideas/{idea['id']}/vote", headers=user2_headers)
    assert r2.json()["votes_count"] == 2

    r3 = await client.post(f"/api/ideas/{idea['id']}/vote", headers=dev_headers)
    assert r3.json()["votes_count"] == 3

    # One user un-votes
    r4 = await client.post(f"/api/ideas/{idea['id']}/vote", headers=user2_headers)
    assert r4.json()["voted"] is False
    assert r4.json()["votes_count"] == 2
