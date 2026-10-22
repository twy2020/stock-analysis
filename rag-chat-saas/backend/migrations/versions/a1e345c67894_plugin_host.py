"""Service plugins, expiring knowledge spaces, analysis events and chat images."""
from alembic import op
import sqlalchemy as sa

revision='a1e345c67894'
down_revision='f0d234b56783'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('plugin_knowledge_spaces',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('service_id',sa.String(120),nullable=False),
        sa.Column('tenant_id',sa.String(120),nullable=False),sa.Column('context',sa.JSON(),nullable=False),
        sa.Column('kind',sa.String(20),nullable=False),sa.Column('name',sa.String(200),nullable=False),
        sa.Column('promotion_key',sa.String(64),unique=True),sa.Column('expires_at',sa.DateTime()),
        sa.Column('created_at',sa.DateTime(),nullable=False))
    for key in ('service_id','tenant_id','expires_at'):op.create_index('ix_plugin_knowledge_spaces_'+key,'plugin_knowledge_spaces',[key])
    op.create_table('plugin_knowledge_documents',
        sa.Column('space_id',sa.String(36),sa.ForeignKey('plugin_knowledge_spaces.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('id',sa.String(160),primary_key=True),sa.Column('title',sa.String(500),nullable=False),
        sa.Column('revision',sa.String(160),nullable=False),sa.Column('chunks',sa.JSON(),nullable=False))
    op.create_table('plugin_analysis_runs',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('request_id',sa.String(36),nullable=False),
        sa.Column('service_id',sa.String(120),nullable=False),sa.Column('tenant_id',sa.String(120),nullable=False),
        sa.Column('context',sa.JSON(),nullable=False),sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('space_id',sa.String(36),nullable=False),sa.Column('payload',sa.JSON(),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),sa.Column('content',sa.Text(),nullable=False),
        sa.Column('cancel_requested',sa.Boolean(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('completed_at',sa.DateTime()),sa.Column('expires_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('service_id','tenant_id','request_id'))
    for key in ('service_id','status','expires_at'):op.create_index('ix_plugin_analysis_runs_'+key,'plugin_analysis_runs',[key])
    op.create_table('plugin_analysis_events',sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('run_id',sa.String(36),sa.ForeignKey('plugin_analysis_runs.id',ondelete='CASCADE'),nullable=False),
        sa.Column('name',sa.String(32),nullable=False),sa.Column('payload',sa.JSON(),nullable=False))
    op.create_index('ix_plugin_analysis_events_run_id','plugin_analysis_events',['run_id'])
    op.create_table('chat_images',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('message_id',sa.String(36),sa.ForeignKey('messages.id',ondelete='CASCADE')),
        sa.Column('name',sa.String(200),nullable=False),sa.Column('media_type',sa.String(80),nullable=False),
        sa.Column('content',sa.LargeBinary(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False))
    for key in ('owner_id','message_id'):op.create_index('ix_chat_images_'+key,'chat_images',[key])


def downgrade():
    for table in ('chat_images','plugin_analysis_events','plugin_analysis_runs','plugin_knowledge_documents','plugin_knowledge_spaces'):
        op.drop_table(table)
