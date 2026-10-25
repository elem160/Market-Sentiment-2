import os
import tempfile

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command


def test_migration_002_downgrade_with_nullable_publication_times():
    """
    Verify that downgrading migration 002 with undated articles (published_at_utc IS NULL)
    safely preserves evidence rows by backfilling the Unix epoch sentinel instead of
    failing with a database NOT NULL constraint violation.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_migration_002_downgrade.db")
        db_url = f"sqlite:///{db_file.replace(os.sep, '/')}"

        ini_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "alembic.ini")
        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        engine = create_engine(db_url)

        try:
            # 1. Upgrade to 002_freshness_reliability
            command.upgrade(alembic_cfg, "002_freshness_reliability")

            # 2. Seed an analysis run and an undated article (published_at_utc IS NULL)
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
                            'run_undated', 'MSFT', 'Microsoft Corporation', 'EQUITY', 'REGULAR_HOURS', 'ckey_undated',
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
                            'art_undated_1', 'run_undated', 'YFINANCE', 'Reuters', 'Reuters', 'https://example.com/undated',
                            'Undated Article Title', NULL, '2026-10-19 18:00:00', 'Lead', 0.0,
                            0.0, 1.0, 0.0, 0.0, 0.0, 0.0
                        )
                        """
                    )
                )

            # 3. Execute downgrade to 001_initial_schema
            # Must succeed without IntegrityError / NOT NULL constraint failure
            command.downgrade(alembic_cfg, "001_initial_schema")

            # 4. Verify table schema and data preservation in 001 schema
            inspector = inspect(engine)
            columns = {col["name"]: col for col in inspector.get_columns("article_evidence")}
            assert "effective_weight" not in columns
            assert "age_hours" not in columns
            assert columns["published_at_utc"]["nullable"] is False

            # Verify the article record was preserved and backfilled with sentinel timestamp
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT id, published_at_utc FROM article_evidence WHERE id = 'art_undated_1'")
                ).fetchone()
                assert row is not None
                assert row[0] == "art_undated_1"
                assert str(row[1]).startswith("1970-01-01")

            # 5. Verify clean upgrade back to head
            command.upgrade(alembic_cfg, "head")
            inspector = inspect(engine)
            columns_head = {col["name"]: col for col in inspector.get_columns("article_evidence")}
            assert "effective_weight" in columns_head
            assert "age_hours" in columns_head
            assert columns_head["published_at_utc"]["nullable"] is True

        finally:
            engine.dispose()
