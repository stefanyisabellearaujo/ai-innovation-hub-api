"""
Integration tests for the Comments API (M3).

Tests exercise POST /api/ideas/{idea_id}/comments (add)
and GET /api/ideas/{idea_id}/comments (list, paginated).
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
    email = f"comment_user_{_user_counter}_{uuid.uuid4().hex[:6]}@example.com"

    payload = {
        "name": f"Comment User {_user_counter}",
        "email": email,
        "password": "SecurePass123!",
        "role": role,
    }
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text

    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_test_idea(client: AsyncClient, headers: dict, title: str = "Comment Test Idea") -> dict:
    """Helper to create an idea and return the response JSON."""
    response = await client.post(
        "/api/ideas",
        json={"title": title, "description": "A detailed description for comment tests"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Add comment tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_adds_comment_returns_201(client: AsyncClient):
    """A user can add a comment; response includes the content."""
    user_headers = await register_and_login(client, role="user")
    idea = await create_test_idea(client, user_headers)

    response = await client.post(
        f"/api/ideas/{idea['id']}/comments",
        json={"content": "This is a great idea!"},
        headers=user_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["content"] == "This is a great idea!"
    assert data["idea_id"] == idea["id"]
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_developer_adds_comment_returns_201(client: AsyncClient):
    """A developer can also add a comment."""
    user_headers = await register_and_login(client, role="user")
    dev_headers = await register_and_login(client, role="developer")
    idea = await create_test_idea(client, user_headers)

    response = await client.post(
        f"/api/ideas/{idea['id']}/comments",
        json={"content": "Developer perspective: this is implementable."},
        headers=dev_headers,
    )
    assert response.status_code == 201
    assert response.json()["content"] == "Developer perspective: this is implementable."


@pytest.mark.asyncio
async def test_admin_cannot_add_comment_returns_403(client: AsyncClient):
    """An admin is not allowed to add comments; expects 403."""
    user_headers = await register_and_login(client, role="user")
    admin_headers = await register_and_login(client, role="admin")
    idea = await create_test_idea(client, user_headers)

    response = await client.post(
        f"/api/ideas/{idea['id']}/comments",
        json={"content": "Admin comment attempt"},
        headers=admin_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_whitespace_only_comment_returns_422(client: AsyncClient):
    """A comment with only whitespace is rejected with 422."""
    user_headers = await register_and_login(client, role="user")
    idea = await create_test_idea(client, user_headers)

    response = await client.post(
        f"/api/ideas/{idea['id']}/comments",
        json={"content": "   "},
        headers=user_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_comment_exceeding_max_length_returns_422(client: AsyncClient):
    """A comment longer than 2000 characters is rejected with 422."""
    user_headers = await register_and_login(client, role="user")
    idea = await create_test_idea(client, user_headers)

    long_content = "x" * 2001
    response = await client.post(
        f"/api/ideas/{idea['id']}/comments",
        json={"content": long_content},
        headers=user_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_add_comment_to_non_existent_idea_returns_404(client: AsyncClient):
    """Adding a comment to a non-existent idea returns 404."""
    user_headers = await register_and_login(client, role="user")
    fake_id = str(uuid.uuid4())

    response = await client.post(
        f"/api/ideas/{fake_id}/comments",
        json={"content": "This idea does not exist"},
        headers=user_headers,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# List comments tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_comments_returns_200_with_pagination(client: AsyncClient):
    """GET /api/ideas/{id}/comments returns paginated structure with items, total, etc."""
    user_headers = await register_and_login(client, role="user")
    idea = await create_test_idea(client, user_headers)

    # Add a couple of comments
    await client.post(
        f"/api/ideas/{idea['id']}/comments",
        json={"content": "First comment"},
        headers=user_headers,
    )
    await client.post(
        f"/api/ideas/{idea['id']}/comments",
        json={"content": "Second comment"},
        headers=user_headers,
    )

    response = await client.get(f"/api/ideas/{idea['id']}/comments", headers=user_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "per_page" in data
    assert "pages" in data
    assert data["total"] >= 2
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_comments_are_ordered_asc(client: AsyncClient):
    """Comments are returned in ascending chronological order."""
    user_headers = await register_and_login(client, role="user")
    idea = await create_test_idea(client, user_headers)

    contents = ["Alpha comment", "Beta comment", "Gamma comment"]
    for content in contents:
        await client.post(
            f"/api/ideas/{idea['id']}/comments",
            json={"content": content},
            headers=user_headers,
        )

    response = await client.get(f"/api/ideas/{idea['id']}/comments", headers=user_headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 3
    # Verify ASC order by checking created_at timestamps
    timestamps = [item["created_at"] for item in items[-3:]]
    assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_list_comments_admin_can_read(client: AsyncClient):
    """An admin can list comments (GET is open to all authenticated users)."""
    user_headers = await register_and_login(client, role="user")
    admin_headers = await register_and_login(client, role="admin")
    idea = await create_test_idea(client, user_headers)

    await client.post(
        f"/api/ideas/{idea['id']}/comments",
        json={"content": "Readable by admin"},
        headers=user_headers,
    )

    response = await client.get(f"/api/ideas/{idea['id']}/comments", headers=admin_headers)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_comments_non_existent_idea_returns_404(client: AsyncClient):
    """Listing comments for a non-existent idea returns 404."""
    user_headers = await register_and_login(client, role="user")
    fake_id = str(uuid.uuid4())

    response = await client.get(f"/api/ideas/{fake_id}/comments", headers=user_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_comment_content_is_stripped(client: AsyncClient):
    """Leading/trailing whitespace in comment content is stripped."""
    user_headers = await register_and_login(client, role="user")
    idea = await create_test_idea(client, user_headers)

    response = await client.post(
        f"/api/ideas/{idea['id']}/comments",
        json={"content": "  trimmed content  "},
        headers=user_headers,
    )
    assert response.status_code == 201
    assert response.json()["content"] == "trimmed content"


@pytest.mark.asyncio
async def test_list_comments_pagination(client: AsyncClient):
    """Pagination parameters work correctly for comments."""
    user_headers = await register_and_login(client, role="user")
    idea = await create_test_idea(client, user_headers)

    # Add 5 comments
    for i in range(5):
        await client.post(
            f"/api/ideas/{idea['id']}/comments",
            json={"content": f"Paginated comment {i + 1}"},
            headers=user_headers,
        )

    # Request page 1 with 2 per page
    response = await client.get(
        f"/api/ideas/{idea['id']}/comments?page=1&per_page=2",
        headers=user_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["per_page"] == 2
    assert data["page"] == 1
    assert data["total"] >= 5
