import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.vote import Vote
    from app.models.collaborator import Collaborator
    from app.models.comment import Comment


class Idea(Base):
    """SQLAlchemy model representing an AI innovation idea."""

    __tablename__ = "ideas"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="idea", index=True
    )
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    votes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    author: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="ideas", lazy="selectin"
    )
    votes: Mapped[list["Vote"]] = relationship(
        "Vote", back_populates="idea", lazy="select", passive_deletes=True
    )
    collaborators: Mapped[list["Collaborator"]] = relationship(
        "Collaborator", back_populates="idea", lazy="select", passive_deletes=True
    )
    comments: Mapped[list["Comment"]] = relationship(
        "Comment", back_populates="idea", lazy="select", passive_deletes=True
    )

    # Indexes are declared inline via index=True on each column above

    def __repr__(self) -> str:
        return f"<Idea id={self.id} title={self.title!r} status={self.status}>"
