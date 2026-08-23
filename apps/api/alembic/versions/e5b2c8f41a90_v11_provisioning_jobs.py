"""v1.1: provisioning jobs table + agent-reported public IP.

Revision ID: e5b2c8f41a90
Revises: c3a9d7e51b84
Create Date: 2026-08-22
"""

import sqlalchemy as sa
from alembic import op

revision = "e5b2c8f41a90"
down_revision = "c3a9d7e51b84"
branch_labels = None
depends_on = None

STATUS_CHECK = sa.CheckConstraint(
    "status IN ('queued','running','succeeded','failed')",
    name="ck_jobs_status",
)


def upgrade() -> None:
    op.add_column("vps", sa.Column("root_password_encrypted", sa.Text()))
    op.create_table(
        "provisioning_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False, server_default="vps_create"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(64), nullable=False, server_default=""),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
        sa.Column("vps_id", sa.Uuid(), sa.ForeignKey("vps.id", ondelete="SET NULL")),
        sa.Column("node_id", sa.Uuid()),
        sa.Column("user_id", sa.Uuid()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        STATUS_CHECK,
    )
    op.create_index("ix_provisioning_jobs_status", "provisioning_jobs", ["status"])
    op.create_index("ix_provisioning_jobs_vps_id", "provisioning_jobs", ["vps_id"])
    op.create_index("ix_provisioning_jobs_user_id", "provisioning_jobs", ["user_id"])
    op.create_index(
        "ix_jobs_status_created", "provisioning_jobs", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_column("vps", "root_password_encrypted")
    op.drop_index("ix_jobs_status_created", table_name="provisioning_jobs")
    op.drop_index("ix_provisioning_jobs_user_id", table_name="provisioning_jobs")
    op.drop_index("ix_provisioning_jobs_vps_id", table_name="provisioning_jobs")
    op.drop_index("ix_provisioning_jobs_status", table_name="provisioning_jobs")
    op.drop_table("provisioning_jobs")
