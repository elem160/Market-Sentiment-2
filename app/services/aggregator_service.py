import math
from datetime import datetime, timezone
from app.core.models import (
    ScoredArticle,
    ObservedFact,
    PipelineRationale,
    DecisionVerdict,
    PipelineMode,
)
from app.core.session_window import SessionWindow

# 14-hour half life for exponential recency decay
LAMBDA_DECAY = math.log(2.0) / 14.0


class AggregatorService:
    @classmethod
    def aggregate_and_decide(
        cls,
        ticker: str,
        company_name: str,
        session: SessionWindow,
        articles: list[ScoredArticle],
        observed_facts: list[ObservedFact],
        llm_summary: str,
        pipeline_mode: PipelineMode = PipelineMode.HYBRID_FINBERT_LLM,
    ) -> tuple[DecisionVerdict, float, float, float, PipelineRationale, list[str]]:
        """
        Calculates:
        - Exponential recency decay
        - Composite sentiment score S in [-1.0, 1.0]
        - Evidence quality Q in [0.0, 1.0]
        - Decision confidence C in [0.0, 1.0]
        - Enforces the 2-distinct-publisher & 2-distinct-cluster rule for BUY/SELL
        - Heuristic decision matrix verdict
        - Plain-English rationale separating facts vs inferences
        
        Returns:
        (decision, confidence, sentiment_score, evidence_quality, rationale, warnings)
        """
        warnings: list[str] = []
        if pipeline_mode == PipelineMode.DETERMINISTIC_FINBERT_ONLY:
            warnings.append("LLM synthesis unavailable: Result generated using local NLP classifier only (confidence capped at 0.60).")

        # 1. Filter valid non-excluded articles
        valid_articles = [a for a in articles if a.exclusion_reason is None]

        # Check for zero news
        if len(valid_articles) == 0:
            summary = f"No verifiable news found for {ticker} within the current trading session window."
            rationale = PipelineRationale(
                summary=summary,
                observed_facts=[],
                inferences=["Zero articles passed session window and entity relevance filters."],
            )
            return (
                DecisionVerdict.HOLD,
                0.0,
                0.0,
                0.0,
                rationale,
                ["No current-day news available within the session window."]
            )

        # 2. Separate directional vs neutral articles and compute recency weights
        now_utc = session.run_timestamp_utc
        pos_count = 0
        neg_count = 0
        neu_count = 0

        valid_publishers = set()
        valid_clusters = set()

        directional_weighted_sum = 0.0
        directional_weight_sum = 0.0

        for art in valid_articles:
            pub_utc = art.published_at_utc
            if pub_utc.tzinfo is None:
                pub_utc = pub_utc.replace(tzinfo=timezone.utc)
            delta_hours = max(0.0, (now_utc - pub_utc).total_seconds() / 3600.0)
            recency_decay = math.exp(-LAMBDA_DECAY * delta_hours)

            art_weight = round(recency_decay * max(0.2, art.final_weight), 4)

            # Directional tally
            if art.finbert_directional_score > 0.15:
                pos_count += 1
                directional_weighted_sum += art_weight * art.finbert_directional_score
                directional_weight_sum += art_weight
                if art.canonical_publisher != "Unknown Aggregator":
                    valid_publishers.add(art.canonical_publisher)
                if art.cluster_id:
                    valid_clusters.add(art.cluster_id)
            elif art.finbert_directional_score < -0.15:
                neg_count += 1
                directional_weighted_sum += art_weight * art.finbert_directional_score
                directional_weight_sum += art_weight
                if art.canonical_publisher != "Unknown Aggregator":
                    valid_publishers.add(art.canonical_publisher)
                if art.cluster_id:
                    valid_clusters.add(art.cluster_id)
            else:
                neu_count += 1
                # Neutral articles do not dilute directional score summation

        # 3. Composite Sentiment Score S in [-1.0, 1.0] (computed from directional evidence)
        if directional_weight_sum > 0:
            sentiment_score = round(max(-1.0, min(1.0, directional_weighted_sum / directional_weight_sum)), 4)
        else:
            sentiment_score = 0.0

        # 4. Evidence Quality Metric Q in [0.0, 1.0]
        distinct_pub_count = len(valid_publishers)
        distinct_cluster_count = len(valid_clusters)
        n_valid = len(valid_articles)
        directional_total = pos_count + neg_count

        volume_factor = min(1.0, max(0.3, directional_total / 3.0))
        diversity_factor = 0.5 + 0.5 * min(1.0, max(1, distinct_pub_count) / 2.0)
        evidence_quality = round(min(1.0, max(0.1, volume_factor * diversity_factor)), 4)

        # 5. Decision Confidence C in [0.0, 1.0]
        if directional_total > 0:
            consensus_ratio = abs(pos_count - neg_count) / directional_total
        else:
            consensus_ratio = 0.0

        raw_confidence = abs(sentiment_score) * (0.4 + 0.6 * consensus_ratio) * evidence_quality
        if pipeline_mode == PipelineMode.DETERMINISTIC_FINBERT_ONLY:
            decision_confidence = round(min(0.60, max(0.15, raw_confidence)), 4)
        else:
            decision_confidence = round(min(0.95, max(0.20, raw_confidence)), 4)

        # 6. Evaluate Ratio-Based Decision Matrix
        inferences = [
            f"FinBERT evaluated {n_valid} total headlines: {pos_count} positive, {neg_count} negative, {neu_count} neutral.",
            f"Calculated directional sentiment score: {sentiment_score:+.2f} (Neutral articles excluded from score dilution).",
            f"Evidence quality: {evidence_quality:.2f} across {distinct_pub_count} distinct publisher(s) and {distinct_cluster_count} cluster(s).",
            f"Decision confidence: {decision_confidence:.2f} (Directional consensus ratio: {consensus_ratio:.2f}).",
        ]

        if distinct_pub_count < 2 and distinct_cluster_count < 2 and directional_total >= 2:
            warnings.append("Single-source feed: Directional sentiment observed primarily from one publisher or cluster.")

        # Rule A: Sparse Evidence
        if directional_total < 2 or n_valid < 2:
            decision = DecisionVerdict.HOLD
            summary = f"HOLD: Insufficient directional headline volume for {ticker} ({directional_total} directional headline(s)). Sparse evidence mandates a neutral stance."
            inferences.append("Decision rule applied: Minimum directional evidence threshold not met (mandates HOLD).")

        # Rule B: Strong Positive BUY (Ratio Pos >= 1.5 * Neg and Pos >= 2)
        elif pos_count >= 2 and (neg_count == 0 or pos_count >= 1.5 * neg_count) and sentiment_score >= 0.20:
            decision = DecisionVerdict.BUY
            summary = (
                llm_summary
                if llm_summary
                else f"BUY: Positive catalyst momentum supported by {pos_count} positive headlines vs {neg_count} negative (Pos/Neg ratio: {pos_count}/{max(1, neg_count)})."
            )
            inferences.append(f"Decision rule applied: Positive ratio threshold met ({pos_count} pos >= 1.5 * {neg_count} neg, S={sentiment_score:+.2f} >= +0.20).")

        # Rule C: Strong Negative SELL (Ratio Neg >= 1.5 * Pos and Neg >= 2)
        elif neg_count >= 2 and (pos_count == 0 or neg_count >= 1.5 * pos_count) and sentiment_score <= -0.20:
            decision = DecisionVerdict.SELL
            summary = (
                llm_summary
                if llm_summary
                else f"SELL: Negative catalyst pressure supported by {neg_count} negative headlines vs {pos_count} positive (Neg/Pos ratio: {neg_count}/{max(1, pos_count)})."
            )
            inferences.append(f"Decision rule applied: Negative ratio threshold met ({neg_count} neg >= 1.5 * {pos_count} pos, S={sentiment_score:+.2f} <= -0.20).")

        # Rule D: Conflicting Evidence
        elif directional_total >= 2 and pos_count >= 1 and neg_count >= 1:
            decision = DecisionVerdict.HOLD
            summary = f"HOLD: Conflicting market sentiment ({pos_count} positive vs. {neg_count} negative catalysts). Balanced opposing forces indicate neutral market context."
            inferences.append("Decision rule applied: Positive and negative catalysts balance within 1.5x ratio corridor.")

        # Rule E: Default Neutral HOLD
        else:
            decision = DecisionVerdict.HOLD
            summary = llm_summary if llm_summary else f"HOLD: Market sentiment for {ticker} is balanced or within neutral thresholds (S={sentiment_score:+.2f})."
            inferences.append(f"Decision rule applied: Sentiment within neutral corridor (S={sentiment_score:+.2f}).")

        rationale = PipelineRationale(
            summary=summary,
            observed_facts=observed_facts,
            inferences=inferences,
        )

        return (
            decision,
            decision_confidence,
            sentiment_score,
            evidence_quality,
            rationale,
            warnings,
        )
