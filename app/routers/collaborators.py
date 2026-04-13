import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, require_role
from app.models.collaborator import Collaborator
from app.models.idea import Idea
from app.models.user import User
from app.schemas.collaborator import CollaboratorResponse

MAX_COLLABORATORS = 3

router = APIRouter(prefix="/api/ideas", tags=["Collaborators"])


@router.post(
    "/{idea_id}/collaborators",
    response_model=CollaboratorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Join an idea as a collaborator",
)
async def join_idea(
    idea_id: uuid.UUID,
    current_user: User = Depends(require_role("developer")),
    db: AsyncSession = Depends(get_db),
) -> CollaboratorResponse:
    """Join an idea as a collaborator (developer only, max 3 collaborators)."""
    # 404 if idea not found
    result = await db.execute(select(Idea).where(Idea.id == idea_id))
    idea = result.scalar_one_or_none()
    if idea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")

    # 409 if already a collaborator
    existing_result = await db.execute(
        select(Collaborator).where(
            Collaborator.user_id == current_user.id,
            Collaborator.idea_id == idea_id,
        )
    )
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already a collaborator on this idea",
        )

    # 409 if collaborator limit reached
    count_result = await db.execute(
        select(func.count()).where(Collaborator.idea_id == idea_id)
    )
    collab_count = count_result.scalar_one()
    if collab_count >= MAX_COLLABORATORS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Limite de desenvolvedores atingido",
        )

    # Insert new collaborator
    new_collaborator = Collaborator(
        user_id=current_user.id,
        idea_id=idea_id,
        role="contributor",
    )
    db.add(new_collaborator)
    await db.flush()
    await db.refresh(new_collaborator)

    return CollaboratorResponse(
        id=new_collaborator.id,
        user_id=new_collaborator.user_id,
        idea_id=new_collaborator.idea_id,
        role=new_collaborator.role,
        joined_at=new_collaborator.joined_at,
        user_name=current_user.name,
    )


@router.get(
    "/{idea_id}/collaborators",
    response_model=list[CollaboratorResponse],
    status_code=status.HTTP_200_OK,
    summary="List collaborators for an idea",
)
async def list_collaborators(
    idea_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CollaboratorResponse]:
    """List all collaborators for an idea. All authenticated roles may access this."""
    result = await db.execute(select(Idea).where(Idea.id == idea_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")

    collab_result = await db.execute(
        select(Collaborator, User)
        .join(User, Collaborator.user_id == User.id)
        .where(Collaborator.idea_id == idea_id)
        .order_by(Collaborator.joined_at.asc())
    )
    rows = collab_result.all()
    return [
        CollaboratorResponse(
            id=c.id,
            user_id=c.user_id,
            idea_id=c.idea_id,
            role=c.role,
            joined_at=c.joined_at,
            user_name=u.name,
        )
        for c, u in rows
    ]


@router.delete(
    "/{idea_id}/collaborators",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Leave an idea as a collaborator",
)
async def leave_idea(
    idea_id: uuid.UUID,
    current_user: User = Depends(require_role("developer")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Leave an idea as a collaborator (developer only)."""
    # 404 if idea not found
    result = await db.execute(select(Idea).where(Idea.id == idea_id))
    idea = result.scalar_one_or_none()
    if idea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")

    # 404 if not a collaborator
    collab_result = await db.execute(
        select(Collaborator).where(
            Collaborator.user_id == current_user.id,
            Collaborator.idea_id == idea_id,
        )
    )
    collaborator = collab_result.scalar_one_or_none()
    if collaborator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not a collaborator on this idea",
        )

    await db.delete(collaborator)
    await db.flush()
