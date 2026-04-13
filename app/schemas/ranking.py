import uuid

from pydantic import BaseModel, ConfigDict


class RankingEntry(BaseModel):
    """A single developer entry in the leaderboard."""

    model_config = ConfigDict(from_attributes=True)

    rank: int
    user_id: uuid.UUID
    name: str
    avatar_url: str | None = None
    completed_count: int
    in_progress_count: int


class RankingResponse(BaseModel):
    """Response containing the full developer ranking list."""

    rankings: list[RankingEntry]
