from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_role
from app.models.collaborator import Collaborator
from app.models.idea import Idea
from app.models.user import User
from app.schemas.ranking import RankingEntry, RankingResponse

router = APIRouter(prefix="/api/ranking", tags=["Ranking"])


@router.get(
    "/developers",
    response_model=RankingResponse,
    summary="Developer leaderboard",
    description=(
        "Returns all developers ranked by the number of completed idea collaborations. "
        "Ties are broken by in-progress (development) collaboration count. "
        "Developers with zero collaborations still appear in the list. "
        "Requires developer role."
    ),
)
async def get_developer_ranking(
    current_user: User = Depends(require_role("developer", "admin")),
    db: AsyncSession = Depends(get_db),
) -> RankingResponse:
    """
    Returns developers ranked by number of completed idea collaborations.
    Only accessible by users with the developer role.

    Primary sort: completed_count DESC
    Secondary sort: in_progress_count DESC
    """
    stmt = (
        select(
            User.id,
            User.name,
            User.avatar_url,
            func.count(
                case((Idea.status == "completed", 1), else_=None)
            ).label("completed_count"),
            func.count(
                case((Idea.status == "development", 1), else_=None)
            ).label("in_progress_count"),
        )
        .where(User.role == "developer")
        .outerjoin(Collaborator, Collaborator.user_id == User.id)
        .outerjoin(Idea, Idea.id == Collaborator.idea_id)
        .group_by(User.id, User.name, User.avatar_url)
        .order_by(
            func.count(case((Idea.status == "completed", 1), else_=None)).desc(),
            func.count(case((Idea.status == "development", 1), else_=None)).desc(),
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    rankings: list[RankingEntry] = []
    for rank, row in enumerate(rows, start=1):
        rankings.append(
            RankingEntry(
                rank=rank,
                user_id=row.id,
                name=row.name,
                avatar_url=row.avatar_url,
                completed_count=row.completed_count,
                in_progress_count=row.in_progress_count,
            )
        )

    return RankingResponse(rankings=rankings)
