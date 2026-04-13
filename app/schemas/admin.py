from pydantic import BaseModel


class AdminStats(BaseModel):
    """Aggregated platform statistics for the admin dashboard."""

    total_ideas: int
    ideas_by_status: dict[str, int]    # status -> count
    ideas_by_category: dict[str, int]  # category -> count
    active_collaborators: int          # distinct users with at least 1 collaboration
