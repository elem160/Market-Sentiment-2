import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.enums import ExclusionReason
from app.cli import main as cli_main
from app.config import settings
from app.core.models import Asset, IngestedArticle
from app.db.database import Base
from app.db.models import AnalysisJobDB, AnalysisRunDB, ArticleEvidenceDB, ObservedFactDB
from app.services.deduplication_service import DeduplicationService
from app.services.maintenance import (
    delete_expired_jobs,
    delete_old_analysis_runs,
    run_maintenance,
)
from app.services.relevance import RelevanceMatcher


@pytest.fixture
def test_db_session():
    """Create an isolated SQLite in-memory database session with schema for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session, TestingSession
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_delete_expired_jobs(test_db_session):
    db, _ = test_db_session
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Past expired job
    expired_job = AnalysisJobDB(
        id=str(uuid.uuid4()),
        ticker="AAPL",
        status="FAILED",
        stage="COMPLETED",
        progress_pct=1.0,
        expires_at=now - timedelta(hours=2),
    )
    # 2. Future job
    active_job = AnalysisJobDB(
        id=str(uuid.uuid4()),
        ticker="MSFT",
        status="PROCESSING",
        stage="FINBERT_SCORING",
        progress_pct=0.7,
        expires_at=now + timedelta(hours=1),
    )
    db.add_all([expired_job, active_job])
    db.commit()

    deleted = delete_expired_jobs(db, now=now)
    assert deleted == 1

    remaining = db.query(AnalysisJobDB).all()
    assert len(remaining) == 1
    assert remaining[0].id == active_job.id


def test_delete_old_analysis_runs_and_cascade(test_db_session):
    db, _ = test_db_session
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)

    # Old run (40 days old)
    old_run = AnalysisRunDB(
        id=str(uuid.uuid4()),
        ticker="NVDA",
        company_name="Nvidia Corp",
        asset_type="EQUITY",
        session_type="IN_SESSION",
        cache_key="key_old",
        window_start_utc=now - timedelta(days=41),
        window_end_utc=now - timedelta(days=40),
        run_timestamp_utc=now - timedelta(days=40),
        created_at=now - timedelta(days=40),
        decision="BUY",
        sentiment_score=0.8,
        decision_confidence=0.9,
        evidence_quality=0.85,
        rationale_summary="Old rationale",
        pipeline_mode="DETERMINISTIC_FINBERT_ONLY",
        config_version="v1",
        cache_status="MISS",
        llm_cost_usd=0.01,
    )
    # Recent run (5 days old)
    recent_run = AnalysisRunDB(
        id=str(uuid.uuid4()),
        ticker="NVDA",
        company_name="Nvidia Corp",
        asset_type="EQUITY",
        session_type="IN_SESSION",
        cache_key="key_recent",
        window_start_utc=now - timedelta(days=6),
        window_end_utc=now - timedelta(days=5),
        run_timestamp_utc=now - timedelta(days=5),
        created_at=now - timedelta(days=5),
        decision="HOLD",
        sentiment_score=0.0,
        decision_confidence=0.5,
        evidence_quality=0.6,
        rationale_summary="Recent rationale",
        pipeline_mode="DETERMINISTIC_FINBERT_ONLY",
        config_version="v1",
        cache_status="MISS",
        llm_cost_usd=0.0,
    )
    db.add_all([old_run, recent_run])
    db.commit()

    # Add evidence and facts for both runs
    old_evidence = ArticleEvidenceDB(
        id="ev_old_1",
        article_id="art_old_1",
        run_id=old_run.id,
        provider="yfinance",
        source_name="Reuters",
        canonical_publisher="Reuters",
        canonical_url="https://reuters.com/nvda-old",
        title="Old NVDA Title",
        retrieved_at_utc=now - timedelta(days=40),
        lead_text="Old lead text",
        finbert_positive=0.9,
        finbert_negative=0.05,
        finbert_neutral=0.05,
        finbert_directional_score=0.85,
        finbert_confidence=0.9,
    )
    recent_evidence = ArticleEvidenceDB(
        id="ev_recent_1",
        article_id="art_recent_1",
        run_id=recent_run.id,
        provider="yfinance",
        source_name="Bloomberg",
        canonical_publisher="Bloomberg",
        canonical_url="https://bloomberg.com/nvda-recent",
        title="Recent NVDA Title",
        retrieved_at_utc=now - timedelta(days=5),
        lead_text="Recent lead text",
        finbert_positive=0.1,
        finbert_negative=0.1,
        finbert_neutral=0.8,
        finbert_directional_score=0.0,
        finbert_confidence=0.8,
    )
    old_fact = ObservedFactDB(
        id="fact_old_1",
        run_id=old_run.id,
        statement="Old Nvidia Fact",
        cited_article_id="art_old_1",
        catalyst_category="REGULATORY",
        impact="POSITIVE",
    )
    recent_fact = ObservedFactDB(
        id="fact_recent_1",
        run_id=recent_run.id,
        statement="Recent Nvidia Fact",
        cited_article_id="art_recent_1",
        catalyst_category="REGULATORY",
        impact="NEUTRAL",
    )
    db.add_all([old_evidence, recent_evidence, old_fact, recent_fact])
    db.commit()

    # Purge runs older than 30 days
    purged_count = delete_old_analysis_runs(db, retention_days=30, now=now)
    assert purged_count == 1

    # Old run and cascaded items must be deleted
    assert db.query(AnalysisRunDB).filter(AnalysisRunDB.id == old_run.id).first() is None
    assert db.query(ArticleEvidenceDB).filter(ArticleEvidenceDB.run_id == old_run.id).first() is None
    assert db.query(ObservedFactDB).filter(ObservedFactDB.run_id == old_run.id).first() is None

    # Recent run and cascaded items must remain
    assert db.query(AnalysisRunDB).filter(AnalysisRunDB.id == recent_run.id).first() is not None
    assert db.query(ArticleEvidenceDB).filter(ArticleEvidenceDB.run_id == recent_run.id).first() is not None
    assert db.query(ObservedFactDB).filter(ObservedFactDB.run_id == recent_run.id).first() is not None


def test_run_maintenance_end_to_end(test_db_session):
    _, testing_session_factory = test_db_session
    now = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)

    # Seed an expired job in DB
    seed_db = testing_session_factory()
    job = AnalysisJobDB(
        id=str(uuid.uuid4()),
        ticker="GOOGL",
        status="COMPLETED",
        stage="DONE",
        progress_pct=1.0,
        expires_at=now - timedelta(days=1),
    )
    seed_db.add(job)
    seed_db.commit()
    seed_db.close()

    result = run_maintenance(
        session_factory=testing_session_factory,
        retention_days=30,
        vacuum=False,
        now=now,
    )
    assert result["expired_jobs_deleted"] == 1
    assert result["old_runs_deleted"] == 0
    assert result["vacuumed"] is False


def test_cli_maintenance_command(capsys):
    test_args = ["cli.py", "maintenance", "--retention-days", "45"]
    with patch("sys.argv", test_args):
        with patch("app.cli.run_maintenance") as mock_maint:
            mock_maint.return_value = {
                "expired_jobs_deleted": 3,
                "old_runs_deleted": 2,
                "vacuumed": False,
            }
            cli_main()
            mock_maint.assert_called_once_with(retention_days=45, vacuum=False)

    captured = capsys.readouterr()
    assert "expired jobs deleted: 3" in captured.out
    assert "old runs deleted: 2" in captured.out


def test_deduplication_sample_capping_and_counts():
    asset = Asset(ticker="AAPL", company_name="Apple Inc.", exchange="NASDAQ")
    matcher = RelevanceMatcher.for_asset(asset)

    # 1. Test relevance exclusion sample capping: create 35 irrelevant articles
    now = datetime.now(timezone.utc)
    irrelevant_articles = [
        IngestedArticle(
            article_id=f"irrel_{i}",
            provider="GOOGLE_RSS_AGGREGATOR",
            source_name="MarketNews",
            canonical_url=f"https://example.com/other_{i}",
            title=f"Unrelated commodity report {i}",
            summary="Wheat and oil prices fluctuate today.",
            published_at_utc=now,
            retrieved_at_utc=now,
        )
        for i in range(35)
    ]

    dedup_res = DeduplicationService.process_and_deduplicate(
        irrelevant_articles,
        matcher=matcher,
        max_samples_per_reason=20,
    )
    retained, sample_excluded, cluster_map = dedup_res

    assert len(retained) == 0
    assert len(sample_excluded) == 20
    assert dedup_res.counts[ExclusionReason.INSUFFICIENT_ENTITY_RELEVANCE.value] == 35

    # 2. Test duplicate syndication sample capping: create 1 original + 25 identical duplicates
    original = IngestedArticle(
        article_id="orig_1",
        provider="GOOGLE_RSS_AGGREGATOR",
        source_name="Reuters",
        canonical_url="https://reuters.com/aapl-story",
        title="Apple launches revolutionary new M5 processor for Mac lineup",
        summary="Apple Inc announced today the new M5 chip with breakthrough performance.",
        published_at_utc=now - timedelta(minutes=10),
        retrieved_at_utc=now,
    )
    duplicates = [
        IngestedArticle(
            article_id=f"dup_{i}",
            provider="GOOGLE_RSS_AGGREGATOR",
            source_name=f"Syndicator_{i}",
            canonical_url=f"https://syndicate_{i}.com/aapl-story",
            title="Apple launches revolutionary new M5 processor for Mac lineup",
            summary="Apple Inc announced today the new M5 chip with breakthrough performance.",
            published_at_utc=now - timedelta(minutes=5),
            retrieved_at_utc=now,
        )
        for i in range(25)
    ]

    dedup_res_dup = DeduplicationService.process_and_deduplicate(
        [original] + duplicates,
        matcher=matcher,
        max_samples_per_reason=20,
    )
    retained_dup, sample_excluded_dup, _ = dedup_res_dup

    assert len(retained_dup) == 1
    assert retained_dup[0].article_id == "orig_1"
    # Duplicates capped at 20 samples
    assert len(sample_excluded_dup) == 20
    assert dedup_res_dup.counts[ExclusionReason.DUPLICATE_SYNDICATION.value] == 25

    # 3. Test capacity limit sample capping: max_articles=2 with 30 distinct relevant articles
    distinct_words = [
        "revenue", "earnings", "dividend", "headquarters", "supplier",
        "battery", "display", "processor", "software", "retail",
        "workforce", "acquisition", "datacenter", "patent", "antitrust",
        "expansion", "executive", "boardroom", "subsidiary", "logistics",
        "keynote", "lawsuit", "investor", "forecast", "partnership",
        "factory", "assembly", "chipset", "cloud", "security"
    ]
    distinct_articles = [
        IngestedArticle(
            article_id=f"art_unique_{i}",
            provider="GOOGLE_RSS_AGGREGATOR",
            source_name="Bloomberg",
            canonical_url=f"https://bloomberg.com/aapl-distinct-{i}",
            title=f"Apple {distinct_words[i]} development update today",
            summary=f"Apple Inc shares react to distinct quarterly {distinct_words[i]} news item.",
            published_at_utc=now - timedelta(minutes=i),
            retrieved_at_utc=now,
        )
        for i in range(30)
    ]
    dedup_res_cap = DeduplicationService.process_and_deduplicate(
        distinct_articles,
        matcher=matcher,
        max_articles=2,
        max_samples_per_reason=20,
    )
    retained_cap, sample_excluded_cap, _ = dedup_res_cap

    assert len(retained_cap) == 2
    # Capacity limit excluded 28 articles, but sample_excluded capped at 20
    assert len(sample_excluded_cap) == 20
    assert dedup_res_cap.counts[ExclusionReason.CAPACITY_LIMIT.value] == 28
