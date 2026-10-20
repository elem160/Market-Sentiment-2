import re
import urllib.parse
from datetime import datetime, timezone
from app.config import settings
from app.core.models import IngestedArticle, Asset
from app.core.enums import ExclusionReason
from app.core.session_window import SessionWindow
from app.services.relevance import RelevanceMatcher


from app.core.constants import MAX_EXCLUDED_SAMPLES_PER_REASON

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by",
    "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from", "further",
    "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me", "more", "most", "my",
    "myself", "no", "nor", "not", "now", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "we", "were",
    "what", "when", "where", "which", "while", "who", "whom", "why", "with", "would", "you", "your"
}

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "syndication", "ocid", "guccounter", "ncid"
}

PUBLISHER_NORMALIZATION_MAP = {
    "reuters": "Reuters",
    "bloomberg": "Bloomberg",
    "cnbc": "CNBC",
    "wall street journal": "Wall Street Journal",
    "wsj": "Wall Street Journal",
    "marketwatch": "MarketWatch",
    "pr newswire": "PR Newswire",
    "business wire": "Business Wire",
    "globe newswire": "GlobeNewswire",
    "seeking alpha": "Seeking Alpha",
    "motley fool": "Motley Fool",
    "investor's business daily": "Investor's Business Daily",
    "barron's": "Barron's",
    "barrons": "Barron's",
    "forbes": "Forbes",
    "yahoo": "Yahoo Finance",
    "associated press": "Associated Press",
    "ap": "Associated Press",
}



class DeduplicationService:
    @staticmethod
    def canonicalize_url(raw_url: str) -> str:
        """Strips query tracking parameters, anchors, and trailing slashes."""
        if not raw_url:
            return ""
        parsed = urllib.parse.urlparse(raw_url.strip())
        query_pairs = urllib.parse.parse_qsl(parsed.query)
        cleaned_query = [
            (k, v) for k, v in query_pairs if k.lower() not in TRACKING_PARAMS
        ]
        new_query = urllib.parse.urlencode(cleaned_query)
        path = parsed.path.rstrip("/")
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", new_query, ""))

    @staticmethod
    def normalize_publisher(source_name: str) -> str:
        """Extracts and normalizes canonical publisher entity name using whole-word boundaries (F-11)."""
        stripped = source_name.strip()
        # For syndicated "Yahoo - X", return the normalized X (not "Yahoo Finance")
        syndicated_match = re.match(
            r"^yahoo(?:\s*!\s*finance|\s+finance)?\s*[-–—:]\s*(.+)$",
            stripped,
            flags=re.IGNORECASE
        )
        if syndicated_match:
            sub_source = syndicated_match.group(1).strip()
            if sub_source:
                return DeduplicationService.normalize_publisher(sub_source)

        lower = stripped.lower()
        # Sort patterns by length descending so longer phrases match before abbreviations
        for pattern, canonical in sorted(PUBLISHER_NORMALIZATION_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            if re.search(rf"\b{re.escape(pattern)}\b", lower):
                return canonical
        if re.search(r"\b(google|rss)\b", lower):
            return "Unknown Aggregator"
        return stripped

    @staticmethod
    def tokenize(text: str) -> set[str]:
        """Convert text into normalized alphanumeric token set without stop words."""
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
        tokens = {t for t in cleaned.split() if len(t) > 2 and t not in STOP_WORDS}
        return tokens

    @classmethod
    def jaccard_similarity(cls, text_a: str, text_b: str) -> float:
        """Compute Jaccard token similarity between two headlines."""
        tokens_a = cls.tokenize(text_a)
        tokens_b = cls.tokenize(text_b)
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a.intersection(tokens_b)
        union = tokens_a.union(tokens_b)
        return len(intersection) / len(union)


    @classmethod
    def filter_by_session_window(
        cls,
        articles: list[IngestedArticle],
        session: SessionWindow,
        max_samples_per_reason: int = MAX_EXCLUDED_SAMPLES_PER_REASON,
    ) -> tuple[list[IngestedArticle], list[tuple[IngestedArticle, ExclusionReason, str]], int, int]:
        """
        Freshness stage (F-01/F-07):
        Filters articles against the active SessionWindow before relevance filtering and FinBERT scoring.
        - None timestamp -> MISSING_OR_UNTRUSTED_TIMESTAMP
        - Outside window -> TIMESTAMP_OUT_OF_WINDOW
        Returns:
        - in_window: list of valid IngestedArticle inside [window_start_utc, window_end_utc + 5min]
        - sample_excluded: list of up to max_samples_per_reason tuples per reason
        - total_out_of_window: true count of out-of-window articles
        - total_missing_timestamp: true count of undated articles
        """
        in_window: list[IngestedArticle] = []
        sample_excluded: list[tuple[IngestedArticle, ExclusionReason, str]] = []
        count_out_of_window = 0
        count_missing_ts = 0

        sample_counts = {
            ExclusionReason.MISSING_OR_UNTRUSTED_TIMESTAMP: 0,
            ExclusionReason.TIMESTAMP_OUT_OF_WINDOW: 0,
        }

        for art in articles:
            if art.published_at_utc is None:
                count_missing_ts += 1
                if sample_counts[ExclusionReason.MISSING_OR_UNTRUSTED_TIMESTAMP] < max_samples_per_reason:
                    sample_counts[ExclusionReason.MISSING_OR_UNTRUSTED_TIMESTAMP] += 1
                    sample_excluded.append((
                        art,
                        ExclusionReason.MISSING_OR_UNTRUSTED_TIMESTAMP,
                        "Article published timestamp is missing, untrusted, or unparseable."
                    ))
            elif not session.is_timestamp_in_window(art.published_at_utc):
                count_out_of_window += 1
                if sample_counts[ExclusionReason.TIMESTAMP_OUT_OF_WINDOW] < max_samples_per_reason:
                    sample_counts[ExclusionReason.TIMESTAMP_OUT_OF_WINDOW] += 1
                    sample_excluded.append((
                        art,
                        ExclusionReason.TIMESTAMP_OUT_OF_WINDOW,
                        f"Timestamp {art.published_at_utc.isoformat()} is outside session window [{session.window_start_utc.isoformat()}, {session.window_end_utc.isoformat()}]."
                    ))
            else:
                in_window.append(art)

        return in_window, sample_excluded, count_out_of_window, count_missing_ts

    @classmethod
    def process_and_deduplicate(
        cls,
        raw_articles: list[IngestedArticle],
        ticker: str = "",
        company_name: str = "",
        max_articles: int | None = None,
        matcher: RelevanceMatcher | None = None,
    ) -> tuple[list[IngestedArticle], list[tuple[IngestedArticle, ExclusionReason, str]], dict[str, str]]:
        """
        Processes ingested articles:
        1. Canonicalizes URLs
        2. Filters out articles lacking material entity relevance
        3. Detects syndicated duplicates via Token-Sort Jaccard similarity (>= 0.82)
        4. Enforces capacity limit (settings.MAX_RETAINED_ARTICLES or max_articles) newest first
        
        Returns:
        - retained_articles: list[IngestedArticle]
        - excluded_articles: list[tuple[IngestedArticle, ExclusionReason, str]] (article, reason, note)
        - cluster_map: dict[article_id, cluster_id]
        """
        retained: list[IngestedArticle] = []
        excluded: list[tuple[IngestedArticle, ExclusionReason, str]] = []
        cluster_map: dict[str, str] = {}

        # Clean URLs first
        cleaned_articles: list[IngestedArticle] = []
        for a in raw_articles:
            a.canonical_url = cls.canonicalize_url(a.canonical_url)
            cleaned_articles.append(a)

        # Sort chronologically (earliest first so earliest release becomes cluster primary)
        sorted_articles = sorted(
            cleaned_articles,
            key=lambda x: x.published_at_utc or datetime.min.replace(tzinfo=timezone.utc)
        )

        seen_clusters: list[tuple[str, str, IngestedArticle]] = []  # (cluster_id, headline, primary_article)
        non_dup_candidates: list[IngestedArticle] = []

        if matcher is None:
            matcher = RelevanceMatcher.for_asset(
                Asset(ticker=ticker, company_name=company_name, exchange="")
            )

        for article in sorted_articles:
            # 1. Relevance check via RelevanceMatcher
            match_reason = matcher.match(article.title, article.summary)
            if not match_reason:
                excluded.append((
                    article,
                    ExclusionReason.INSUFFICIENT_ENTITY_RELEVANCE,
                    f"Headline does not mention {matcher.asset.ticker} or {matcher.asset.company_name} materially."
                ))
                continue

            # 2. Duplicate / Syndication check
            is_dup = False
            for cluster_id, primary_headline, primary_art in seen_clusters:
                sim = cls.jaccard_similarity(article.title, primary_headline)
                same_url = article.canonical_url and (article.canonical_url == primary_art.canonical_url)
                if sim >= 0.82 or same_url:
                    is_dup = True
                    cluster_map[article.article_id] = cluster_id
                    excluded.append((
                        article,
                        ExclusionReason.DUPLICATE_SYNDICATION,
                        f"Syndicated copy of '{primary_art.title[:60]}...' (similarity: {sim:.2f})"
                    ))
                    break

            if not is_dup:
                # New distinct event cluster
                cluster_id = f"clust_{article.article_id}"
                cluster_map[article.article_id] = cluster_id
                seen_clusters.append((cluster_id, article.title, article))
                non_dup_candidates.append(article)

        # F-05: Sort retained candidates newest first before applying MAX_RETAINED_ARTICLES
        non_dup_candidates.sort(
            key=lambda x: x.published_at_utc or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )

        effective_limit = max_articles if max_articles is not None else settings.MAX_RETAINED_ARTICLES
        for candidate in non_dup_candidates:
            if len(retained) < effective_limit:
                retained.append(candidate)
            else:
                excluded.append((
                    candidate,
                    ExclusionReason.CAPACITY_LIMIT,
                    f"Retained article limit ({effective_limit}) reached."
                ))

        return retained, excluded, cluster_map

