import os
import tempfile

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command


def test_upgrade_from_003_to_004_schema_and_roundtrip():
    """
    Test upgrading an existing 003-schema SQLite database to 004_decision_integrity,
    verifying publisher_inferred and hold_reason columns, then downgrading cleanly.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_migration_004.db")
        db_url = f"sqlite:///{db_file.replace(os.sep, '/')}"

        ini_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "alembic.ini")
        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        engine = create_engine(db_url)

        try:
            # 1. Upgrade to 003_persistence_integrity first
            command.upgrade(alembic_cfg, "003_persistence_integrity")

            # Seed data in 003 schema
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
                            created_at, data_status, is_cacheable
                        ) VALUES (
                            'run_p2', 'AAPL', 'Apple Inc.', 'EQUITY', 'REGULAR_HOURS', 'ckey_p2',
                            '2026-10-19 14:00:00', '2026-10-19 18:00:00', '2026-10-19 18:00:00', 'HOLD',
                            0.0, 0.0, 0.0, 'Summary', '[]', 'DETERMINISTIC_FINBERT_ONLY', '{}', 'cfg',
                            '{}', 'MISS', '{}', '[]', '2026-10-19 18:00:00', 'OK', 1
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO article_evidence (
                            id, article_id, run_id, provider, source_name, canonical_publisher, canonical_url,
                            title, published_at_utc, retrieved_at_utc, lead_text, finbert_positive,
                            finbert_negative, finbert_neutral, finbert_directional_score, finbert_confidence,
                            effective_weight, age_hours
                        ) VALUES (
                            'run_p2_art1', 'art1', 'run_p2', 'YFINANCE', 'Reuters', 'Reuters', 'https://example.com/art',
                            'Article Title', '2026-10-19 17:00:00', '2026-10-19 18:00:00', 'Lead', 0.8,
                            0.1, 0.1, 0.7, 0.9, 1.0, 1.0
                        )
                        """
                    )
                )

            # 2. Upgrade to 004_decision_integrity
            command.upgrade(alembic_cfg, "004_decision_integrity")

            inspector = inspect(engine)

            # Verify analysis_runs has hold_reason column
            run_cols = {col["name"]: col for col in inspector.get_columns("analysis_runs")}
            assert "hold_reason" in run_cols

            # Verify article_evidence has publisher_inferred column
            art_cols = {col["name"]: col for col in inspector.get_columns("article_evidence")}
            assert "publisher_inferred" in art_cols

            # Verify seeded article defaulted publisher_inferred to False (0)
            with engine.connect() as conn:
                row = conn.execute(text("SELECT publisher_inferred FROM article_evidence WHERE id = 'run_p2_art1'")).fetchone()
                assert row[0] in (0, False)

                # Insert a new record with hold_reason and publisher_inferred = 1
                conn.execute(
                    text(
                        """
                        INSERT INTO article_evidence (
                            id, article_id, run_id, provider, source_name, canonical_publisher,
                            publisher_inferred, canonical_url, title, published_at_utc, retrieved_at_utc,
                            lead_text, finbert_positive, finbert_negative, finbert_neutral,
                            finbert_directional_score, finbert_confidence, effective_weight, age_hours
                        ) VALUES (
                            'run_p2_art2', 'art2', 'run_p2', 'GOOGLE_RSS_AGGREGATOR', 'Google News',
                            'Google News', 1, 'https://example.com/art2', 'Google Title',
                            '2026-10-19 17:30:00', '2026-10-19 18:00:00', 'Lead 2', 0.8,
                            0.1, 0.1, 0.7, 0.9, 1.0, 1.0
                        )
                        """
                    )
                )
                row2 = conn.execute(text("SELECT publisher_inferred FROM article_evidence WHERE id = 'run_p2_art2'")).fetchone()
                assert row2[0] in (1, True)

            # 3. Test downgrade back to 003_persistence_integrity
            command.downgrade(alembic_cfg, "003_persistence_integrity")

            inspector = inspect(engine)
            run_cols_post = {col["name"]: col for col in inspector.get_columns("analysis_runs")}
            art_cols_post = {col["name"]: col for col in inspector.get_columns("article_evidence")}
            assert "hold_reason" not in run_cols_post
            assert "publisher_inferred" not in art_cols_post

        finally:
            engine.dispose()
