"""ip_addresses.vps_id foreign key

Enforces IPAM consistency at the database level: an assigned address always
references a real VPS; deleting the VPS releases the address (SET NULL).

Revision ID: b7f2c1a94d03
Revises: 6918a468329b
Create Date: 2026-08-21 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b7f2c1a94d03'
down_revision: Union[str, None] = '6918a468329b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = 'fk_ip_addresses_vps_id_vps'


def upgrade() -> None:
    # Clean up any dangling references before adding the constraint.
    op.execute(
        "UPDATE ip_addresses SET vps_id = NULL "
        "WHERE vps_id IS NOT NULL AND vps_id NOT IN (SELECT id FROM vps)"
    )
    op.create_foreign_key(
        FK_NAME, 'ip_addresses', 'vps', ['vps_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint(FK_NAME, 'ip_addresses', type_='foreignkey')
