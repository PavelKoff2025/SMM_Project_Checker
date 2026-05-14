"""add composite index on checks(user_id, created_at) and tighten NOT NULL

Revision ID: 8a1f2c3d4e5b
Revises: 7e706c20eb44
Create Date: 2026-05-14 17:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '8a1f2c3d4e5b'
down_revision = '7e706c20eb44'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE checks SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
    ))
    bind.execute(sa.text(
        "UPDATE checks SET status = 'pending' WHERE status IS NULL"
    ))
    with op.batch_alter_table('checks', schema=None) as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.String(length=20),
            nullable=False,
            existing_server_default=None,
        )
        batch_op.alter_column(
            'created_at',
            existing_type=sa.DateTime(),
            nullable=False,
        )
        batch_op.create_index(
            'ix_checks_user_created', ['user_id', 'created_at']
        )


def downgrade():
    with op.batch_alter_table('checks', schema=None) as batch_op:
        batch_op.drop_index('ix_checks_user_created')
        batch_op.alter_column(
            'created_at',
            existing_type=sa.DateTime(),
            nullable=True,
        )
        batch_op.alter_column(
            'status',
            existing_type=sa.String(length=20),
            nullable=True,
        )
