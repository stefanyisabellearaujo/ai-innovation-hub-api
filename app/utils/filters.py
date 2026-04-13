import uuid

from sqlalchemy import or_, select

from app.models.idea import Idea


def apply_idea_filters(
    query,
    *,
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
    author_id: uuid.UUID | None = None,
    collaborator_id: uuid.UUID | None = None,
):
    """
    Apply dynamic filters to an ideas SQLAlchemy select statement.

    Parameters
    ----------
    query:
        A SQLAlchemy select() statement targeting the Idea model.
    status:
        Filter by exact status value.
    category:
        Filter by exact category value.
    search:
        Case-insensitive substring search on title and description.
    author_id:
        Filter ideas authored by this user UUID.
    collaborator_id:
        Filter ideas where this user is a collaborator.
        Silently skipped if the collaborators table does not yet exist.

    Returns
    -------
    The filtered query.
    """
    if status is not None:
        # Support comma-separated status values e.g. "idea,evaluation,development"
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if len(statuses) == 1:
            query = query.where(Idea.status == statuses[0])
        elif len(statuses) > 1:
            query = query.where(Idea.status.in_(statuses))

    if category is not None:
        query = query.where(Idea.category == category)

    if author_id is not None:
        query = query.where(Idea.author_id == author_id)

    if search is not None:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Idea.title.ilike(pattern),
                Idea.description.ilike(pattern),
            )
        )

    if collaborator_id is not None:
        try:
            from app.models.collaborator import Collaborator  # type: ignore[import]

            subquery = (
                select(Collaborator.idea_id)
                .where(Collaborator.user_id == collaborator_id)
                .scalar_subquery()
            )
            query = query.where(Idea.id.in_(subquery))
        except (ImportError, Exception):
            # Collaborators table not yet available (M3); skip filter gracefully
            pass

    return query
