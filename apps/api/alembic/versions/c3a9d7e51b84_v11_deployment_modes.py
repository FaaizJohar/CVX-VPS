"""v1.1 deployment modes: local control-plane deployments + node kinds.

Revision ID: c3a9d7e51b84
Revises: b7f2c1a94d03
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a9d7e51b84"
down_revision: str | None = "b7f2c1a94d03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nodes",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default="agent",
        ),
    )
    op.add_column(
        "vps",
        sa.Column(
            "deployment_mode",
            sa.String(length=16),
            nullable=False,
            server_default="node",
        ),
    )
    op.create_check_constraint(
        "ck_vps_deployment_mode", "vps", "deployment_mode IN ('node', 'local')"
    )
    op.create_index("ix_nodes_kind", "nodes", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_nodes_kind", table_name="nodes")
    op.drop_constraint("ck_vps_deployment_mode", "vps", type_="check")
    op.drop_column("vps", "deployment_mode")
    op.drop_column("nodes", "kind")
