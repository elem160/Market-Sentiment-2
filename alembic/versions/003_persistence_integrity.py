"""persistence and integrity schema update

Revision ID: 003_persistence_integrity
Revises: 002_freshness_reliability
Create Date: 2026-10-20 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '003_persistence_integrity'
down_revision: str | None = '002_freshness_reliability'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update analysis_runs: add is_cacheable, widen ticker to VARCHAR(32)
    with op.batch_alter_table('analysis_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_cacheable', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.alter_column('ticker', existing_type=sa.String(length=10), type_=sa.String(length=32), nullable=False)

    # 2. Update analysis_jobs: widen ticker to VARCHAR(32)
    with op.batch_alter_table('analysis_jobs', schema=None) as batch_op:
        batch_op.alter_column('ticker', existing_type=sa.String(length=10), type_=sa.String(length=32), nullable=False)

    # 3. Update article_evidence: add article_id, backfill, set NOT NULL and add unique index
    with op.batch_alter_table('article_evidence', schema=None) as batch_op:
        batch_op.add_column(sa.Column('article_id', sa.String(length=64), nullable=True))

    op.execute(
        "UPDATE article_evidence "
        "SET article_id = CASE "
        "  WHEN id LIKE run_id || '_%' THEN substr(id, length(run_id) + 2) "
        "  ELSE id "
        "END "
        "WHERE article_id IS NULL"
    )

    with op.batch_alter_table('article_evidence', schema=None) as batch_op:
        batch_op.alter_column('article_id', existing_type=sa.String(length=64), nullable=False)
        batch_op.create_index('uq_article_evidence_run_article', ['run_id', 'article_id'], unique=True)


def downgrade() -> None:
    # 1. Revert article_evidence
    with op.batch_alter_table('article_evidence', schema=None) as batch_op:
        batch_op.drop_index('uq_article_evidence_run_article')
        batch_op.drop_column('article_id')

    # 2. Revert analysis_jobs
    with op.batch_alter_table('analysis_jobs', schema=None) as batch_op:
        batch_op.alter_column('ticker', existing_type=sa.String(length=32), type_=sa.String(length=10), nullable=False)

    # 3. Revert analysis_runs
    with op.batch_alter_table('analysis_runs', schema=None) as batch_op:
        batch_op.alter_column('ticker', existing_type=sa.String(length=32), type_=sa.String(length=10), nullable=False)
        batch_op.drop_column('is_cacheable')
