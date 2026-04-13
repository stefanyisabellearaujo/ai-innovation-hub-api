import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_role
from app.models.collaborator import Collaborator
from app.models.idea import Idea
from app.models.user import User
from app.schemas.admin import AdminStats
from app.schemas.user import RoleUpdate, UserResponse
from app.services.auth_service import get_all_users, update_user_role

router = APIRouter(prefix="/api/admin", tags=["Admin"])

_admin_only = Depends(require_role("admin"))


@router.get(
    "/users",
    response_model=list[UserResponse],
    summary="List all users",
    description="Returns all registered users. Admin access only.",
    dependencies=[_admin_only],
)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserResponse]:
    users = await get_all_users(db)
    return [UserResponse.model_validate(u) for u in users]


@router.get(
    "/stats",
    response_model=AdminStats,
    summary="Get platform statistics",
    description="Returns aggregated platform metrics. Admin access only.",
    dependencies=[Depends(require_role("admin"))],
)
async def get_stats(db: Annotated[AsyncSession, Depends(get_db)]) -> AdminStats:
    """
    Aggregated platform statistics for the admin dashboard:
    - Total idea count
    - Count per status
    - Count per category
    - Number of distinct active collaborators
    """
    # Total ideas
    total_result = await db.execute(select(func.count()).select_from(Idea))
    total_ideas = total_result.scalar_one()

    # Ideas by status
    status_result = await db.execute(
        select(Idea.status, func.count().label("cnt")).group_by(Idea.status)
    )
    ideas_by_status = {row.status: row.cnt for row in status_result.all()}

    # Ideas by category
    category_result = await db.execute(
        select(Idea.category, func.count().label("cnt"))
        .where(Idea.category.is_not(None))
        .group_by(Idea.category)
    )
    ideas_by_category = {row.category: row.cnt for row in category_result.all() if row.category}

    # Active collaborators (distinct users with at least one collaboration)
    collab_result = await db.execute(
        select(func.count(distinct(Collaborator.user_id)))
    )
    active_collaborators = collab_result.scalar_one()

    return AdminStats(
        total_ideas=total_ideas,
        ideas_by_status=ideas_by_status,
        ideas_by_category=ideas_by_category,
        active_collaborators=active_collaborators,
    )


@router.put(
    "/users/{user_id}/role",
    response_model=UserResponse,
    summary="Update a user's role",
    description=(
        "Change the role of any user (user, developer, admin). "
        "Cannot remove the last admin. Admin access only."
    ),
    dependencies=[_admin_only],
)
async def update_role(
    user_id: uuid.UUID,
    data: RoleUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    user = await update_user_role(db, user_id, data.role.value)
    return UserResponse.model_validate(user)
