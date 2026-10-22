"""add account base url

Revision ID: 9d2d0b5d3c11
Revises: 4f8c92a1e441
"""

from alembic import op
import sqlalchemy as sa


revision = "9d2d0b5d3c11"
down_revision = "4f8c92a1e441"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_accounts") as batch:
        batch.add_column(sa.Column("base_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_accounts") as batch:
        batch.drop_column("base_url")
