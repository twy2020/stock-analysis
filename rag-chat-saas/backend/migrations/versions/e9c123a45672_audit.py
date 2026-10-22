"""Immutable activity history and per-call model diagnostics."""
from alembic import op
import sqlalchemy as sa

revision = 'e9c123a45672'
down_revision = 'd8b012f34561'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('audit_records',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36)), sa.Column('user_id', sa.String(36)),
        sa.Column('username', sa.String(80), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False), sa.Column('action', sa.String(80), nullable=False),
        sa.Column('status', sa.String(20), nullable=False), sa.Column('run_id', sa.String(36)),
        sa.Column('conversation_id', sa.String(36)), sa.Column('latency_ms', sa.Integer()),
        sa.Column('details', sa.JSON(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True)))
    for name in ('organization_id','user_id','kind','action','status','run_id','conversation_id','created_at'):
        op.create_index('ix_audit_records_'+name, 'audit_records', [name])


def downgrade():
    op.drop_table('audit_records')
