import os
import tempfile
from sqlalchemy import create_engine, inspect, text
from alembic.config import Config
from alembic import command


def test_upgrade_from_004_to_005_schema_and_roundtrip():
    """
    Test upgrading an existing 004-schema SQLite database to 005_operations,
    verifying llm_cost_usd column and backfill from metrics_json, operational indexes,
    then downgrading cleanly.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_migration_005.db")
        db_url = f"sqlite:///{db_file.replace(os.sep, '/')}"

        ini_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "alembic.ini")
        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        engine = create_engine(db_url)

        try:
            # 1. Upgrade to 004_decision_integrity first
            command.upgrade(alembic_cfg, "004_decision_integrity")

            # Seed data in 004 schema with metrics_json containing estimated_cost_usd
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
                            created_at, data_status, is_cacheable, hold_reason
                        ) VALUES (
                            'run_op', 'NVDA', 'NVIDIA Corporation', 'EQUITY', 'REGULAR_HOURS', 'ckey_op',
                            '2026-10-24 14:00:00', '2026-10-24 18:00:00', '2026-10-24 18:00:00', 'BUY',
                            0.75, 0.90, 0.85, 'Summary', '[]', 'HYBRID_FINBERT_LLM', '{}', 'cfg',
                            '{}', 'MISS', '{"estimated_cost_usd": 0.0125}', '[]',
                            '2026-10-24 18:00:00', 'OK', 1, NULL
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO analysis_jobs (
                            id, ticker, status, stage, progress_pct, message, run_id,
                            error_message, created_at, updated_at, expires_at
                        ) VALUES (
                            'job_op', 'NVDA', 'COMPLETED', 'DONE', 1.0, 'Done', 'run_op',
                            NULL, '2026-10-24 18:00:00', '2026-10-24 18:01:00', '2026-10-24 19:00:00'
                        )
                        """
                    )
                )

            # 2. Upgrade to 005_operations
            command.upgrade(alembic_cfg, "005_operations")

            inspector = inspect(engine)
            run_cols = {c["name"]: c for c in inspector.get_columns("analysis_runs")}
            assert "llm_cost_usd" in run_cols, "analysis_runs.llm_cost_usd column must exist in 005"

            # Verify backfill populated llm_cost_usd from metrics_json
            with engine.connect() as conn:
                row = conn.execute(
                    text("SELECT llm_cost_usd FROM analysis_runs WHERE id = 'run_op'")
                ).fetchone()
                assert row is not None
                assert abs(row[0] - 0.0125) < 1e-5, f"Expected 0.0125 backfilled, got {row[0]}"

            # Verify indexes
            run_indexes = {idx["name"] for idx in inspector.get_indexes("analysis_runs")}
            assert "ix_analysis_runs_created_at" in run_indexes

            job_indexes = {idx["name"] for idx in inspector.get_indexes("analysis_jobs")}
            assert "ix_analysis_jobs_expires_at" in job_indexes

            # 3. Test clean downgrade to 004
            command.downgrade(alembic_cfg, "004_decision_integrity")

            inspector_down = inspect(engine)
            run_cols_down = {c["name"]: c for c in inspector_down.get_columns("analysis_runs")}
            assert "llm_cost_usd" not in run_cols_down, "llm_cost_usd must be dropped on downgrade"

            # 4. Re-upgrade to head
            command.upgrade(alembic_cfg, "head")

        finally:
            engine.dispose()
