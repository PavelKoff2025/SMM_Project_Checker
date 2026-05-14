"""add llm_provider column to checks

Revision ID: 9b2e3d4f5a6c
Revises: 8a1f2c3d4e5b
Create Date: 2026-05-14 18:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '9b2e3d4f5a6c'
down_revision = '8a1f2c3d4e5b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('checks', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'llm_provider',
                sa.String(length=20),
                nullable=False,
                server_default='deepseek',
            )
        )


def downgrade():
    with op.batch_alter_table('checks', schema=None) as batch_op:
        batch_op.drop_column('llm_provider')
