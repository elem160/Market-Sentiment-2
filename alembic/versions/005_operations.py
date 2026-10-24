"""operations schema update: llm_cost_usd and operational indexes

Revision ID: 005_operations
Revises: 004_decision_integrity
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '005_operations'
down_revision: Union[str, None] = '004_decision_integrity'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update analysis_runs: add llm_cost_usd and created_at index
    with op.batch_alter_table('analysis_runs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('llm_cost_usd', sa.Float(), nullable=False, server_default='0.0')
        )
        batch_op.create_index('ix_analysis_runs_created_at', ['created_at'], unique=False)

    # Backfill llm_cost_usd from metrics_json if present (SQLite JSON extract)
    op.execute(
        "UPDATE analysis_runs "
        "SET llm_cost_usd = COALESCE(CAST(json_extract(metrics_json, '$.estimated_cost_usd') AS REAL), 0.0) "
        "WHERE metrics_json IS NOT NULL;"
    )

    # 2. Update analysis_jobs: add expires_at index
    with op.batch_alter_table('analysis_jobs', schema=None) as batch_op:
        batch_op.create_index('ix_analysis_jobs_expires_at', ['expires_at'], unique=False)


def downgrade() -> None:
    # 1. Revert analysis_jobs
    with op.batch_alter_table('analysis_jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_analysis_jobs_expires_at')

    # 2. Revert analysis_runs
    with op.batch_alter_table('analysis_runs', schema=None) as batch_op:
        batch_op.drop_index('ix_analysis_runs_created_at')
        batch_op.drop_column('llm_cost_usd')
