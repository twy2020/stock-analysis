"""Durable chat jobs, replayable events and conversation read state."""
from alembic import op
import sqlalchemy as sa

revision = 'd8b012f34561'
down_revision = 'c7a901e2f340'
branch_labels = None
depends_on = None

def upgrade():
    for name in ('active_run_id','completed_run_id','seen_run_id'):
        op.add_column('conversations',sa.Column(name,sa.String(36)))
    op.add_column('messages',sa.Column('parent_message_id',sa.String(36)))
    op.add_column('messages',sa.Column('vote',sa.Integer(),nullable=False,server_default='0'))
    op.create_table('chat_runs',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('conversation_id',sa.String(36),sa.ForeignKey('conversations.id',ondelete='CASCADE'),nullable=False),
        sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('user_message_id',sa.String(36),nullable=False),
        sa.Column('assistant_message_id',sa.String(36),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('reasoning_enabled',sa.Boolean()),
        sa.Column('cancel_requested',sa.Boolean(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('completed_at',sa.DateTime(timezone=True)))
    for name in ('conversation_id','owner_id','status'):
        op.create_index('ix_chat_runs_'+name,'chat_runs',[name])
    op.create_table('chat_run_events',
        sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('run_id',sa.String(36),sa.ForeignKey('chat_runs.id',ondelete='CASCADE'),nullable=False),
        sa.Column('name',sa.String(32),nullable=False),sa.Column('payload',sa.JSON(),nullable=False))
    op.create_index('ix_chat_run_events_run_id','chat_run_events',['run_id'])

def downgrade():
    op.drop_table('chat_run_events'); op.drop_table('chat_runs')
    op.drop_column('messages','vote'); op.drop_column('messages','parent_message_id')
    for name in ('active_run_id','completed_run_id','seen_run_id'): op.drop_column('conversations',name)
