"""Unit tests for IdeaService."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaborator import Collaborator
from app.models.idea import Idea
from app.models.user import User
from app.schemas.idea import IdeaCreate, IdeaUpdate
from app.services.idea_service import IdeaService, VALID_STATUS_TRANSITIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(role: str = "user") -> User:
    return User(
        id=uuid.uuid4(),
        name="Test User",
        email=f"{uuid.uuid4()}@test.com",
        password_hash="hashed",
        role=role,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def service(db_session: AsyncSession) -> IdeaService:
    return IdeaService(db_session)


@pytest.fixture
async def author(db_session: AsyncSession) -> User:
    user = make_user(role="user")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def developer(db_session: AsyncSession) -> User:
    user = make_user(role="developer")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def admin(db_session: AsyncSession) -> User:
    user = make_user(role="admin")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def other_user(db_session: AsyncSession) -> User:
    user = make_user(role="user")
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def idea(db_session: AsyncSession, author: User) -> Idea:
    obj = Idea(
        id=uuid.uuid4(),
        title="Test Idea",
        description="A detailed description",
        category="technology",
        status="idea",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()
    return obj


# ---------------------------------------------------------------------------
# VALID_STATUS_TRANSITIONS sanity check
# ---------------------------------------------------------------------------

def test_valid_status_transitions_completeness():
    """Every status must appear as a key in VALID_STATUS_TRANSITIONS."""
    all_statuses = {"idea", "evaluation", "development", "completed", "archived"}
    assert set(VALID_STATUS_TRANSITIONS.keys()) == all_statuses


def test_completed_and_archived_have_no_transitions():
    assert VALID_STATUS_TRANSITIONS["completed"] == []
    assert VALID_STATUS_TRANSITIONS["archived"] == []


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------

async def test_get_by_id_returns_idea(service: IdeaService, idea: Idea):
    result = await service.get_by_id(idea.id)
    assert result.id == idea.id
    assert result.title == idea.title


async def test_get_by_id_raises_404_when_not_found(service: IdeaService):
    with pytest.raises(HTTPException) as exc:
        await service.get_by_id(uuid.uuid4())
    assert exc.value.status_code == 404
    assert "not found" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

async def test_create_assigns_ai_category(service: IdeaService, author: User):
    data = IdeaCreate(title="New Idea", description="Detailed description")
    with patch("app.services.ai_service.categorize_idea", new=AsyncMock(return_value={"category": "automation"})):
        result = await service.create(data, author)

    assert result.title == "New Idea"
    assert result.category == "automation"
    assert result.author_id == author.id


async def test_create_sets_default_priority(service: IdeaService, author: User):
    data = IdeaCreate(title="Priority Test", description="Some description")
    with patch("app.services.ai_service.categorize_idea", new=AsyncMock(return_value={"category": "data"})):
        result = await service.create(data, author)

    assert result.priority == "medium"


async def test_create_sets_default_status(service: IdeaService, author: User):
    data = IdeaCreate(title="Status Test", description="Some description")
    with patch("app.services.ai_service.categorize_idea", new=AsyncMock(return_value={"category": "data"})):
        result = await service.create(data, author)

    assert result.status == "idea"


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

async def test_list_returns_all_ideas(service: IdeaService, idea: Idea, author: User):
    response = await service.list(
        page=1, per_page=10, sort_by="created_at", order="desc",
        status=None, category=None, search=None, author_id=None,
        current_user=author,
    )
    assert response.total >= 1
    ids = [i.id for i in response.items]
    assert idea.id in ids


async def test_list_hides_others_archived_from_regular_user(
    service: IdeaService, db_session: AsyncSession, author: User, other_user: User
):
    archived = Idea(
        id=uuid.uuid4(),
        title="Archived Idea",
        description="desc",
        status="archived",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(archived)
    await db_session.flush()

    response = await service.list(
        page=1, per_page=20, sort_by="created_at", order="desc",
        status=None, category=None, search=None, author_id=None,
        current_user=other_user,
    )
    ids = [i.id for i in response.items]
    assert archived.id not in ids


async def test_list_shows_own_archived_to_regular_user(
    service: IdeaService, db_session: AsyncSession, author: User
):
    archived = Idea(
        id=uuid.uuid4(),
        title="My Archived Idea",
        description="desc",
        status="archived",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(archived)
    await db_session.flush()

    response = await service.list(
        page=1, per_page=20, sort_by="created_at", order="desc",
        status=None, category=None, search=None, author_id=None,
        current_user=author,
    )
    ids = [i.id for i in response.items]
    assert archived.id in ids


async def test_list_shows_archived_to_admin(
    service: IdeaService, db_session: AsyncSession, author: User, admin: User
):
    archived = Idea(
        id=uuid.uuid4(),
        title="Admin Sees Archived",
        description="desc",
        status="archived",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(archived)
    await db_session.flush()

    response = await service.list(
        page=1, per_page=20, sort_by="created_at", order="desc",
        status=None, category=None, search=None, author_id=None,
        current_user=admin,
    )
    ids = [i.id for i in response.items]
    assert archived.id in ids


async def test_list_pagination(
    service: IdeaService, db_session: AsyncSession, author: User
):
    for i in range(5):
        db_session.add(Idea(
            id=uuid.uuid4(),
            title=f"Pagination Idea {i}",
            description="desc",
            status="idea",
            priority="medium",
            author_id=author.id,
            votes_count=0,
        ))
    await db_session.flush()

    response = await service.list(
        page=1, per_page=2, sort_by="created_at", order="desc",
        status=None, category=None, search=None, author_id=None,
    )
    assert len(response.items) == 2
    assert response.per_page == 2


# ---------------------------------------------------------------------------
# update — archived idea
# ---------------------------------------------------------------------------

async def test_update_archived_idea_raises_422(
    service: IdeaService, db_session: AsyncSession, author: User
):
    archived = Idea(
        id=uuid.uuid4(),
        title="Archived",
        description="desc",
        status="archived",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(archived)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await service.update(archived.id, IdeaUpdate(title="New title"), author)
    assert exc.value.status_code == 422
    assert "archived" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# update — completed idea
# ---------------------------------------------------------------------------

async def test_update_completed_idea_content_raises_422(
    service: IdeaService, db_session: AsyncSession, author: User
):
    completed = Idea(
        id=uuid.uuid4(),
        title="Done",
        description="desc",
        status="completed",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(completed)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await service.update(completed.id, IdeaUpdate(title="Changed"), author)
    assert exc.value.status_code == 422
    assert "completed" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# update — archive permission
# ---------------------------------------------------------------------------

async def test_non_admin_cannot_archive(
    service: IdeaService, db_session: AsyncSession, author: User, other_user: User
):
    obj = Idea(
        id=uuid.uuid4(),
        title="Idea",
        description="desc",
        status="idea",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await service.update(obj.id, IdeaUpdate(status="archived"), other_user)
    assert exc.value.status_code == 403


async def test_admin_can_archive_any_idea(
    service: IdeaService, db_session: AsyncSession, author: User, admin: User
):
    obj = Idea(
        id=uuid.uuid4(),
        title="Idea to Archive",
        description="desc",
        status="development",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()

    result = await service.update(obj.id, IdeaUpdate(status="archived"), admin)
    assert result.status == "archived"


# ---------------------------------------------------------------------------
# update — status change permission
# ---------------------------------------------------------------------------

async def test_non_collaborator_cannot_change_status(
    service: IdeaService, db_session: AsyncSession, author: User, other_user: User
):
    obj = Idea(
        id=uuid.uuid4(),
        title="Idea",
        description="desc",
        status="idea",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await service.update(obj.id, IdeaUpdate(status="evaluation"), other_user)
    assert exc.value.status_code == 403


async def test_collaborator_can_change_status(
    service: IdeaService, db_session: AsyncSession, author: User, developer: User
):
    obj = Idea(
        id=uuid.uuid4(),
        title="Collab Idea",
        description="desc",
        status="idea",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()

    collab = Collaborator(
        id=uuid.uuid4(),
        idea_id=obj.id,
        user_id=developer.id,
        role="contributor",
    )
    db_session.add(collab)
    await db_session.flush()

    result = await service.update(obj.id, IdeaUpdate(status="evaluation"), developer)
    assert result.status == "evaluation"


# ---------------------------------------------------------------------------
# update — content edit permission
# ---------------------------------------------------------------------------

async def test_non_author_cannot_edit_content(
    service: IdeaService, db_session: AsyncSession, author: User, developer: User
):
    obj = Idea(
        id=uuid.uuid4(),
        title="Original",
        description="desc",
        status="idea",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()

    collab = Collaborator(
        id=uuid.uuid4(),
        idea_id=obj.id,
        user_id=developer.id,
        role="contributor",
    )
    db_session.add(collab)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await service.update(obj.id, IdeaUpdate(title="Changed by collab"), developer)
    assert exc.value.status_code == 403
    assert "author" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# update — status transitions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("from_status,to_status", [
    ("idea", "evaluation"),
    ("evaluation", "development"),
    ("evaluation", "idea"),
    ("development", "completed"),
    ("development", "evaluation"),
])
async def test_valid_status_transitions(
    service: IdeaService, db_session: AsyncSession, author: User, developer: User,
    from_status: str, to_status: str,
):
    obj = Idea(
        id=uuid.uuid4(),
        title="Transition Idea",
        description="desc",
        status=from_status,
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()

    collab = Collaborator(
        id=uuid.uuid4(),
        idea_id=obj.id,
        user_id=developer.id,
        role="contributor",
    )
    db_session.add(collab)
    await db_session.flush()

    result = await service.update(obj.id, IdeaUpdate(status=to_status), developer)
    assert result.status == to_status


@pytest.mark.parametrize("from_status,to_status", [
    ("idea", "completed"),
    ("idea", "development"),
    ("development", "idea"),
    ("evaluation", "completed"),
])
async def test_invalid_status_transitions_raise_422(
    service: IdeaService, db_session: AsyncSession, author: User, developer: User,
    from_status: str, to_status: str,
):
    obj = Idea(
        id=uuid.uuid4(),
        title="Bad Transition",
        description="desc",
        status=from_status,
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()

    collab = Collaborator(
        id=uuid.uuid4(),
        idea_id=obj.id,
        user_id=developer.id,
        role="contributor",
    )
    db_session.add(collab)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await service.update(obj.id, IdeaUpdate(status=to_status), developer)
    assert exc.value.status_code == 422
    assert "transition" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# update — AI re-categorization
# ---------------------------------------------------------------------------

async def test_update_recategorizes_on_description_change(
    service: IdeaService, db_session: AsyncSession, author: User
):
    obj = Idea(
        id=uuid.uuid4(),
        title="Idea",
        description="Original description",
        category="technology",
        status="idea",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()

    with patch("app.services.ai_service.categorize_idea", new=AsyncMock(return_value={"category": "sustainability"})):
        result = await service.update(
            obj.id, IdeaUpdate(description="New description about sustainability"), author
        )

    assert result.category == "sustainability"


async def test_update_recategorizes_on_title_change(
    service: IdeaService, db_session: AsyncSession, author: User
):
    obj = Idea(
        id=uuid.uuid4(),
        title="Old Title",
        description="desc",
        category="technology",
        status="idea",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()

    with patch("app.services.ai_service.categorize_idea", new=AsyncMock(return_value={"category": "productivity"})):
        result = await service.update(
            obj.id, IdeaUpdate(title="New Title About Productivity"), author
        )

    assert result.category == "productivity"


async def test_update_status_only_does_not_recategorize(
    service: IdeaService, db_session: AsyncSession, author: User, developer: User
):
    obj = Idea(
        id=uuid.uuid4(),
        title="Idea",
        description="desc",
        category="technology",
        status="idea",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()

    collab = Collaborator(
        id=uuid.uuid4(),
        idea_id=obj.id,
        user_id=developer.id,
        role="contributor",
    )
    db_session.add(collab)
    await db_session.flush()

    with patch("app.services.ai_service.categorize_idea", new=AsyncMock()) as mock_ai:
        await service.update(obj.id, IdeaUpdate(status="evaluation"), developer)
        mock_ai.assert_not_called()


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

async def test_author_can_delete_idea(
    service: IdeaService, db_session: AsyncSession, author: User
):
    obj = Idea(
        id=uuid.uuid4(),
        title="To Delete",
        description="desc",
        status="idea",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()

    await service.delete(obj.id, author)

    with pytest.raises(HTTPException) as exc:
        await service.get_by_id(obj.id)
    assert exc.value.status_code == 404


async def test_non_author_cannot_delete(
    service: IdeaService, db_session: AsyncSession, author: User, other_user: User
):
    obj = Idea(
        id=uuid.uuid4(),
        title="Protected",
        description="desc",
        status="idea",
        priority="medium",
        author_id=author.id,
        votes_count=0,
    )
    db_session.add(obj)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await service.delete(obj.id, other_user)
    assert exc.value.status_code == 403
    assert "author" in exc.value.detail.lower()


async def test_delete_nonexistent_idea_raises_404(
    service: IdeaService, author: User
):
    with pytest.raises(HTTPException) as exc:
        await service.delete(uuid.uuid4(), author)
    assert exc.value.status_code == 404
