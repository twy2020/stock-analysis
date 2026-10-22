"""Persist per-run stock web research opt-in."""
from alembic import op
import sqlalchemy as sa

revision = 'a2e345c67895'
down_revision = 'b2f456d78905'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_runs', sa.Column('web_enabled', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('chat_runs') as batch:
        batch.drop_column('web_enabled')
