import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.collaborator import Collaborator
from app.models.idea import Idea
from app.models.user import User
from app.schemas.idea import IdeaCreate, IdeaListResponse, IdeaResponse, IdeaUpdate
from app.utils.filters import apply_idea_filters
from app.utils.pagination import calculate_offset, calculate_pagination

# Allowed status transitions: current_status -> [allowed_next_statuses]
VALID_STATUS_TRANSITIONS: dict[str, list[str]] = {
    "idea": ["evaluation"],
    "evaluation": ["development", "idea"],
    "development": ["completed", "evaluation"],
    "completed": [],
    "archived": [],
}

SORT_COLUMN_MAP = {
    "created_at": Idea.created_at,
    "votes_count": Idea.votes_count,
    "title": Idea.title,
}


class IdeaService:
    """Service layer for Ideas CRUD operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(self, data: IdeaCreate, current_user: User) -> Idea:
        """Create a new idea and auto-assign a category via AI."""
        from app.services import ai_service
        ai_result = await ai_service.categorize_idea(data.description)
        category = ai_result["category"]

        idea = Idea(
            title=data.title,
            description=data.description,
            priority="medium",  # fixed default, not user-settable
            category=category,
            author_id=current_user.id,
        )
        self.db.add(idea)
        await self.db.flush()
        await self.db.refresh(idea)

        # Re-fetch with author eagerly loaded
        return await self.get_by_id(idea.id)

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list(
        self,
        page: int,
        per_page: int,
        sort_by: str,
        order: str,
        status: str | None,
        category: str | None,
        search: str | None,
        author_id: uuid.UUID | None,
        collaborator_id: uuid.UUID | None = None,
        current_user: User | None = None,
    ) -> IdeaListResponse:
        """Return a paginated, filtered, and sorted list of ideas."""
        from sqlalchemy import or_

        base_query = select(Idea)
        base_query = apply_idea_filters(
            base_query,
            status=status,
            category=category,
            search=search,
            author_id=author_id,
            collaborator_id=collaborator_id,
        )

        # Users (role="user") cannot see archived ideas from other people
        if current_user and current_user.role == "user":
            base_query = base_query.where(
                or_(Idea.status != "archived", Idea.author_id == current_user.id)
            )

        # Count total matching rows
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        # Sorting
        sort_col = SORT_COLUMN_MAP.get(sort_by, Idea.created_at)
        if order == "asc":
            base_query = base_query.order_by(sort_col.asc())
        else:
            base_query = base_query.order_by(sort_col.desc())

        # Pagination
        offset = calculate_offset(page, per_page)
        base_query = (
            base_query
            .options(selectinload(Idea.author), selectinload(Idea.collaborators).selectinload(Collaborator.user))
            .offset(offset)
            .limit(per_page)
        )

        result = await self.db.execute(base_query)
        ideas = result.scalars().all()

        pagination = calculate_pagination(total, page, per_page)
        return IdeaListResponse(
            items=[IdeaResponse.model_validate(idea) for idea in ideas],
            **pagination,
        )

    # ------------------------------------------------------------------
    # Get by ID
    # ------------------------------------------------------------------

    async def get_by_id(self, idea_id: uuid.UUID) -> Idea:
        """Fetch a single idea by its UUID; raises 404 if not found."""
        query = (
            select(Idea)
            .where(Idea.id == idea_id)
            .options(selectinload(Idea.author), selectinload(Idea.collaborators).selectinload(Collaborator.user))
        )
        result = await self.db.execute(query)
        idea = result.scalar_one_or_none()
        if idea is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Idea not found",
            )
        return idea

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update(
        self,
        idea_id: uuid.UUID,
        data: IdeaUpdate,
        current_user: User,
    ) -> Idea:
        """
        Update an idea.

        Rules:
        - Only the author OR a developer collaborator may update.
        - If the current status is 'archived', updates are rejected (422).
        - A collaborator (non-author) may only change the status field.
        - Status transitions must follow VALID_STATUS_TRANSITIONS.
        - Re-categorises via AI when title or description change.
        """
        idea = await self.get_by_id(idea_id)

        is_author = idea.author_id == current_user.id
        is_collaborator = await self._is_collaborator(idea_id, current_user.id)
        is_admin = current_user.role == "admin"

        # Nobody can edit an archived idea
        if idea.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Archived ideas cannot be modified",
            )

        update_fields_preview = data.model_dump(exclude_none=True)
        non_status_preview = {k for k in update_fields_preview if k not in ("status", "category")}

        # Completed ideas: only status and category can change (no title/description edits)
        if idea.status == "completed" and non_status_preview:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Completed ideas cannot have their content edited. Only status changes and comments are allowed.",
            )

        update_fields = data.model_dump(exclude_none=True)

        # Archive: only admin can archive — responsible parties should delete instead
        if update_fields.get("status") == "archived" and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can archive ideas",
            )

        # Status change: collaborators or admin can change status
        # Exception: author (developer) can set status to "archived" on their own idea
        if "status" in update_fields and not is_collaborator and not is_admin:
            is_own_idea = idea.author_id == current_user.id
            is_archiving_own = (
                update_fields.get("status") == "archived"
                and current_user.role == "developer"
                and is_own_idea
            )
            if not is_archiving_own:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only collaborators or administrators can change idea status",
                )

        # Non-status fields (title, description): only author can edit
        non_status_fields = {k for k in update_fields if k != "status"}
        if non_status_fields and not is_author and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the author can edit idea content",
            )

        # Validate status transition
        # Admin or author-developer can archive from any status; all others follow the transition map
        if data.status is not None and data.status != idea.status:
            # Admin can archive from any status; all others follow the transition map
            if not (is_admin and data.status == "archived"):
                allowed = VALID_STATUS_TRANSITIONS.get(idea.status, [])
                if data.status not in allowed:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=(
                            f"Cannot transition from '{idea.status}' to '{data.status}'. "
                            f"Allowed transitions: {allowed}"
                        ),
                    )

        # Apply updates
        title_changed = "title" in update_fields
        description_changed = "description" in update_fields

        for field, value in update_fields.items():
            setattr(idea, field, value)

        # Re-categorise if content changed
        if title_changed or description_changed:
            from app.services import ai_service
            ai_result = await ai_service.categorize_idea(idea.description)
            idea.category = ai_result["category"]

        await self.db.flush()
        await self.db.refresh(idea)
        return await self.get_by_id(idea.id)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, idea_id: uuid.UUID, current_user: User) -> None:
        """Delete an idea; only the author may delete."""
        idea = await self.get_by_id(idea_id)

        if idea.author_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the author can delete this idea",
            )

        # Explicitly delete child records before the idea to avoid FK constraint issues.
        # SQLAlchemy may try to SET NULL on loaded relations before the DB CASCADE fires.
        from app.models.vote import Vote
        from app.models.comment import Comment

        await self.db.execute(sa_delete(Vote).where(Vote.idea_id == idea_id))
        await self.db.execute(sa_delete(Collaborator).where(Collaborator.idea_id == idea_id))
        await self.db.execute(sa_delete(Comment).where(Comment.idea_id == idea_id))

        await self.db.delete(idea)
        await self.db.flush()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _is_collaborator(self, idea_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """
        Check whether the user is a collaborator on the idea.

        Returns False gracefully if the collaborators table does not exist yet.
        """
        try:
            from app.models.collaborator import Collaborator  # type: ignore[import]
            from sqlalchemy import select as sa_select

            result = await self.db.execute(
                sa_select(Collaborator).where(
                    Collaborator.idea_id == idea_id,
                    Collaborator.user_id == user_id,
                )
            )
            return result.scalar_one_or_none() is not None
        except (ImportError, Exception):
            return False
