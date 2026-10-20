from datetime import datetime, timedelta
from app.services.aggregator_service import AggregatorService
from app.core.models import ScoredArticle, ObservedFact
from app.core.enums import (
    ProviderType,
    DecisionVerdict,
    CatalystCategory,
    DirectionalPolarity,
    PipelineMode,
)
from app.core.session_window import compute_session_window


def create_mock_scored_article(
    art_id: str,
    publisher: str,
    score: float,
    confidence: float,
    now: datetime,
    hours_ago: float = 2.0,
    cluster_id: str | None = None,
) -> ScoredArticle:
    pub_dt = now - timedelta(hours=hours_ago)
    return ScoredArticle(
        article_id=art_id,
        provider=ProviderType.YFINANCE,
        source_name=publisher,
        canonical_publisher=publisher,
        canonical_url=f"https://{publisher.lower().replace(' ', '')}.com/{art_id}",
        title=f"Sample headline {art_id} from {publisher}",
        published_at_utc=pub_dt,
        lead_text=f"Sample text for {art_id}",
        finbert_positive=max(0.0, score) if score > 0 else 0.05,
        finbert_negative=abs(score) if score < 0 else 0.05,
        finbert_neutral=0.1,
        finbert_directional_score=score,
        finbert_confidence=confidence,
        is_llm_catalyst=True,
        catalyst_category=CatalystCategory.EARNINGS,
        exclusion_reason=None,
        final_weight=confidence * 1.25,
        cluster_id=cluster_id or f"clust_{art_id}",
    )


def test_sparse_evidence_mandates_hold(frozen_now):
    session = compute_session_window(frozen_now)
    # Single article only
    art = create_mock_scored_article("1", "Reuters", 0.85, 0.90, frozen_now)

    decision, confidence, score, quality, rationale, warnings = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [art], [], ""
    )

    assert decision == DecisionVerdict.HOLD
    assert "Sparse evidence" in rationale.summary or "Insufficient" in rationale.summary


def test_single_publisher_forces_hold_with_insufficient_corroboration(frozen_now):
    session = compute_session_window(frozen_now)
    # Two articles, both from the same publisher (Reuters)
    art1 = create_mock_scored_article("1", "Reuters", 0.80, 0.88, frozen_now, cluster_id="c1")
    art2 = create_mock_scored_article("2", "Reuters", 0.75, 0.85, frozen_now, cluster_id="c1")

    decision, confidence, score, quality, rationale, warnings = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [art1, art2], [], ""
    )

    # Corroboration requirement forces HOLD when < 2 distinct publishers
    assert decision == DecisionVerdict.HOLD
    assert any("corroboration" in w.lower() for w in warnings)


def test_neutral_articles_do_not_dilute_positive_buy(frozen_now):
    session = compute_session_window(frozen_now)
    # Two positive articles and ten neutral articles
    pos1 = create_mock_scored_article("p1", "Reuters", 0.80, 0.90, frozen_now, cluster_id="c1")
    pos2 = create_mock_scored_article("p2", "CNBC", 0.75, 0.85, frozen_now, cluster_id="c2")
    neutrals = [
        create_mock_scored_article(f"n{i}", "Yahoo Finance", 0.0, 0.10, frozen_now, cluster_id=f"cn{i}")
        for i in range(10)
    ]

    decision, confidence, score, quality, rationale, warnings = AggregatorService.aggregate_and_decide(
        "NVDA", "Nvidia Corp.", session, [pos1, pos2] + neutrals, [], ""
    )

    # Neutrals must NOT dilute directional score into HOLD!
    assert decision == DecisionVerdict.BUY
    assert score >= 0.70


def test_multi_publisher_positive_triggers_buy(frozen_now):
    session = compute_session_window(frozen_now)
    # Two articles from TWO distinct publishers (Reuters and CNBC) with distinct clusters
    art1 = create_mock_scored_article("1", "Reuters", 0.80, 0.90, frozen_now, cluster_id="c1")
    art2 = create_mock_scored_article("2", "CNBC", 0.75, 0.85, frozen_now, cluster_id="c2")

    fact1 = ObservedFact(
        statement="Revenue surged 15% exceeding consensus.",
        cited_article_id="1",
        catalyst_category=CatalystCategory.EARNINGS,
        impact=DirectionalPolarity.POSITIVE,
    )

    decision, confidence, score, quality, rationale, warnings = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [art1, art2], [fact1], "Strong earnings momentum confirmed."
    )

    assert decision == DecisionVerdict.BUY
    assert score >= 0.35
    assert confidence >= 0.40
    assert len(rationale.observed_facts) == 1


def test_multi_publisher_negative_triggers_sell(frozen_now):
    session = compute_session_window(frozen_now)
    # Two negative articles from Bloomberg and Wall Street Journal
    art1 = create_mock_scored_article("1", "Bloomberg", -0.75, 0.85, frozen_now, cluster_id="c1")
    art2 = create_mock_scored_article("2", "Wall Street Journal", -0.80, 0.90, frozen_now, cluster_id="c2")

    decision, confidence, score, quality, rationale, warnings = AggregatorService.aggregate_and_decide(
        "NVDA", "Nvidia Corp.", session, [art1, art2], [], ""
    )

    assert decision == DecisionVerdict.SELL
    assert score <= -0.35
    assert confidence >= 0.40


def test_conflicting_evidence_forces_hold(frozen_now):
    session = compute_session_window(frozen_now)
    # One strong positive from Reuters, one strong negative from Bloomberg
    art1 = create_mock_scored_article("1", "Reuters", 0.85, 0.90, frozen_now, cluster_id="c1")
    art2 = create_mock_scored_article("2", "Bloomberg", -0.85, 0.90, frozen_now, cluster_id="c2")
    art3 = create_mock_scored_article("3", "CNBC", 0.10, 0.50, frozen_now, cluster_id="c3")

    decision, confidence, score, quality, rationale, warnings = AggregatorService.aggregate_and_decide(
        "TSLA", "Tesla Inc.", session, [art1, art2, art3], [], ""
    )

    assert decision == DecisionVerdict.HOLD
    assert "Conflicting" in rationale.summary


def test_deterministic_finbert_only_confidence_ceiling(frozen_now):
    session = compute_session_window(frozen_now)
    art1 = create_mock_scored_article("1", "Reuters", 0.95, 0.95, frozen_now, cluster_id="c1")
    art2 = create_mock_scored_article("2", "CNBC", 0.95, 0.95, frozen_now, cluster_id="c2")

    # In classifier-only mode, confidence must be capped at 0.60
    decision, confidence, score, quality, rationale, warnings = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [art1, art2], [], "", pipeline_mode=PipelineMode.DETERMINISTIC_FINBERT_ONLY
    )

    assert confidence <= 0.60
    assert any("LLM synthesis unavailable" in w for w in warnings)
