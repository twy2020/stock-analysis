"""add conversation summary cursor

Revision ID: 4f8c92a1e441
Revises: 1223878efc5d
Create Date: 2026-09-24 21:25:00
"""

from alembic import op
import sqlalchemy as sa


revision = "4f8c92a1e441"
down_revision = "1223878efc5d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("summary_through_message_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("summary_through_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("summary_through_at")
        batch.drop_column("summary_through_message_id")
