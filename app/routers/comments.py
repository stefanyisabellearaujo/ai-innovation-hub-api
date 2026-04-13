import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.middleware.auth import get_current_user, require_role
from app.models.comment import Comment
from app.models.idea import Idea
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentResponse

router = APIRouter(prefix="/api/ideas", tags=["Comments"])


@router.post(
    "/{idea_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment to an idea",
)
async def add_comment(
    idea_id: uuid.UUID,
    body: CommentCreate,
    current_user: User = Depends(require_role("user", "developer")),
    db: AsyncSession = Depends(get_db),
) -> CommentResponse:
    """Add a comment to an idea (user and developer only)."""
    # 404 if idea not found
    result = await db.execute(select(Idea).where(Idea.id == idea_id))
    idea = result.scalar_one_or_none()
    if idea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")

    new_comment = Comment(
        content=body.content,
        user_id=current_user.id,
        idea_id=idea_id,
    )
    db.add(new_comment)
    await db.flush()
    await db.refresh(new_comment)

    return CommentResponse(
        id=new_comment.id,
        content=new_comment.content,
        user_id=new_comment.user_id,
        idea_id=new_comment.idea_id,
        created_at=new_comment.created_at,
        user_name=current_user.name,
    )


@router.get(
    "/{idea_id}/comments",
    status_code=status.HTTP_200_OK,
    summary="List comments for an idea",
)
async def list_comments(
    idea_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List comments for an idea, paginated and ordered by creation date (ascending)."""
    # 404 if idea not found
    result = await db.execute(select(Idea).where(Idea.id == idea_id))
    idea = result.scalar_one_or_none()
    if idea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")

    # Count total
    count_result = await db.execute(
        select(func.count()).where(Comment.idea_id == idea_id)
    )
    total = count_result.scalar_one()

    # Fetch paginated comments ordered ASC
    offset = (page - 1) * per_page
    comments_result = await db.execute(
        select(Comment)
        .where(Comment.idea_id == idea_id)
        .options(selectinload(Comment.user))  # single JOIN, no N+1
        .order_by(Comment.created_at.asc())
        .offset(offset)
        .limit(per_page)
    )
    comments = comments_result.scalars().all()

    items = [
        CommentResponse(
            id=c.id,
            content=c.content,
            user_id=c.user_id,
            idea_id=c.idea_id,
            created_at=c.created_at,
            user_name=c.user.name if c.user else None,
        )
        for c in comments
    ]

    pages = math.ceil(total / per_page) if per_page > 0 else 0

    return {
        "items": [item.model_dump() for item in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }
