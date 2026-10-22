"""Persist feedback snapshots and validated image attachments."""
from alembic import op
import sqlalchemy as sa

revision = 'c7a901e2f340'
down_revision = 'b6f8a1d2e4c0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('feedback',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('username', sa.String(80), nullable=False),
        sa.Column('conversation_id', sa.String(36)),
        sa.Column('conversation_title', sa.String(200), nullable=False),
        sa.Column('comment', sa.Text(), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    for column in ('organization_id', 'owner_id', 'status', 'created_at'):
        op.create_index(f'ix_feedback_{column}', 'feedback', [column])
    op.create_table('feedback_images',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('feedback_id', sa.String(36), sa.ForeignKey('feedback.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('media_type', sa.String(40), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False))
    op.create_index('ix_feedback_images_feedback_id', 'feedback_images', ['feedback_id'])


def downgrade():
    op.drop_table('feedback_images')
    op.drop_table('feedback')
