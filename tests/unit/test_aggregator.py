from datetime import datetime, timedelta
from app.services.aggregator_service import AggregatorService
from app.core.models import ScoredArticle, ObservedFact
from app.core.enums import (
    ProviderType,
    DecisionVerdict,
    CatalystCategory,
    DirectionalPolarity,
    PipelineMode,
    HoldReason,
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
    publisher_inferred: bool = False,
) -> ScoredArticle:
    pub_dt = now - timedelta(hours=hours_ago)
    return ScoredArticle(
        article_id=art_id,
        provider=ProviderType.YFINANCE,
        source_name=publisher,
        canonical_publisher=publisher,
        publisher_inferred=publisher_inferred,
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
    assert confidence == 0.0
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


def test_two_positive_single_publisher_vs_one_negative_forces_hold(frozen_now):
    session = compute_session_window(frozen_now)
    # 2 positive articles from Reuters, 1 negative article from CNBC
    # Ratio = 2 / 1 = 2.0 >= 1.5, score >= 0.20, but pos_publishers has only Reuters (len=1 < 2)
    pos1 = create_mock_scored_article("p1", "Reuters", 0.80, 0.90, frozen_now, cluster_id="c1")
    pos2 = create_mock_scored_article("p2", "Reuters", 0.75, 0.85, frozen_now, cluster_id="c1")
    neg1 = create_mock_scored_article("n1", "CNBC", -0.70, 0.85, frozen_now, cluster_id="c2")

    res = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [pos1, pos2, neg1], [], ""
    )

    assert res.decision == DecisionVerdict.HOLD
    assert res.hold_reason == HoldReason.INSUFFICIENT_CORROBORATION
    assert res.publishers_positive == 1
    assert res.publishers_negative == 1
    assert res.supporting_publishers == 0
    assert any("INSUFFICIENT_CORROBORATION" in w for w in res.warnings)


def test_two_positive_distinct_publishers_vs_one_negative_triggers_buy(frozen_now):
    session = compute_session_window(frozen_now)
    # 1 pos Reuters + 1 pos CNBC + 1 neg WSJ -> BUY (2 pos publishers corroborate)
    pos1 = create_mock_scored_article("p1", "Reuters", 0.85, 0.90, frozen_now, cluster_id="c1")
    pos2 = create_mock_scored_article("p2", "CNBC", 0.80, 0.85, frozen_now, cluster_id="c2")
    neg1 = create_mock_scored_article("n1", "Wall Street Journal", -0.70, 0.85, frozen_now, cluster_id="c3")

    res = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [pos1, pos2, neg1], [], ""
    )

    assert res.decision == DecisionVerdict.BUY
    assert res.hold_reason is None
    assert res.publishers_positive == 2
    assert res.publishers_negative == 1
    assert res.supporting_publishers == 2


def test_only_inferred_publishers_forces_hold(frozen_now):
    session = compute_session_window(frozen_now)
    # 2 positive articles from Reuters and CNBC, but publisher_inferred=True
    pos1 = create_mock_scored_article("p1", "Reuters", 0.85, 0.90, frozen_now, cluster_id="c1", publisher_inferred=True)
    pos2 = create_mock_scored_article("p2", "CNBC", 0.80, 0.85, frozen_now, cluster_id="c2", publisher_inferred=True)

    res = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [pos1, pos2], [], ""
    )

    assert res.decision == DecisionVerdict.HOLD
    assert res.hold_reason == HoldReason.INSUFFICIENT_CORROBORATION
    assert res.publishers_positive == 0
    assert res.supporting_publishers == 0


def test_aggregator_publishers_ignored_in_corroboration(frozen_now):
    session = compute_session_window(frozen_now)
    # 1 positive from Reuters, 1 positive from Unknown Aggregator
    pos1 = create_mock_scored_article("p1", "Reuters", 0.85, 0.90, frozen_now, cluster_id="c1")
    pos2 = create_mock_scored_article("p2", "Unknown Aggregator", 0.80, 0.85, frozen_now, cluster_id="c2")

    res = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [pos1, pos2], [], ""
    )

    assert res.decision == DecisionVerdict.HOLD
    assert res.hold_reason == HoldReason.INSUFFICIENT_CORROBORATION
    assert res.publishers_positive == 1
    assert res.supporting_publishers == 0


def test_hybrid_confidence_ceiling_with_supporting_catalyst(frozen_now):
    """When LLM confirms supporting catalyst in verdict direction, ceiling reaches up to 0.95 (D6)."""
    session = compute_session_window(frozen_now)
    # High sentiment and high confidence from 2 distinct publishers
    art1 = create_mock_scored_article("1", "Reuters", 0.95, 0.95, frozen_now, cluster_id="c1")
    art2 = create_mock_scored_article("2", "CNBC", 0.95, 0.95, frozen_now, cluster_id="c2")
    fact_pos = ObservedFact(
        statement="Record revenue growth",
        cited_article_id="1",
        catalyst_category=CatalystCategory.EARNINGS,
        impact=DirectionalPolarity.POSITIVE,
    )

    res = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [art1, art2], [fact_pos], "Strong catalysts",
        pipeline_mode=PipelineMode.HYBRID_FINBERT_LLM
    )

    assert res.decision == DecisionVerdict.BUY
    # With supporting positive catalyst confirmed by LLM, confidence can exceed 0.60 (up to 0.95)
    assert res.decision_confidence > 0.60
    assert res.decision_confidence <= 0.95


def test_hybrid_confidence_ceiling_without_supporting_catalyst(frozen_now):
    """When LLM does not confirm any supporting catalyst in verdict direction, ceiling is 0.60 (D6)."""
    session = compute_session_window(frozen_now)
    art1 = create_mock_scored_article("1", "Reuters", 0.95, 0.95, frozen_now, cluster_id="c1")
    art2 = create_mock_scored_article("2", "CNBC", 0.95, 0.95, frozen_now, cluster_id="c2")

    # In HYBRID mode but with NO observed facts confirmed
    res = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [art1, art2], [], "",
        pipeline_mode=PipelineMode.HYBRID_FINBERT_LLM
    )

    assert res.decision == DecisionVerdict.BUY
    # Without supporting catalyst, ceiling is 0.60 even in HYBRID mode
    assert res.decision_confidence <= 0.60


def test_hold_verdict_confidence_capped_at_060(frozen_now):
    """HOLD verdict has no directional supporting catalyst, so confidence is capped at 0.60 (D6)."""
    session = compute_session_window(frozen_now)
    # 2 pos, 2 neg -> conflicting
    art1 = create_mock_scored_article("1", "Reuters", 0.90, 0.95, frozen_now, cluster_id="c1")
    art2 = create_mock_scored_article("2", "CNBC", 0.90, 0.95, frozen_now, cluster_id="c2")
    art3 = create_mock_scored_article("3", "Bloomberg", -0.90, 0.95, frozen_now, cluster_id="c3")
    art4 = create_mock_scored_article("4", "WSJ", -0.90, 0.95, frozen_now, cluster_id="c4")

    res = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [art1, art2, art3, art4], [], "",
        pipeline_mode=PipelineMode.HYBRID_FINBERT_LLM
    )

    assert res.decision == DecisionVerdict.HOLD
    assert res.hold_reason == HoldReason.CONFLICTING
    assert res.decision_confidence <= 0.60


def test_neutral_sentiment_hold_reason(frozen_now):
    """Balanced sentiment within neutral corridor yields NEUTRAL hold reason."""
    session = compute_session_window(frozen_now)
    # 2 weakly positive articles above DIRECTIONAL_THRESHOLD (0.15) but below buy threshold (0.20)
    art1 = create_mock_scored_article("1", "Reuters", 0.16, 0.50, frozen_now, cluster_id="c1")
    art2 = create_mock_scored_article("2", "CNBC", 0.17, 0.50, frozen_now, cluster_id="c2")

    res = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [art1, art2], [], ""
    )

    assert res.decision == DecisionVerdict.HOLD
    assert res.hold_reason == HoldReason.NEUTRAL


def test_sell_corroboration_with_inferred_publishers(frozen_now):
    """SELL requires >= 2 distinct non-inferred publishers; inferred negative publisher forces HOLD."""
    session = compute_session_window(frozen_now)
    # 1 negative from Bloomberg (authoritative), 1 negative from Reuters with publisher_inferred=True
    art1 = create_mock_scored_article("1", "Bloomberg", -0.80, 0.90, frozen_now, cluster_id="c1", publisher_inferred=False)
    art2 = create_mock_scored_article("2", "Reuters", -0.75, 0.85, frozen_now, cluster_id="c2", publisher_inferred=True)

    res = AggregatorService.aggregate_and_decide("AAPL", "Apple Inc.", session, [art1, art2], [], "")
    assert res.decision == DecisionVerdict.HOLD
    assert res.hold_reason == HoldReason.INSUFFICIENT_CORROBORATION
    assert res.publishers_negative == 1  # Only Bloomberg is eligible
    assert res.supporting_publishers == 0


def test_sell_with_mixed_positive_negative_publishers(frozen_now):
    """SELL with 2 negative eligible publishers and 1 positive eligible publisher."""
    session = compute_session_window(frozen_now)
    neg1 = create_mock_scored_article("n1", "Bloomberg", -0.85, 0.90, frozen_now, cluster_id="c1")
    neg2 = create_mock_scored_article("n2", "Wall Street Journal", -0.80, 0.85, frozen_now, cluster_id="c2")
    pos1 = create_mock_scored_article("p1", "Reuters", 0.70, 0.80, frozen_now, cluster_id="c3")

    res = AggregatorService.aggregate_and_decide("AAPL", "Apple Inc.", session, [neg1, neg2, pos1], [], "")
    assert res.decision == DecisionVerdict.SELL
    assert res.hold_reason is None
    assert res.publishers_negative == 2
    assert res.publishers_positive == 1
    assert res.supporting_publishers == 2


def test_conflicting_mixed_publishers_has_zero_supporting_publishers(frozen_now):
    """Mixed 1 positive and 1 negative eligible publisher yields CONFLICTING HOLD with 0 supporting publishers."""
    session = compute_session_window(frozen_now)
    pos = create_mock_scored_article("p1", "Reuters", 0.85, 0.90, frozen_now, cluster_id="c1")
    neg = create_mock_scored_article("n1", "Bloomberg", -0.85, 0.90, frozen_now, cluster_id="c2")

    res = AggregatorService.aggregate_and_decide("AAPL", "Apple Inc.", session, [pos, neg], [], "")
    assert res.decision == DecisionVerdict.HOLD
    assert res.hold_reason == HoldReason.CONFLICTING
    assert res.publishers_positive == 1
    assert res.publishers_negative == 1
    assert res.supporting_publishers == 0

