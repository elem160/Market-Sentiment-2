from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.db.models import AnalysisRunDB
from app.db.types import UTCDateTime


def test_utc_datetime_type_decorator_rejects_naive():
    decorator = UTCDateTime()
    naive_dt = datetime(2026, 10, 14, 15, 0, 0)
    with pytest.raises(ValueError, match="Naive datetime rejected"):
        decorator.process_bind_param(naive_dt, None)


def test_utc_datetime_type_decorator_normalizes_to_utc():
    decorator = UTCDateTime()
    # 11:00 AM New York time (EDT is UTC-4) -> 15:00 UTC
    ny_tz = ZoneInfo("America/New_York")
    ny_dt = datetime(2026, 10, 14, 11, 0, 0, tzinfo=ny_tz)
    bound = decorator.process_bind_param(ny_dt, None)
    assert bound is not None
    assert bound.tzinfo is None  # stored as naive UTC for SQLite
    assert bound.hour == 15

    # Reading result attaches UTC
    result = decorator.process_result_value(bound, None)
    assert result is not None
    assert result.tzinfo == timezone.utc
    assert result.hour == 15


@pytest.mark.asyncio
async def test_history_endpoint_returns_z_timestamp_and_metadata(async_client, db_session):
    now_utc = datetime(2026, 10, 14, 15, 30, 0, tzinfo=timezone.utc)
    run = AnalysisRunDB(
        id="run_tz_test",
        ticker="AAPL",
        company_name="Apple Inc.",
        asset_type="EQUITY",
        session_type="REGULAR_HOURS",
        cache_key="ckey_tz",
        window_start_utc=now_utc - timedelta(hours=4),
        window_end_utc=now_utc,
        run_timestamp_utc=now_utc,
        decision="BUY",
        sentiment_score=0.75,
        decision_confidence=0.85,
        evidence_quality=0.90,
        rationale_summary="Positive sentiment",
        inferences_json="[]",
        pipeline_mode="DETERMINISTIC_FINBERT_ONLY",
        model_versions_json="{}",
        config_version="v1",
        provider_outcomes_json="{}",
        cache_status="MISS",
        metrics_json="{}",
        warnings_json="[]",
        data_status="OK",
        created_at=now_utc,
    )
    db_session.add(run)
    db_session.commit()

    resp = await async_client.get("/api/v1/history?limit=5")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 1
    found = next((item for item in items if item["run_id"] == "run_tz_test"), None)
    assert found is not None
    assert found["run_timestamp_utc"].endswith("Z")
    assert found["asset_type"] == "EQUITY"
    assert found["data_status"] == "OK"
