import os
import tempfile
from sqlalchemy import create_engine, inspect, text
from alembic.config import Config
from alembic import command


def test_upgrade_from_002_to_003_schema_and_roundtrip():
    """
    Test upgrading an existing 002-schema SQLite database to 003_persistence_integrity
    with seeded data, verifying backfill and unique index, then downgrading cleanly.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_migration_003.db")
        db_url = f"sqlite:///{db_file.replace(os.sep, '/')}"

        ini_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "alembic.ini")
        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        engine = create_engine(db_url)

        try:
            # 1. Upgrade to 002_freshness_reliability first
            command.upgrade(alembic_cfg, "002_freshness_reliability")

            # Seed data in 002 schema
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
                            'run_p1', 'AAPL', 'Apple Inc.', 'EQUITY', 'REGULAR_HOURS', 'ckey_p1',
                            '2026-10-19 14:00:00', '2026-10-19 18:00:00', '2026-10-19 18:00:00', 'HOLD',
                            0.0, 0.0, 0.0, 'Summary', '[]', 'DETERMINISTIC_FINBERT_ONLY', '{}', 'cfg',
                            '{}', 'MISS', '{}', '[]', '2026-10-19 18:00:00', 'OK'
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
                            'run_p1_art_stable_123', 'run_p1', 'YFINANCE', 'Reuters', 'Reuters', 'https://example.com/art',
                            'Article Title', '2026-10-19 17:00:00', '2026-10-19 18:00:00', 'Lead', 0.8,
                            0.1, 0.1, 0.7, 0.9, 1.0, 1.0
                        )
                        """
                    )
                )

            # 2. Upgrade to head (003_persistence_integrity)
            command.upgrade(alembic_cfg, "head")

            inspector = inspect(engine)
            run_cols = {col["name"]: col for col in inspector.get_columns("analysis_runs")}
            assert "is_cacheable" in run_cols

            # Verify backfill
            with engine.begin() as conn:
                row = conn.execute(
                    text("SELECT article_id, is_cacheable FROM article_evidence JOIN analysis_runs ON article_evidence.run_id = analysis_runs.id WHERE article_evidence.id = 'run_p1_art_stable_123'")
                ).fetchone()
                assert row is not None
                assert row[0] == "art_stable_123"
                assert row[1] in (1, True)

            # Verify unique constraint on (run_id, article_id)
            indices = inspector.get_indexes("article_evidence")
            uq_idx = next((i for i in indices if i["name"] == "uq_article_evidence_run_article"), None)
            assert uq_idx is not None
            assert bool(uq_idx["unique"]) is True
            assert set(uq_idx["column_names"]) == {"run_id", "article_id"}

            # 3. Test Downgrade back to 002
            command.downgrade(alembic_cfg, "002_freshness_reliability")
            inspector = inspect(engine)
            run_cols_down = {col["name"] for col in inspector.get_columns("analysis_runs")}
            assert "is_cacheable" not in run_cols_down
            ev_cols_down = {col["name"] for col in inspector.get_columns("article_evidence")}
            assert "article_id" not in ev_cols_down

        finally:
            engine.dispose()
