import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_role
from app.models.idea import Idea
from app.models.user import User
from app.models.vote import Vote
from app.schemas.vote import VoteResponse

router = APIRouter(prefix="/api/ideas", tags=["Votes"])


@router.post(
    "/{idea_id}/vote",
    response_model=VoteResponse,
    status_code=status.HTTP_200_OK,
    summary="Toggle vote on an idea",
)
async def toggle_vote(
    idea_id: uuid.UUID,
    current_user: User = Depends(require_role("user", "developer")),
    db: AsyncSession = Depends(get_db),
) -> VoteResponse:
    """Toggle vote on an idea. Returns voted status and updated vote count."""
    # 1. Verify idea exists
    result = await db.execute(select(Idea).where(Idea.id == idea_id))
    idea = result.scalar_one_or_none()
    if idea is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Idea not found")

    if idea.author_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot vote on your own idea",
        )

    if idea.status in ("completed", "archived"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Voting is not allowed on completed or archived ideas",
        )

    # 2. Check if vote already exists for this (user_id, idea_id)
    vote_result = await db.execute(
        select(Vote).where(Vote.user_id == current_user.id, Vote.idea_id == idea_id)
    )
    existing_vote = vote_result.scalar_one_or_none()

    if existing_vote is not None:
        # 3. Vote exists: delete it and decrement count
        await db.delete(existing_vote)
        idea.votes_count = max(0, idea.votes_count - 1)
        voted = False
    else:
        # 4. Vote does not exist: insert it and increment count
        new_vote = Vote(user_id=current_user.id, idea_id=idea_id)
        db.add(new_vote)
        idea.votes_count = idea.votes_count + 1
        voted = True

    await db.flush()
    return VoteResponse(voted=voted, votes_count=idea.votes_count)
