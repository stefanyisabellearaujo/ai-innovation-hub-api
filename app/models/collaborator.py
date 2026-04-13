import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Collaborator(Base):
    __tablename__ = "collaborators"

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
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="contributor"
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "idea_id", name="uq_collaborators_user_idea"),
        CheckConstraint("role IN ('lead', 'contributor')", name="ck_collaborators_role"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="collaborations")  # type: ignore[name-defined]  # noqa: F821
    idea: Mapped["Idea"] = relationship("Idea", back_populates="collaborators")  # type: ignore[name-defined]  # noqa: F821

    def __repr__(self) -> str:
        return f"<Collaborator user_id={self.user_id} idea_id={self.idea_id} role={self.role}>"
