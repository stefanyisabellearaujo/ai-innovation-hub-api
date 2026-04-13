"""add collaboration tables (votes, collaborators, comments)

Revision ID: 003
Revises: 002
Create Date: 2026-04-12 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ votes
    op.create_table(
        "votes",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "idea_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ideas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "idea_id", name="uq_votes_user_idea"),
    )
    op.create_index("ix_votes_user_id", "votes", ["user_id"])
    op.create_index("ix_votes_idea_id", "votes", ["idea_id"])

    # ------------------------------------------------------------- collaborators
    op.create_table(
        "collaborators",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "idea_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ideas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(50), nullable=False, server_default="contributor"),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "idea_id", name="uq_collaborators_user_idea"),
        sa.CheckConstraint("role IN ('lead', 'contributor')", name="ck_collaborators_role"),
    )
    op.create_index("ix_collaborators_user_id", "collaborators", ["user_id"])
    op.create_index("ix_collaborators_idea_id", "collaborators", ["idea_id"])

    # --------------------------------------------------------------- comments
    op.create_table(
        "comments",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "idea_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ideas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_comments_user_id", "comments", ["user_id"])
    op.create_index("ix_comments_idea_id", "comments", ["idea_id"])


def downgrade() -> None:
    op.drop_index("ix_comments_idea_id", table_name="comments")
    op.drop_index("ix_comments_user_id", table_name="comments")
    op.drop_table("comments")

    op.drop_index("ix_collaborators_idea_id", table_name="collaborators")
    op.drop_index("ix_collaborators_user_id", table_name="collaborators")
    op.drop_table("collaborators")

    op.drop_index("ix_votes_idea_id", table_name="votes")
    op.drop_index("ix_votes_user_id", table_name="votes")
    op.drop_table("votes")
