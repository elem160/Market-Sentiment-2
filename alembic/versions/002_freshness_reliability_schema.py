"""freshness and reliability schema update

Revision ID: 002_freshness_reliability
Revises: 001_initial_schema
Create Date: 2026-10-19 02:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002_freshness_reliability'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('analysis_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('data_status', sa.String(length=30), nullable=False, server_default='OK'))
        batch_op.add_column(sa.Column('llm_summary', sa.Text(), nullable=True))

    with op.batch_alter_table('article_evidence', schema=None) as batch_op:
        batch_op.add_column(sa.Column('effective_weight', sa.Float(), nullable=True, server_default='0.0'))
        batch_op.add_column(sa.Column('age_hours', sa.Float(), nullable=True, server_default='0.0'))
        batch_op.alter_column('published_at_utc', existing_type=sa.DateTime(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('article_evidence', schema=None) as batch_op:
        batch_op.alter_column('published_at_utc', existing_type=sa.DateTime(), nullable=False)
        batch_op.drop_column('age_hours')
        batch_op.drop_column('effective_weight')

    with op.batch_alter_table('analysis_runs', schema=None) as batch_op:
        batch_op.drop_column('llm_summary')
        batch_op.drop_column('data_status')
