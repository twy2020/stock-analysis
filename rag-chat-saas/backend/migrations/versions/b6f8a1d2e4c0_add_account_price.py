"""add account price snapshot

Revision ID: b6f8a1d2e4c0
Revises: 9d2d0b5d3c11
"""

from alembic import op
import sqlalchemy as sa


revision = "b6f8a1d2e4c0"
down_revision = "9d2d0b5d3c11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_accounts") as batch:
        batch.add_column(sa.Column("price", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_accounts") as batch:
        batch.drop_column("price")
