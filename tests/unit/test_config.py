import hashlib
import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.config import BASE_DIR, Settings, settings
from app.services.orchestrator import AnalysisOrchestrator


def test_base_dir_anchoring():
    """Verify BASE_DIR is properly resolved from package and contains core assets."""
    assert BASE_DIR.is_absolute()
    assert (BASE_DIR / "app").exists()
    assert (BASE_DIR / "alembic.ini").exists()


def test_relative_sqlite_path_anchored_to_base_dir():
    """Verify relative SQLite paths resolve to absolute paths anchored to BASE_DIR."""
    custom_settings = Settings(DATABASE_URL="sqlite:///./data/test_custom.db")
    expected_prefix = f"sqlite:///{BASE_DIR.as_posix()}"
    assert custom_settings.DATABASE_URL.startswith(expected_prefix)
    assert custom_settings.DATABASE_URL.endswith("/data/test_custom.db")

    # In-memory SQLite remains untouched
    memory_settings = Settings(DATABASE_URL="sqlite:///:memory:")
    assert memory_settings.DATABASE_URL == "sqlite:///:memory:"


def test_cache_bucket_validation():
    """Verify cache bucket minutes must be between 1 and 1440 and divide 1440 evenly."""
    # Valid bucket (divides 1440 evenly)
    valid_settings = Settings(CACHE_INTRADAY_BUCKET_MINUTES=30)
    assert valid_settings.CACHE_INTRADAY_BUCKET_MINUTES == 30

    # Invalid: 17 does not divide 1440 evenly
    with pytest.raises(ValidationError) as exc_info:
        Settings(CACHE_INTRADAY_BUCKET_MINUTES=17)
    assert "divide 1440 evenly" in str(exc_info.value)

    # Invalid: 0 is out of bounds
    with pytest.raises(ValidationError) as exc_info:
        Settings(CACHE_INTRADAY_BUCKET_MINUTES=0)
    assert "between 1 and 1440" in str(exc_info.value)

    # Invalid: > 1440
    with pytest.raises(ValidationError) as exc_info:
        Settings(CACHE_INTRADAY_BUCKET_MINUTES=1500)
    assert "between 1 and 1440" in str(exc_info.value)


def test_config_hash_fingerprint():
    """Verify config hash includes ALGORITHM_VERSION, models, limits, and fallback model."""
    h1 = settings.get_config_hash()
    assert len(h1) == 12

    # Modifying fallback model ID produces different hash
    custom_settings = Settings(LLM_FALLBACK_MODEL_ID="nvidia/custom-fallback:free")
    h2 = custom_settings.get_config_hash()
    assert h1 != h2

    # Modifying algorithm version produces different hash
    custom_algo = Settings(ALGORITHM_VERSION=3)
    assert custom_algo.get_config_hash() != h1


def test_compute_cache_key():
    """Verify compute_cache_key implements sha256(ALGORITHM_VERSION, ticker, asset_type, bucket, enable_llm, config_hash)."""
    k1 = AnalysisOrchestrator.compute_cache_key("AAPL", "2026-10-24_09-30", "yfinance_rss", True, "EQUITY")
    expected_raw = f"{settings.ALGORITHM_VERSION}:AAPL:EQUITY:2026-10-24_09-30:True:{settings.get_config_hash()}"
    assert k1 == hashlib.sha256(expected_raw.encode()).hexdigest()

    # Changing asset_type produces different key
    k_crypto = AnalysisOrchestrator.compute_cache_key("BTC", "2026-10-24_09-30", "yfinance_rss", True, "CRYPTO")
    assert k1 != k_crypto

    # Changing enable_llm produces different key
    k_no_llm = AnalysisOrchestrator.compute_cache_key("AAPL", "2026-10-24_09-30", "yfinance_rss", False, "EQUITY")
    assert k1 != k_no_llm


def test_timeout_misconfiguration_check():
    """Verify timeout misconfiguration detection when stage timeouts exceed pipeline timeout."""
    # Default settings: 20 + 30 + 10 = 60 < 90 -> no warning
    assert settings.check_timeout_misconfiguration() is None

    # Misconfigured: 50s ingestion + 40s LLM + 10s FinBERT = 100s >= 90s
    bad_settings = Settings(
        INGESTION_TIMEOUT_SECONDS=50.0,
        LLM_TIMEOUT_SECONDS=40.0,
        PIPELINE_TIMEOUT_SECONDS=90,
    )
    warning = bad_settings.check_timeout_misconfiguration()
    assert warning is not None
    assert "Pipeline timeout misconfiguration" in warning
    assert "100.0s" in warning


def test_env_example_matches_all_settings_fields():
    """Verify every field defined in Settings class is listed in .env.example with matching default."""
    env_example_path = BASE_DIR / ".env.example"
    assert env_example_path.exists()

    env_vars: dict[str, str] = {}
    with open(env_example_path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                k, v = stripped.split("=", 1)
                env_vars[k.strip()] = v.strip()

    for field_name, field_info in Settings.model_fields.items():
        assert field_name in env_vars, f"Field '{field_name}' in Settings is missing from .env.example"
        raw_val = env_vars[field_name]
        default_val = field_info.default

        if field_name == "DATABASE_URL":
            # In .env.example it is sqlite:///./data/sentiment.db
            assert raw_val == "sqlite:///./data/sentiment.db"
        elif field_name == "MODEL_PRICING":
            # Model pricing can default to empty json override in .env.example
            assert raw_val == "{}"
        elif isinstance(default_val, bool):
            assert (raw_val.lower() == "true") == default_val
        elif isinstance(default_val, int):
            assert int(raw_val) == default_val
        elif isinstance(default_val, float):
            assert float(raw_val) == default_val
        elif isinstance(default_val, (list, dict)):
            parsed = json.loads(raw_val) if raw_val else ([] if isinstance(default_val, list) else {})
            assert parsed == default_val
        elif default_val is None:
            assert raw_val == "" or raw_val.lower() == "none"
        else:
            assert raw_val == str(default_val)


def test_app_main_module_runner():
    """Verify python -m app entrypoint launches uvicorn with configured host, port, and proxy settings."""
    from app.__main__ import main as app_main

    with patch("uvicorn.run") as mock_uvicorn_run:
        app_main()
        mock_uvicorn_run.assert_called_once_with(
            "app.main:app",
            host=settings.APP_HOST,
            port=settings.APP_PORT,
            workers=1,
            proxy_headers=settings.TRUST_PROXY_HEADERS,
            forwarded_allow_ips=None,
            log_level=settings.LOG_LEVEL.lower(),
        )
