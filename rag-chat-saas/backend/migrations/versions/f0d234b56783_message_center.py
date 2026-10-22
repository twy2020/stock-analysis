"""Threaded feedback, system announcements and per-user read cursors."""
from alembic import op
import sqlalchemy as sa

revision = 'f0d234b56783'
down_revision = 'e9c123a45672'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('feedback_replies',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('feedback_id', sa.String(36), sa.ForeignKey('feedback.id'), nullable=False),
        sa.Column('author_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('username', sa.String(80), nullable=False), sa.Column('author_role', sa.String(16), nullable=False),
        sa.Column('body', sa.Text(), nullable=False), sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_feedback_replies_feedback_id', 'feedback_replies', ['feedback_id'])
    op.create_index('ix_feedback_replies_created_at', 'feedback_replies', ['created_at'])
    op.create_table('center_receipts',
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('kind', sa.String(20), primary_key=True), sa.Column('item_id', sa.String(36), primary_key=True),
        sa.Column('through', sa.Integer(), nullable=False))
    op.create_table('announcements',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('title', sa.String(120), nullable=False), sa.Column('content', sa.Text(), nullable=False),
        sa.Column('username', sa.String(80), nullable=False), sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_announcements_organization_id', 'announcements', ['organization_id'])
    op.create_index('ix_announcements_created_at', 'announcements', ['created_at'])


def downgrade():
    op.drop_table('center_receipts')
    op.drop_table('feedback_replies')
    op.drop_table('announcements')
