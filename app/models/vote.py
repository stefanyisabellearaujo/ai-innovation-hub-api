import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idea_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ideas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "idea_id", name="uq_votes_user_idea"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="votes")  # type: ignore[name-defined]  # noqa: F821
    idea: Mapped["Idea"] = relationship("Idea", back_populates="votes")  # type: ignore[name-defined]  # noqa: F821

    def __repr__(self) -> str:
        return f"<Vote user_id={self.user_id} idea_id={self.idea_id}>"
