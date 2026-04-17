"""add version and deployment_state to agents

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-16 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add version — backfill existing rows with a sentinel so NOT NULL holds.
    op.add_column(
        "agents",
        sa.Column("version", sa.String(), nullable=False, server_default="0.0.0"),
    )
    # Remove the server_default after backfill; new rows must supply the value.
    op.alter_column("agents", "version", server_default=None)

    op.add_column(
        "agents",
        sa.Column(
            "deployment_state",
            sa.String(),
            nullable=False,
            server_default="running",
        ),
    )

    op.create_unique_constraint("uq_agents_name_version", "agents", ["name", "version"])


def downgrade() -> None:
    op.drop_constraint("uq_agents_name_version", "agents", type_="unique")
    op.drop_column("agents", "deployment_state")
    op.drop_column("agents", "version")
