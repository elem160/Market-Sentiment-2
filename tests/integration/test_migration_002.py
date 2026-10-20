import os
import tempfile
import pytest
from sqlalchemy import create_engine, inspect, text
from alembic.config import Config
from alembic import command


def test_upgrade_from_001_to_002_schema():
    """
    Test upgrading an existing 001-schema SQLite database to head (002_freshness_reliability)
    using Alembic batch_alter_table (F-02).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_migration.db")
        db_url = f"sqlite:///{db_file.replace(os.sep, '/')}"

        ini_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "alembic.ini")
        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        engine = create_engine(db_url)

        try:
            # 1. Upgrade to 001_initial_schema first
            command.upgrade(alembic_cfg, "001_initial_schema")

            inspector = inspect(engine)

            # Verify 001 schema state: analysis_runs has no data_status
            run_cols_001 = {col["name"] for col in inspector.get_columns("analysis_runs")}
            assert "id" in run_cols_001
            assert "ticker" in run_cols_001
            assert "data_status" not in run_cols_001
            assert "llm_summary" not in run_cols_001

            # article_evidence in 001 has no effective_weight
            ev_cols_001 = {col["name"] for col in inspector.get_columns("article_evidence")}
            assert "effective_weight" not in ev_cols_001
            assert "age_hours" not in ev_cols_001

            # 2. Upgrade to 002_freshness_reliability
            command.upgrade(alembic_cfg, "002_freshness_reliability")

            # 3. Verify upgraded schema state
            inspector = inspect(engine)
            run_cols_002 = {col["name"] for col in inspector.get_columns("analysis_runs")}
            assert "data_status" in run_cols_002
            assert "llm_summary" in run_cols_002

            ev_cols_002 = {col["name"] for col in inspector.get_columns("article_evidence")}
            assert "effective_weight" in ev_cols_002
            assert "age_hours" in ev_cols_002

            # 4. Verify that published_at_utc accepts NULL values in article_evidence
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO analysis_runs (
                            id, ticker, company_name, asset_type, session_type, cache_key,
                            window_start_utc, window_end_utc, run_timestamp_utc, decision,
                            sentiment_score, decision_confidence, evidence_quality, rationale_summary,
                            inferences_json, pipeline_mode, model_versions_json, config_version,
                            provider_outcomes_json, cache_status, metrics_json, warnings_json,
                            created_at, data_status
                        ) VALUES (
                            'run_001', 'AAPL', 'Apple Inc.', 'EQUITY', 'REGULAR_HOURS', 'ckey',
                            '2026-10-19 14:00:00', '2026-10-19 18:00:00', '2026-10-19 18:00:00', 'HOLD',
                            0.0, 0.0, 0.0, 'Summary', '[]', 'DETERMINISTIC_FINBERT_ONLY', '{}', 'cfg',
                            '{}', 'MISS', '{}', '[]', '2026-10-19 18:00:00', 'NO_FRESH_NEWS'
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO article_evidence (
                            id, run_id, provider, source_name, canonical_publisher, canonical_url,
                            title, published_at_utc, retrieved_at_utc, lead_text, finbert_positive,
                            finbert_negative, finbert_neutral, finbert_directional_score, finbert_confidence,
                            effective_weight, age_hours
                        ) VALUES (
                            'art_null_ts', 'run_001', 'YFINANCE', 'Yahoo', 'Yahoo', 'https://example.com/null',
                            'Article With Null Timestamp', NULL, '2026-10-19 18:00:00', 'Lead', 0.0,
                            0.0, 1.0, 0.0, 0.0, 0.0, 0.0
                        )
                        """
                    )
                )
                result = conn.execute(text("SELECT id, published_at_utc FROM article_evidence WHERE id = 'art_null_ts'")).fetchone()
                assert result is not None
                assert result[0] == "art_null_ts"
                assert result[1] is None
        finally:
            engine.dispose()
