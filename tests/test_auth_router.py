"""Integration tests for /api/auth endpoints."""
import pytest
import pytest_asyncio
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


async def test_register_new_user(client: AsyncClient):
    resp = await client.post("/api/auth/register", json={
        "name": "Alice Dev",
        "email": "alice@onfly.com",
        "password": "password123",
        "role": "developer",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "alice@onfly.com"
    assert data["user"]["role"] == "developer"


async def test_register_duplicate_email(client: AsyncClient):
    payload = {"name": "Bob", "email": "bob@onfly.com", "password": "password123", "role": "user"}
    await client.post("/api/auth/register", json=payload)
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 409


async def test_login_valid(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "name": "Carol", "email": "carol@onfly.com", "password": "password123", "role": "user"
    })
    resp = await client.post("/api/auth/login", json={
        "email": "carol@onfly.com", "password": "password123"
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/auth/register", json={
        "name": "Dave", "email": "dave@onfly.com", "password": "rightpass", "role": "user"
    })
    resp = await client.post("/api/auth/login", json={
        "email": "dave@onfly.com", "password": "wrongpass"
    })
    assert resp.status_code == 401


async def test_get_me_authenticated(client: AsyncClient):
    reg = await client.post("/api/auth/register", json={
        "name": "Eve", "email": "eve@onfly.com", "password": "password123", "role": "admin"
    })
    token = reg.json()["access_token"]
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "eve@onfly.com"


async def test_get_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
