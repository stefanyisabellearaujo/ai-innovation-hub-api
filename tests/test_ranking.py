"""
Integration tests for GET /api/ranking/developers (M5).
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
    email = f"ranking_user_{_counter}_{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "name": f"Ranking User {_counter}",
        "email": email,
        "password": "SecurePass123!",
        "role": role,
    }
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_idea(client: AsyncClient, headers: dict, title: str = "Ranking Test Idea") -> dict:
    """Create an idea and return its JSON."""
    response = await client.post(
        "/api/ideas",
        json={"title": title, "description": "A description for ranking tests"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def advance_idea_to_status(
    client: AsyncClient,
    idea_id: str,
    target_status: str,
    author_headers: dict,
) -> None:
    """
    Advance an idea through the status workflow up to target_status.
    Valid chain: idea -> evaluation -> development -> completed -> archived
    """
    transitions = ["evaluation", "development", "completed", "archived"]
    for step in transitions:
        resp = await client.put(
            f"/api/ideas/{idea_id}",
            json={"status": step},
            headers=author_headers,
        )
        assert resp.status_code == 200, f"Failed to set status to {step}: {resp.text}"
        if step == target_status:
            break


# ---------------------------------------------------------------------------
# Tests — role access
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_developer_gets_ranking_returns_200(client: AsyncClient):
    """A developer can access GET /api/ranking/developers and receives 200."""
    dev_headers = await register_and_login(client, role="developer")
    response = await client.get("/api/ranking/developers", headers=dev_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "rankings" in data
    assert isinstance(data["rankings"], list)


@pytest.mark.asyncio
async def test_user_gets_ranking_returns_403(client: AsyncClient):
    """A regular user cannot access GET /api/ranking/developers; expects 403."""
    user_headers = await register_and_login(client, role="user")
    response = await client.get("/api/ranking/developers", headers=user_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_gets_ranking_returns_403(client: AsyncClient):
    """An admin cannot access GET /api/ranking/developers; expects 403."""
    admin_headers = await register_and_login(client, role="admin")
    response = await client.get("/api/ranking/developers", headers=admin_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_gets_ranking_returns_401(client: AsyncClient):
    """An unauthenticated request to GET /api/ranking/developers returns 401."""
    response = await client.get("/api/ranking/developers")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Tests — ranking structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ranking_entries_have_correct_structure(client: AsyncClient):
    """Each entry in the ranking has rank, user_id, name, completed_count, in_progress_count."""
    dev_headers = await register_and_login(client, role="developer")
    response = await client.get("/api/ranking/developers", headers=dev_headers)
    assert response.status_code == 200

    data = response.json()
    # Verify we have at least one developer (the one we just created)
    assert len(data["rankings"]) >= 1

    entry = data["rankings"][0]
    assert "rank" in entry
    assert "user_id" in entry
    assert "name" in entry
    assert "completed_count" in entry
    assert "in_progress_count" in entry

    assert isinstance(entry["rank"], int)
    assert isinstance(entry["user_id"], str)
    assert isinstance(entry["name"], str)
    assert isinstance(entry["completed_count"], int)
    assert isinstance(entry["in_progress_count"], int)


@pytest.mark.asyncio
async def test_ranking_ranks_are_sequential_from_one(client: AsyncClient):
    """Rank values start at 1 and are sequential."""
    dev_headers = await register_and_login(client, role="developer")
    response = await client.get("/api/ranking/developers", headers=dev_headers)
    assert response.status_code == 200

    rankings = response.json()["rankings"]
    for i, entry in enumerate(rankings, start=1):
        assert entry["rank"] == i, f"Expected rank {i}, got {entry['rank']}"


# ---------------------------------------------------------------------------
# Tests — ranking correctness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_developers_with_no_collaborations_appear_with_zero_count(client: AsyncClient):
    """Developers who have never collaborated still appear in the ranking with count=0."""
    # Register a fresh developer who will not join any idea
    dev_headers = await register_and_login(client, role="developer")
    me_resp = await client.get("/api/ideas", headers=dev_headers)  # any auth'd request to get token working

    response = await client.get("/api/ranking/developers", headers=dev_headers)
    assert response.status_code == 200

    rankings = response.json()["rankings"]
    # Find a developer with zero completed collaborations
    zero_entries = [e for e in rankings if e["completed_count"] == 0 and e["in_progress_count"] == 0]
    assert len(zero_entries) >= 1, "Expected at least one developer with 0 completed collaborations"


@pytest.mark.asyncio
async def test_ranking_ordered_by_completed_count_descending(client: AsyncClient):
    """The ranking is sorted by completed_count in descending order."""
    user_headers = await register_and_login(client, role="user")
    dev_a_headers = await register_and_login(client, role="developer")
    dev_b_headers = await register_and_login(client, role="developer")

    # dev_a completes 2 ideas; dev_b completes 1 idea
    for i in range(2):
        idea = await create_idea(client, user_headers, title=f"Completed Idea A-{i}")
        r = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=dev_a_headers)
        assert r.status_code == 201, r.text
        await advance_idea_to_status(client, idea["id"], "completed", user_headers)

    idea_b = await create_idea(client, user_headers, title="Completed Idea B-0")
    r = await client.post(f"/api/ideas/{idea_b['id']}/collaborators", headers=dev_b_headers)
    assert r.status_code == 201, r.text
    await advance_idea_to_status(client, idea_b["id"], "completed", user_headers)

    # Fetch ranking (as dev_a)
    response = await client.get("/api/ranking/developers", headers=dev_a_headers)
    assert response.status_code == 200

    rankings = response.json()["rankings"]
    completed_counts = [e["completed_count"] for e in rankings]
    # Verify descending order
    assert completed_counts == sorted(completed_counts, reverse=True), (
        f"Rankings are not sorted by completed_count desc: {completed_counts}"
    )


@pytest.mark.asyncio
async def test_ranking_secondary_sort_by_in_progress_count(client: AsyncClient):
    """When completed_count is equal, in_progress_count is used as tiebreaker (desc)."""
    user_headers = await register_and_login(client, role="user")
    dev_a_headers = await register_and_login(client, role="developer")
    dev_b_headers = await register_and_login(client, role="developer")

    # Both dev_a and dev_b have 0 completed. dev_a has 2 in-progress, dev_b has 1.
    for i in range(2):
        idea = await create_idea(client, user_headers, title=f"InProg Idea A-{i}")
        r = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=dev_a_headers)
        assert r.status_code == 201
        # Advance to development (in_progress)
        await advance_idea_to_status(client, idea["id"], "development", user_headers)

    idea_b = await create_idea(client, user_headers, title="InProg Idea B-0")
    r = await client.post(f"/api/ideas/{idea_b['id']}/collaborators", headers=dev_b_headers)
    assert r.status_code == 201
    await advance_idea_to_status(client, idea_b["id"], "development", user_headers)

    response = await client.get("/api/ranking/developers", headers=dev_a_headers)
    assert response.status_code == 200

    rankings = response.json()["rankings"]
    # All should be ordered: completed desc, then in_progress desc
    for i in range(len(rankings) - 1):
        a = rankings[i]
        b = rankings[i + 1]
        assert (a["completed_count"], a["in_progress_count"]) >= (
            b["completed_count"],
            b["in_progress_count"],
        ), f"Ranking not properly ordered at index {i}: {a} vs {b}"


@pytest.mark.asyncio
async def test_ranking_completed_count_reflects_collaborations(client: AsyncClient):
    """A developer's completed_count matches the number of completed idea collaborations."""
    user_headers = await register_and_login(client, role="user")
    dev_headers = await register_and_login(client, role="developer")

    # Get developer's user_id from registration response
    email = f"rankcheck_{uuid.uuid4().hex[:8]}@example.com"
    reg_resp = await client.post(
        "/api/auth/register",
        json={"name": "Rank Check Dev", "email": email, "password": "SecurePass123!", "role": "developer"},
    )
    assert reg_resp.status_code == 201
    dev_id = reg_resp.json()["user"]["id"]
    fresh_dev_headers = {"Authorization": f"Bearer {reg_resp.json()['access_token']}"}

    # Complete 3 ideas as this developer
    for i in range(3):
        idea = await create_idea(client, user_headers, title=f"Count Check Idea {i}")
        r = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=fresh_dev_headers)
        assert r.status_code == 201, r.text
        await advance_idea_to_status(client, idea["id"], "completed", user_headers)

    response = await client.get("/api/ranking/developers", headers=fresh_dev_headers)
    assert response.status_code == 200

    rankings = response.json()["rankings"]
    dev_entry = next((e for e in rankings if e["user_id"] == dev_id), None)
    assert dev_entry is not None, f"Developer {dev_id} not found in ranking"
    assert dev_entry["completed_count"] == 3, (
        f"Expected completed_count=3, got {dev_entry['completed_count']}"
    )


@pytest.mark.asyncio
async def test_ranking_in_progress_count_reflects_development_collaborations(client: AsyncClient):
    """A developer's in_progress_count matches ideas in 'development' status."""
    user_headers = await register_and_login(client, role="user")

    email = f"inprog_check_{uuid.uuid4().hex[:8]}@example.com"
    reg_resp = await client.post(
        "/api/auth/register",
        json={"name": "InProg Check Dev", "email": email, "password": "SecurePass123!", "role": "developer"},
    )
    assert reg_resp.status_code == 201
    dev_id = reg_resp.json()["user"]["id"]
    fresh_dev_headers = {"Authorization": f"Bearer {reg_resp.json()['access_token']}"}

    # Put 2 ideas into development status
    for i in range(2):
        idea = await create_idea(client, user_headers, title=f"InProg Check Idea {i}")
        r = await client.post(f"/api/ideas/{idea['id']}/collaborators", headers=fresh_dev_headers)
        assert r.status_code == 201, r.text
        await advance_idea_to_status(client, idea["id"], "development", user_headers)

    response = await client.get("/api/ranking/developers", headers=fresh_dev_headers)
    assert response.status_code == 200

    rankings = response.json()["rankings"]
    dev_entry = next((e for e in rankings if e["user_id"] == dev_id), None)
    assert dev_entry is not None, f"Developer {dev_id} not found in ranking"
    assert dev_entry["in_progress_count"] == 2, (
        f"Expected in_progress_count=2, got {dev_entry['in_progress_count']}"
    )


@pytest.mark.asyncio
async def test_ranking_only_includes_developers(client: AsyncClient):
    """The ranking only contains users with role='developer'; users and admins are excluded."""
    user_headers = await register_and_login(client, role="user")
    admin_headers = await register_and_login(client, role="admin")
    dev_headers = await register_and_login(client, role="developer")

    # Get user and admin IDs
    user_email = f"notinranking_user_{uuid.uuid4().hex[:8]}@example.com"
    admin_email = f"notinranking_admin_{uuid.uuid4().hex[:8]}@example.com"

    user_resp = await client.post(
        "/api/auth/register",
        json={"name": "Not In Ranking", "email": user_email, "password": "SecurePass123!", "role": "user"},
    )
    admin_resp = await client.post(
        "/api/auth/register",
        json={"name": "Not In Ranking Admin", "email": admin_email, "password": "SecurePass123!", "role": "admin"},
    )
    user_id = user_resp.json()["user"]["id"]
    admin_id = admin_resp.json()["user"]["id"]

    response = await client.get("/api/ranking/developers", headers=dev_headers)
    assert response.status_code == 200

    rankings = response.json()["rankings"]
    ids_in_ranking = {e["user_id"] for e in rankings}

    assert user_id not in ids_in_ranking, "Regular user should not appear in developer ranking"
    assert admin_id not in ids_in_ranking, "Admin should not appear in developer ranking"
