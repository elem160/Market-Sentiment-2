import re
import urllib.parse
from app.config import settings
from app.core.models import IngestedArticle
from app.core.enums import ExclusionReason

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
        """Extracts and normalizes canonical publisher entity name."""
        lower = source_name.lower().strip()
        for pattern, canonical in PUBLISHER_NORMALIZATION_MAP.items():
            if pattern in lower:
                return canonical
        if "google" in lower or "rss" in lower:
            return "Unknown Aggregator"
        return source_name.strip()

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
    def is_materially_relevant(cls, article: IngestedArticle, ticker: str, company_name: str) -> bool:
        """
        Verify that the ticker symbol, asset aliases, or company name is materially mentioned
        in the title or summary, avoiding listicles or generic market roundups.
        Supports Equities ($NVDA, AAPL), Forex (EUR/USD, EURUSD), Commodities (GC=F, Gold),
        and Crypto (BTC-USD, Bitcoin).
        """
        full_text = f"{article.title} {article.summary}".lower()
        ticker_lower = ticker.lower()

        # 1. Direct or $ prefixed mention
        if ticker_lower in full_text or f"${ticker_lower}" in full_text:
            return True

        # 2. Forex notation variants (EUR/USD <-> EURUSD <-> EURUSD=X)
        if "/" in ticker_lower:
            no_slash = ticker_lower.replace("/", "")
            if no_slash in full_text:
                return True
        if ticker_lower.endswith("=x"):
            raw_pair = ticker_lower[:-2]
            if raw_pair in full_text:
                return True

        # 3. Crypto / Futures variants (BTC-USD -> BTC, GC=F -> GC)
        if "-" in ticker_lower:
            crypto_root = ticker_lower.split("-")[0]
            if len(crypto_root) >= 3 and re.search(rf"\b{re.escape(crypto_root)}\b", full_text):
                return True

        # 4. Standalone alphanumeric ticker word boundary check (e.g. NVDA, AAPL)
        clean_alphanumeric = re.sub(r"[^a-zA-Z0-9]", "", ticker_lower)
        if clean_alphanumeric and len(clean_alphanumeric) <= 5:
            if re.search(rf"\b{re.escape(clean_alphanumeric)}\b", full_text):
                return True

        # 5. Check meaningful company name / asset tokens (e.g. NVIDIA, Apple, Gold, Euro, Bitcoin)
        stop_name_tokens = {
            "inc", "corp", "corporation", "ltd", "company", "co", "the", "group",
            "futures", "currency", "pair", "class", "common", "stock"
        }
        company_tokens = [
            t for t in cls.tokenize(company_name)
            if t not in stop_name_tokens and len(t) >= 3
        ]
        if company_tokens and any(t in full_text for t in company_tokens):
            return True

        return False

    @classmethod
    def process_and_deduplicate(
        cls, raw_articles: list[IngestedArticle], ticker: str, company_name: str
    ) -> tuple[list[IngestedArticle], list[tuple[IngestedArticle, ExclusionReason, str]], dict[str, str]]:
        """
        Processes ingested articles:
        1. Canonicalizes URLs
        2. Filters out articles lacking material entity relevance
        3. Detects syndicated duplicates via Token-Sort Jaccard similarity (>= 0.82)
        4. Enforces capacity limit (settings.MAX_RETAINED_ARTICLES)
        
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
        sorted_articles = sorted(cleaned_articles, key=lambda x: x.published_at_utc)

        seen_clusters: list[tuple[str, str, IngestedArticle]] = []  # (cluster_id, headline, primary_article)

        for article in sorted_articles:
            # 1. Relevance check
            if not cls.is_materially_relevant(article, ticker, company_name):
                excluded.append((
                    article,
                    ExclusionReason.INSUFFICIENT_ENTITY_RELEVANCE,
                    f"Headline does not mention {ticker} or {company_name} materially."
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

                # Check capacity limit
                if len(retained) < settings.MAX_RETAINED_ARTICLES:
                    retained.append(article)
                else:
                    excluded.append((
                        article,
                        ExclusionReason.CAPACITY_LIMIT,
                        f"Retained article limit ({settings.MAX_RETAINED_ARTICLES}) reached."
                    ))

        return retained, excluded, cluster_map
