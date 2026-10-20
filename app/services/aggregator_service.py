import math
from datetime import datetime, timezone
from app.core.models import (
    ScoredArticle,
    ObservedFact,
    PipelineRationale,
    DecisionVerdict,
    PipelineMode,
)
from app.core.enums import HoldReason, DirectionalPolarity
from app.core.session_window import SessionWindow
from app.core.exceptions import FreshnessViolationException
from app.core.constants import DIRECTIONAL_THRESHOLD, DEFAULT_WEIGHT_FLOOR

# 14-hour half life for exponential recency decay
LAMBDA_DECAY = math.log(2.0) / 14.0


class AggregatorResult(tuple):
    """
    Subclasses tuple of 6 elements for 100% backward compatibility:
    (decision, decision_confidence, sentiment_score, evidence_quality, rationale, warnings)
    while exposing directional publisher counts and hold_reason as attributes.
    """
    def __new__(
        cls,
        decision: DecisionVerdict,
        decision_confidence: float,
        sentiment_score: float,
        evidence_quality: float,
        rationale: PipelineRationale,
        warnings: list[str],
        publishers_positive: int = 0,
        publishers_negative: int = 0,
        supporting_publishers: int = 0,
        hold_reason: HoldReason | None = None,
    ):
        instance = super().__new__(
            cls,
            (decision, decision_confidence, sentiment_score, evidence_quality, rationale, warnings),
        )
        instance.decision = decision
        instance.decision_confidence = decision_confidence
        instance.sentiment_score = sentiment_score
        instance.evidence_quality = evidence_quality
        instance.rationale = rationale
        instance.warnings = warnings
        instance.publishers_positive = publishers_positive
        instance.publishers_negative = publishers_negative
        instance.supporting_publishers = supporting_publishers
        instance.hold_reason = hold_reason
        return instance


class AggregatorService:
    @classmethod
    def aggregate_and_decide(
        cls,
        ticker: str,
        company_name: str,
        session: SessionWindow,
        articles: list[ScoredArticle],
        observed_facts: list[ObservedFact],
        llm_summary: str = "",
        pipeline_mode: PipelineMode = PipelineMode.HYBRID_FINBERT_LLM,
    ) -> AggregatorResult:
        """
        Calculates:
        - Exponential recency decay
        - Composite sentiment score S in [-1.0, 1.0] using effective weights
        - Evidence quality Q in [0.0, 1.0] using directional diversity factor
        - Decision confidence C in [0.0, 1.0]
        - Enforces directional corroboration (>= 2 eligible publishers on supporting side for BUY/SELL)
        - Heuristic decision matrix verdict
        - Plain-English rationale separating facts vs inferences
        
        Returns:
        AggregatorResult (unpacks as 6-tuple for backward compatibility)
        """
        warnings: list[str] = []
        if pipeline_mode == PipelineMode.DETERMINISTIC_FINBERT_ONLY:
            warnings.append("LLM synthesis unavailable: Result generated using local NLP classifier only (confidence capped at 0.60).")

        # 1. Filter valid non-excluded articles
        valid_articles = [a for a in articles if a.exclusion_reason is None]

        # 2. Defense-in-depth: enforce core invariant that all valid articles are strictly inside session window
        in_window_articles: list[ScoredArticle] = []
        for art in valid_articles:
            if art.published_at_utc is None or not session.is_timestamp_in_window(art.published_at_utc):
                ts_str = art.published_at_utc.isoformat() if art.published_at_utc else "None"
                raise FreshnessViolationException(
                    article_id=art.article_id,
                    timestamp_str=ts_str,
                    window_start=session.window_start_utc.isoformat(),
                    window_end=session.window_end_utc.isoformat(),
                )
            in_window_articles.append(art)

        # Check for zero news
        if len(in_window_articles) == 0:
            summary = f"No verifiable news found for {ticker} within the current trading session window."
            rationale = PipelineRationale(
                summary=summary,
                observed_facts=[],
                inferences=["Zero articles passed session window and entity relevance filters."],
            )
            return AggregatorResult(
                decision=DecisionVerdict.HOLD,
                decision_confidence=0.0,
                sentiment_score=0.0,
                evidence_quality=0.0,
                rationale=rationale,
                warnings=warnings + ["No current-day news available within the session window."],
                publishers_positive=0,
                publishers_negative=0,
                supporting_publishers=0,
                hold_reason=HoldReason.NO_NEWS,
            )

        # 3. Compute recency weights and directional tallies consistently (F-08, C-04)
        now_utc = session.run_timestamp_utc
        pos_count = 0
        neg_count = 0
        neu_count = 0

        pos_publishers: set[str] = set()
        neg_publishers: set[str] = set()
        valid_publishers: set[str] = set()
        valid_clusters: set[str] = set()

        directional_weighted_sum = 0.0
        directional_weight_sum = 0.0

        def _is_eligible_publisher(a: ScoredArticle) -> bool:
            return bool(
                a.canonical_publisher
                and a.canonical_publisher != "Unknown Aggregator"
                and not a.publisher_inferred
            )

        for art in in_window_articles:
            pub_utc = art.published_at_utc
            if pub_utc.tzinfo is None:
                pub_utc = pub_utc.replace(tzinfo=timezone.utc)
            delta_hours = max(0.0, (now_utc - pub_utc).total_seconds() / 3600.0)
            recency_decay = math.exp(-LAMBDA_DECAY * delta_hours)

            # Compute effective_weight once per article
            effective_weight = round(recency_decay * max(DEFAULT_WEIGHT_FLOOR, art.final_weight), 4)
            art.effective_weight = effective_weight
            art.age_hours = round(delta_hours, 2)

            # Skip articles whose effective weight is not positive
            if effective_weight <= 0.0:
                continue

            # Directional tally and scoring
            if art.finbert_directional_score >= DIRECTIONAL_THRESHOLD:
                pos_count += 1
                directional_weighted_sum += effective_weight * art.finbert_directional_score
                directional_weight_sum += effective_weight
                if _is_eligible_publisher(art):
                    pos_publishers.add(art.canonical_publisher)
                if art.canonical_publisher and art.canonical_publisher != "Unknown Aggregator":
                    valid_publishers.add(art.canonical_publisher)
                if art.cluster_id:
                    valid_clusters.add(art.cluster_id)
            elif art.finbert_directional_score <= -DIRECTIONAL_THRESHOLD:
                neg_count += 1
                directional_weighted_sum += effective_weight * art.finbert_directional_score
                directional_weight_sum += effective_weight
                if _is_eligible_publisher(art):
                    neg_publishers.add(art.canonical_publisher)
                if art.canonical_publisher and art.canonical_publisher != "Unknown Aggregator":
                    valid_publishers.add(art.canonical_publisher)
                if art.cluster_id:
                    valid_clusters.add(art.cluster_id)
            else:
                neu_count += 1

        # 4. Composite Sentiment Score S in [-1.0, 1.0] (computed from directional evidence)
        if directional_weight_sum > 0:
            sentiment_score = round(max(-1.0, min(1.0, directional_weighted_sum / directional_weight_sum)), 4)
        else:
            sentiment_score = 0.0

        # Determine preliminary candidate direction to calculate P_support
        directional_total = pos_count + neg_count
        is_buy_candidate = (
            pos_count >= 2
            and (neg_count == 0 or pos_count >= 1.5 * neg_count)
            and sentiment_score >= 0.20
        )
        is_sell_candidate = (
            neg_count >= 2
            and (pos_count == 0 or neg_count >= 1.5 * pos_count)
            and sentiment_score <= -0.20
        )

        if is_buy_candidate:
            p_support = len(pos_publishers)
        elif is_sell_candidate:
            p_support = len(neg_publishers)
        else:
            p_support = max(len(pos_publishers), len(neg_publishers))

        # 5. Evidence Quality Metric Q in [0.0, 1.0]
        distinct_pub_count = len(valid_publishers)
        distinct_cluster_count = len(valid_clusters)
        n_valid = pos_count + neg_count + neu_count

        volume_factor = min(1.0, max(0.3, directional_total / 3.0))
        if p_support == 0:
            diversity_factor = 0.5
        else:
            diversity_factor = 0.5 + 0.5 * min(1.0, p_support / 2.0)
        evidence_quality = round(min(1.0, max(0.1, volume_factor * diversity_factor)), 4)

        # 6. Evaluate Ratio-Based Decision Matrix & Publisher Corroboration (F-09, C-04)
        hold_reason: HoldReason | None = None

        # Rule A: Sparse Evidence (directional_total < 2)
        if directional_total < 2:
            decision = DecisionVerdict.HOLD
            hold_reason = HoldReason.SPARSE_EVIDENCE
            summary = f"HOLD: Insufficient directional headline volume for {ticker} ({directional_total} directional headline(s)). Sparse evidence mandates a neutral stance."

        # Rule B: Strong Positive BUY (Ratio Pos >= 1.5 * Neg and Pos >= 2)
        elif is_buy_candidate:
            if len(pos_publishers) < 2:
                decision = DecisionVerdict.HOLD
                hold_reason = HoldReason.INSUFFICIENT_CORROBORATION
                summary = f"HOLD: Positive directional sentiment observed ({pos_count} positive) but lacks multi-publisher corroboration ({len(pos_publishers)} positive publisher(s))."
                warnings.append("INSUFFICIENT_CORROBORATION")
            else:
                decision = DecisionVerdict.BUY
                summary = f"BUY: Positive catalyst momentum supported by {pos_count} positive headlines vs {neg_count} negative across {len(pos_publishers)} positive publishers (Pos/Neg ratio: {pos_count}/{max(1, neg_count)})."

        # Rule C: Strong Negative SELL (Ratio Neg >= 1.5 * Pos and Neg >= 2)
        elif is_sell_candidate:
            if len(neg_publishers) < 2:
                decision = DecisionVerdict.HOLD
                hold_reason = HoldReason.INSUFFICIENT_CORROBORATION
                summary = f"HOLD: Negative directional sentiment observed ({neg_count} negative) but lacks multi-publisher corroboration ({len(neg_publishers)} negative publisher(s))."
                warnings.append("INSUFFICIENT_CORROBORATION")
            else:
                decision = DecisionVerdict.SELL
                summary = f"SELL: Negative catalyst pressure supported by {neg_count} negative headlines vs {pos_count} positive across {len(neg_publishers)} negative publishers (Neg/Pos ratio: {neg_count}/{max(1, pos_count)})."

        # Rule D: Conflicting Evidence
        elif directional_total >= 2 and pos_count >= 1 and neg_count >= 1:
            decision = DecisionVerdict.HOLD
            hold_reason = HoldReason.CONFLICTING
            summary = f"HOLD: Conflicting market sentiment ({pos_count} positive vs. {neg_count} negative catalysts). Balanced opposing forces indicate neutral market context."

        # Rule E: Default Neutral HOLD
        else:
            decision = DecisionVerdict.HOLD
            hold_reason = HoldReason.NEUTRAL
            summary = f"HOLD: Market sentiment for {ticker} is balanced or within neutral thresholds (S={sentiment_score:+.2f})."

        # 7. Decision Confidence C in [0.0, 1.0] per D6
        if directional_total > 0:
            consensus_ratio = abs(pos_count - neg_count) / directional_total
        else:
            consensus_ratio = 0.0

        if hold_reason in (HoldReason.NO_NEWS, HoldReason.SPARSE_EVIDENCE):
            # Evidence-free or sparse directional evidence mandates 0.0 confidence (no floor)
            decision_confidence = 0.0
            confidence_note = "0.00 (Sparse evidence / no news)"
        else:
            raw_confidence = abs(sentiment_score) * (0.4 + 0.6 * consensus_ratio) * evidence_quality
            has_supporting_catalyst = False
            if pipeline_mode == PipelineMode.HYBRID_FINBERT_LLM:
                if decision == DecisionVerdict.BUY:
                    has_supporting_catalyst = any(
                        f.impact == DirectionalPolarity.POSITIVE for f in observed_facts
                    )
                elif decision == DecisionVerdict.SELL:
                    has_supporting_catalyst = any(
                        f.impact == DirectionalPolarity.NEGATIVE for f in observed_facts
                    )

            if has_supporting_catalyst:
                ceiling = 0.95
                floor = 0.20
            else:
                ceiling = 0.60
                floor = 0.15

            decision_confidence = round(min(ceiling, max(floor, raw_confidence)), 4)
            confidence_note = f"{decision_confidence:.2f} (ceiling {ceiling:.2f})"

        inferences = [
            f"FinBERT evaluated {n_valid} total headlines: {pos_count} positive, {neg_count} negative, {neu_count} neutral.",
            f"Calculated directional sentiment score: {sentiment_score:+.2f} (Neutral articles excluded from score dilution).",
            f"Corroboration: {len(pos_publishers)} positive publisher(s), {len(neg_publishers)} negative publisher(s) (P_support={p_support}).",
            f"Evidence quality: {evidence_quality:.2f} across {distinct_pub_count} distinct publisher(s) and {distinct_cluster_count} cluster(s).",
            f"Decision confidence: {confidence_note} (Directional consensus ratio: {consensus_ratio:.2f}).",
        ]

        if hold_reason == HoldReason.SPARSE_EVIDENCE:
            inferences.append("Decision rule applied: Minimum directional evidence threshold not met (mandates HOLD).")
        elif hold_reason == HoldReason.INSUFFICIENT_CORROBORATION:
            inferences.append("Corroboration rule applied: BUY/SELL requires at least 2 distinct canonical publishers on the supporting side; single-source evidence forces HOLD.")
        elif decision == DecisionVerdict.BUY:
            inferences.append(f"Decision rule applied: Positive ratio threshold met ({pos_count} pos >= 1.5 * {neg_count} neg, S={sentiment_score:+.2f} >= +0.20, corroborated by {len(pos_publishers)} publishers).")
        elif decision == DecisionVerdict.SELL:
            inferences.append(f"Decision rule applied: Negative ratio threshold met ({neg_count} neg >= 1.5 * {pos_count} pos, S={sentiment_score:+.2f} <= -0.20, corroborated by {len(neg_publishers)} publishers).")
        elif hold_reason == HoldReason.CONFLICTING:
            inferences.append("Decision rule applied: Positive and negative catalysts balance within 1.5x ratio corridor.")
        else:
            inferences.append(f"Decision rule applied: Sentiment within neutral corridor (S={sentiment_score:+.2f}).")

        rationale = PipelineRationale(
            summary=summary,
            observed_facts=observed_facts,
            inferences=inferences,
        )

        sup_publishers = (
            len(pos_publishers)
            if decision == DecisionVerdict.BUY
            else (len(neg_publishers) if decision == DecisionVerdict.SELL else 0)
        )

        return AggregatorResult(
            decision=decision,
            decision_confidence=decision_confidence,
            sentiment_score=sentiment_score,
            evidence_quality=evidence_quality,
            rationale=rationale,
            warnings=warnings,
            publishers_positive=len(pos_publishers),
            publishers_negative=len(neg_publishers),
            supporting_publishers=sup_publishers,
            hold_reason=hold_reason,
        )

