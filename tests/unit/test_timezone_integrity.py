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


def test_retrieved_at_utc_and_session_window_round_trip(db_session):
    """Verify ScoredArticle.retrieved_at_utc preservation and SessionWindow rebuild (Finding L4)."""
    from app.core.enums import AssetType, DecisionVerdict, ProviderType, SessionType
    from app.core.models import AnalysisResult, PipelineMetrics, PipelineRationale, ScoredArticle
    from app.core.session_window import SessionWindow
    from app.db.repository import SentimentRepository

    ingested_time = datetime(2026, 10, 14, 13, 15, 0, tzinfo=timezone.utc)
    published_time = datetime(2026, 10, 14, 13, 0, 0, tzinfo=timezone.utc)
    run_time = datetime(2026, 10, 14, 15, 0, 0, tzinfo=timezone.utc)
    start_time = datetime(2026, 10, 13, 20, 0, 0, tzinfo=timezone.utc)

    session = SessionWindow(
        market_timezone="America/New_York",
        session_type=SessionType.REGULAR_HOURS,
        is_market_open=True,
        window_start_utc=start_time,
        window_start_et=start_time.astimezone(ZoneInfo("America/New_York")),
        window_end_utc=run_time,
        window_end_et=run_time.astimezone(ZoneInfo("America/New_York")),
        window_duration_hours=19.0,
        run_timestamp_utc=run_time,
        run_timestamp_et=run_time.astimezone(ZoneInfo("America/New_York")),
    )

    art = ScoredArticle(
        article_id="art_l4_test",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_publisher="reuters.com",
        canonical_url="https://reuters.com/article/1",
        title="Test Headline",
        published_at_utc=published_time,
        retrieved_at_utc=ingested_time,
        lead_text="Test snippet",
        finbert_positive=0.9,
        finbert_negative=0.05,
        finbert_neutral=0.05,
        finbert_directional_score=0.85,
        finbert_confidence=0.9,
        is_llm_catalyst=False,
    )

    result = AnalysisResult(
        run_id="run_l4_test",
        ticker="AAPL",
        company_name="Apple Inc.",
        asset_type=AssetType.EQUITY,
        session=session,
        decision=DecisionVerdict.BUY,
        decision_confidence=0.85,
        sentiment_score=0.85,
        evidence_quality=0.9,
        disclaimer="Research Only",
        pipeline_mode="DETERMINISTIC_FINBERT_ONLY",
        cache_status="MISS",
        data_status="OK",
        articles=[art],
        metrics=PipelineMetrics(
            total_sources=1,
            distinct_publishers=1,
            distinct_clusters=1,
            articles_ingested=1,
            articles_retained=1,
            articles_excluded_total=0,
            articles_deduplicated=0,
            articles_scored_local=1,
            articles_sent_to_llm=0,
            completion_tokens=0,
            prompt_tokens=0,
            estimated_cost_usd=0.0,
            excluded_missing_timestamp=0,
            excluded_out_of_window=0,
            stage_latencies={},
            total_latency_ms=50.0,
        ),
        rationale=PipelineRationale(
            summary="Strong bullish signals",
            observed_facts=[],
            inferences=[],
        ),
        model_versions={},
        config_version="v2",
    )

    # Save to database
    SentimentRepository.save_analysis_run(db_session, result, cache_key="ckey_l4_test")

    # Read back from database
    loaded = SentimentRepository.get_analysis_run(db_session, "run_l4_test")
    assert loaded is not None

    # Verify retrieved_at_utc was preserved and not overwritten with datetime.now()
    assert len(loaded.articles) == 1
    loaded_art = loaded.articles[0]
    assert loaded_art.retrieved_at_utc == ingested_time
    assert loaded_art.published_at_utc == published_time

    # Verify session window was rebuilt from stored columns without re-evaluating calendar
    assert loaded.session.session_type == SessionType.REGULAR_HOURS
    assert loaded.session.window_start_utc == start_time
    assert loaded.session.window_end_utc == run_time
    assert loaded.session.run_timestamp_utc == run_time
    assert loaded.session.window_duration_hours == 19.0
    assert loaded.session.is_market_open is True

