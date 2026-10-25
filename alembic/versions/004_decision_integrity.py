"""decision integrity schema update: publisher_inferred and hold_reason

Revision ID: 004_decision_integrity
Revises: 003_persistence_integrity
Create Date: 2026-10-20 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '004_decision_integrity'
down_revision: str | None = '003_persistence_integrity'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update article_evidence: add publisher_inferred
    with op.batch_alter_table('article_evidence', schema=None) as batch_op:
        batch_op.add_column(sa.Column('publisher_inferred', sa.Boolean(), nullable=False, server_default=sa.false()))

    # 2. Update analysis_runs: add hold_reason
    with op.batch_alter_table('analysis_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hold_reason', sa.String(length=40), nullable=True))


def downgrade() -> None:
    # 1. Revert analysis_runs
    with op.batch_alter_table('analysis_runs', schema=None) as batch_op:
        batch_op.drop_column('hold_reason')

    # 2. Revert article_evidence
    with op.batch_alter_table('article_evidence', schema=None) as batch_op:
        batch_op.drop_column('publisher_inferred')
