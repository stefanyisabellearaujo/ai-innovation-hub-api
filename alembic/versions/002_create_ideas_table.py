"""create ideas table

Revision ID: 002
Revises: 001
Create Date: 2026-04-12 00:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ideas",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="idea"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column(
            "author_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("votes_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Indexes for performance
    op.create_index("ix_ideas_title", "ideas", ["title"])
    op.create_index("ix_ideas_status", "ideas", ["status"])
    op.create_index("ix_ideas_category", "ideas", ["category"])
    op.create_index("ix_ideas_author_id", "ideas", ["author_id"])


def downgrade() -> None:
    op.drop_index("ix_ideas_author_id", table_name="ideas")
    op.drop_index("ix_ideas_category", table_name="ideas")
    op.drop_index("ix_ideas_status", table_name="ideas")
    op.drop_index("ix_ideas_title", table_name="ideas")
    op.drop_table("ideas")
