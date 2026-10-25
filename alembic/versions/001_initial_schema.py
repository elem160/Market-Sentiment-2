"""initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-17 01:25:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '001_initial_schema'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. analysis_jobs
    op.create_table(
        'analysis_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('ticker', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('stage', sa.String(length=30), nullable=False),
        sa.Column('progress_pct', sa.Float(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('run_id', sa.String(length=36), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analysis_jobs_ticker'), 'analysis_jobs', ['ticker'], unique=False)

    # 2. analysis_runs
    op.create_table(
        'analysis_runs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('ticker', sa.String(length=10), nullable=False),
        sa.Column('company_name', sa.String(length=255), nullable=False),
        sa.Column('asset_type', sa.String(length=20), nullable=False),
        sa.Column('session_type', sa.String(length=30), nullable=False),
        sa.Column('cache_key', sa.String(length=64), nullable=False),
        sa.Column('window_start_utc', sa.DateTime(), nullable=False),
        sa.Column('window_end_utc', sa.DateTime(), nullable=False),
        sa.Column('run_timestamp_utc', sa.DateTime(), nullable=False),
        sa.Column('decision', sa.String(length=10), nullable=False),
        sa.Column('sentiment_score', sa.Float(), nullable=False),
        sa.Column('decision_confidence', sa.Float(), nullable=False),
        sa.Column('evidence_quality', sa.Float(), nullable=False),
        sa.Column('rationale_summary', sa.Text(), nullable=False),
        sa.Column('inferences_json', sa.Text(), nullable=False),
        sa.Column('pipeline_mode', sa.String(length=30), nullable=False),
        sa.Column('model_versions_json', sa.Text(), nullable=False),
        sa.Column('config_version', sa.String(length=32), nullable=False),
        sa.Column('provider_outcomes_json', sa.Text(), nullable=False),
        sa.Column('cache_status', sa.String(length=10), nullable=False),
        sa.Column('metrics_json', sa.Text(), nullable=False),
        sa.Column('warnings_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analysis_runs_cache_key'), 'analysis_runs', ['cache_key'], unique=False)
    op.create_index(op.f('ix_analysis_runs_ticker'), 'analysis_runs', ['ticker'], unique=False)
    op.create_index('idx_runs_ticker_created', 'analysis_runs', ['ticker', 'created_at'], unique=False)

    # 3. article_evidence
    op.create_table(
        'article_evidence',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('source_name', sa.String(length=100), nullable=False),
        sa.Column('canonical_publisher', sa.String(length=100), nullable=False),
        sa.Column('canonical_url', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('published_at_utc', sa.DateTime(), nullable=False),
        sa.Column('retrieved_at_utc', sa.DateTime(), nullable=False),
        sa.Column('lead_text', sa.Text(), nullable=False),
        sa.Column('finbert_positive', sa.Float(), nullable=False),
        sa.Column('finbert_negative', sa.Float(), nullable=False),
        sa.Column('finbert_neutral', sa.Float(), nullable=False),
        sa.Column('finbert_directional_score', sa.Float(), nullable=False),
        sa.Column('finbert_confidence', sa.Float(), nullable=False),
        sa.Column('is_llm_catalyst', sa.Boolean(), nullable=True),
        sa.Column('catalyst_category', sa.String(length=30), nullable=True),
        sa.Column('exclusion_reason', sa.String(length=40), nullable=True),
        sa.Column('final_weight', sa.Float(), nullable=True),
        sa.Column('cluster_id', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_article_evidence_run_id'), 'article_evidence', ['run_id'], unique=False)

    # 4. observed_facts
    op.create_table(
        'observed_facts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('statement', sa.Text(), nullable=False),
        sa.Column('cited_article_id', sa.String(length=64), nullable=False),
        sa.Column('catalyst_category', sa.String(length=30), nullable=False),
        sa.Column('impact', sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_observed_facts_run_id'), 'observed_facts', ['run_id'], unique=False)


def downgrade() -> None:
    op.drop_table('observed_facts')
    op.drop_table('article_evidence')
    op.drop_table('analysis_runs')
    op.drop_table('analysis_jobs')
