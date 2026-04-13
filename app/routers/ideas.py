import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_role
from app.models.user import User
from app.schemas.idea import IdeaCreate, IdeaListResponse, IdeaResponse, IdeaUpdate
from app.services.idea_service import IdeaService

router = APIRouter(prefix="/api/ideas", tags=["Ideas"])


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def get_idea_service(db: Annotated[AsyncSession, Depends(get_db)]) -> IdeaService:
    """FastAPI dependency that provides an IdeaService instance."""
    return IdeaService(db)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=IdeaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new idea",
)
async def create_idea(
    data: IdeaCreate,
    current_user: Annotated[User, Depends(require_role("user", "developer"))],
    service: Annotated[IdeaService, Depends(get_idea_service)],
) -> IdeaResponse:
    """
    Submit a new AI innovation idea.

    Only users with the **user** or **developer** role may create ideas.
    Admins are not allowed to submit ideas.

    The idea is automatically categorised via the AI service (falls back to
    *"Other"* if the service is unavailable).
    """
    idea = await service.create(data, current_user)
    return IdeaResponse.model_validate(idea)


@router.get(
    "",
    response_model=IdeaListResponse,
    status_code=status.HTTP_200_OK,
    summary="List ideas",
)
async def list_ideas(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[IdeaService, Depends(get_idea_service)],
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    per_page: int = Query(default=20, ge=1, le=100, description="Items per page (max 100)"),
    sort_by: str = Query(default="created_at", description="Sort field: created_at, votes_count, title"),
    order: str = Query(default="desc", description="Sort order: asc or desc"),
    status: str | None = Query(default=None, description="Filter by status"),
    category: str | None = Query(default=None, description="Filter by category"),
    search: str | None = Query(default=None, description="Search in title and description"),
    author_id: uuid.UUID | None = Query(default=None, description="Filter by author UUID"),
    collaborator_id: uuid.UUID | None = Query(default=None, description="Filter by collaborator UUID"),
) -> IdeaListResponse:
    """
    Return a paginated list of ideas.

    All authenticated roles may access this endpoint.
    Supports filtering by status, category, author, collaborator, and a
    full-text search on title and description.
    """
    return await service.list(
        page=page,
        per_page=per_page,
        sort_by=sort_by,
        order=order,
        status=status,
        category=category,
        search=search,
        author_id=author_id,
        collaborator_id=collaborator_id,
        current_user=current_user,
    )


@router.get(
    "/{idea_id}",
    response_model=IdeaResponse,
    status_code=status.HTTP_200_OK,
    summary="Get idea by ID",
)
async def get_idea(
    idea_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[IdeaService, Depends(get_idea_service)],
) -> IdeaResponse:
    """
    Retrieve a single idea by its UUID.

    All authenticated roles may access this endpoint.
    Returns 404 if the idea does not exist.
    """
    idea = await service.get_by_id(idea_id)
    return IdeaResponse.model_validate(idea)


@router.put(
    "/{idea_id}",
    response_model=IdeaResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an idea",
)
async def update_idea(
    idea_id: uuid.UUID,
    data: IdeaUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[IdeaService, Depends(get_idea_service)],
) -> IdeaResponse:
    """
    Partially update an idea.

    - **Author**: may update title, description, status, and priority.
    - **Developer collaborator**: may only update the status field.
    - Status transitions must follow the allowed workflow.
    - Archived ideas cannot be modified.
    """
    idea = await service.update(idea_id, data, current_user)
    return IdeaResponse.model_validate(idea)


@router.delete(
    "/{idea_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an idea",
)
async def delete_idea(
    idea_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[IdeaService, Depends(get_idea_service)],
) -> None:
    """
    Permanently delete an idea.

    Only the idea's **author** may delete it.
    Returns 403 if the current user is not the author, 404 if not found.
    """
    await service.delete(idea_id, current_user)
