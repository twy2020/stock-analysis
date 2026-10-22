"""Cache OCR image descriptions for subsequent chat turns."""
from alembic import op
import sqlalchemy as sa

revision='b2f456d78905'
down_revision='a1e345c67894'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('chat_images',sa.Column('analysis_json',sa.JSON(),nullable=True))


def downgrade():
    op.drop_column('chat_images','analysis_json')
