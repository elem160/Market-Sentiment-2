import React from 'react';
import { AnalysisResult } from '../types';
import { formatTickerLabel } from '../utils/formatters';
import {
  TrendingUp,
  TrendingDown,
  MinusCircle,
  AlertTriangle,
  Info,
  CheckCircle2,
} from 'lucide-react';

interface DecisionHeroProps {
  result: AnalysisResult;
}

export const DecisionHero: React.FC<DecisionHeroProps> = ({ result }) => {
  const verdict = result.decision || 'HOLD';
  const verdictClass = verdict.toLowerCase();

  const getVerdictIcon = () => {
    switch (verdict) {
      case 'BUY':
        return <TrendingUp size={24} aria-hidden="true" />;
      case 'SELL':
        return <TrendingDown size={24} aria-hidden="true" />;
      case 'HOLD':
      default:
        return <MinusCircle size={24} aria-hidden="true" />;
    }
  };

  const getCompositeColor = (score: number) => {
    if (score > 0.25) return 'var(--color-positive)';
    if (score < -0.25) return 'var(--color-negative)';
    return 'var(--color-caution)';
  };

  const formatScore = (val: number) => {
    return (val > 0 ? '+' : '') + (val || 0).toFixed(3);
  };

  const formatHoldReason = (reason?: string | null) => {
    switch (reason) {
      case 'NO_NEWS':
        return 'No News';
      case 'SPARSE_EVIDENCE':
        return 'Sparse Evidence';
      case 'INSUFFICIENT_CORROBORATION':
        return 'Insufficient Corroboration';
      case 'CONFLICTING':
        return 'Conflicting Evidence';
      case 'NEUTRAL':
        return 'Neutral Sentiment';
      default:
        return reason || '';
    }
  };

  const distinctPubs = result.metrics?.distinct_publishers ?? 0;
  const supportingPubs = result.metrics?.supporting_publishers ?? 0;
  const isCorroborated = (verdict === 'BUY' || verdict === 'SELL') && supportingPubs >= 2;
  const isEvidenceFreeHold =
    verdict === 'HOLD' &&
    (result.hold_reason === 'NO_NEWS' ||
      result.hold_reason === 'SPARSE_EVIDENCE' ||
      result.data_status === 'NO_FRESH_NEWS' ||
      result.data_status === 'NO_RELEVANT_NEWS' ||
      (result.decision_confidence || 0) === 0);

  return (
    <section
      className={`hero-decision-card ${verdictClass} animate-fade-in`}
      id="decision-hero-card"
      aria-label="Directional market sentiment classification"
    >
      <div className="decision-top">
        <div className="asset-identity">
          <div className="sp-hero-eyebrow">Current Algorithmic Classification</div>
          <div className="asset-ticker-row">
            <h2 className="asset-ticker" id="result-ticker-symbol">
              {formatTickerLabel(result.ticker, result.asset_type)}
            </h2>
            <span className="asset-exchange">{result.asset_type || 'US Equity'}</span>
            {result.cache_status === 'HIT' && (
              <span className="badge badge-neutral" style={{ color: 'var(--color-accent)' }}>
                Cached Result
              </span>
            )}
            {result.data_status === 'NO_FRESH_NEWS' && (
              <span className="badge badge-hold">
                No Fresh News
              </span>
            )}
            {result.data_status === 'NO_RELEVANT_NEWS' && (
              <span className="badge badge-hold">
                No Relevant News
              </span>
            )}
            {result.data_status === 'DEGRADED' && (
              <span className="badge badge-sell">
                Degraded
              </span>
            )}
          </div>
          <div className="asset-name">{result.company_name}</div>
        </div>

        <div className="verdict-box">
          <div className={`verdict-pill ${verdictClass}`} id="result-verdict-pill">
            {getVerdictIcon()}
            <span>{verdict}</span>
          </div>
          {verdict === 'HOLD' && result.hold_reason && (
            <div className="hold-reason-sub">
              Reason: {formatHoldReason(result.hold_reason)}
            </div>
          )}
        </div>
      </div>

      {result.data_status === 'NO_FRESH_NEWS' && (
        <div className="no-fresh-news-banner" role="status">
          <AlertTriangle size={18} style={{ flexShrink: 0 }} aria-hidden="true" />
          <span>
            <strong>NO FRESH NEWS IN SESSION:</strong> Zero articles satisfied current session window freshness criteria. The HOLD verdict is an uncorroborated default for zero active headlines.
          </span>
        </div>
      )}

      {result.data_status === 'NO_RELEVANT_NEWS' && (
        <div className="no-fresh-news-banner" role="status">
          <AlertTriangle size={18} style={{ flexShrink: 0 }} aria-hidden="true" />
          <span>
            <strong>NO RELEVANT NEWS IN SESSION:</strong> Ingested articles did not pass multi-asset entity relevance filters for this symbol. The HOLD verdict is an evidence-free default.
          </span>
        </div>
      )}

      {result.data_status === 'DEGRADED' && (
        <div className="no-fresh-news-banner degraded" role="alert">
          <AlertTriangle size={18} style={{ flexShrink: 0 }} aria-hidden="true" />
          <span>
            <strong>DEGRADED INGESTION:</strong> All external RSS news feeds failed during ingestion sweep. Analysis was completed using partial sources only and will not be cached.
          </span>
        </div>
      )}

      <div className="metrics-strip" role="group" aria-label="Supporting metrics">
        <div className="metric-item">
          <div className="metric-label">Composite Sentiment</div>
          <div
            className="metric-val"
            style={{ color: getCompositeColor(result.sentiment_score) }}
            id="result-composite-score"
          >
            {formatScore(result.sentiment_score)}
          </div>
          <div className="metric-sub">
            Range [-1.00 to +1.00]
          </div>
        </div>

        <div className="metric-item">
          <div className="metric-label">Confidence Level</div>
          <div className="metric-val" id="result-confidence-score">
            {isEvidenceFreeHold ? 'n/a' : `${((result.decision_confidence || 0) * 100).toFixed(0)}%`}
          </div>
          <div className="metric-sub">
            {isEvidenceFreeHold
              ? (result.hold_reason === 'SPARSE_EVIDENCE' ? 'Sparse Evidence' : 'Evidence-Free HOLD')
              : result.decision_confidence >= 0.7
              ? 'High Confidence'
              : result.decision_confidence >= 0.4
              ? 'Moderate Confidence'
              : 'Low / Capped'}
          </div>
        </div>

        <div className="metric-item">
          <div className="metric-label">Evidence Quality</div>
          <div className="metric-val">
            {((result.evidence_quality || 0) * 100).toFixed(0)}%
          </div>
          <div className="metric-sub">
            {result.metrics?.articles_retained ?? (result.articles?.filter(a => !a.exclusion_reason).length || 0)} Retained Articles
          </div>
        </div>

        <div className="metric-item">
          <div className="metric-label">Publisher Corroboration</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
            {isCorroborated ? (
              <span className="badge badge-buy">
                <CheckCircle2 size={13} aria-hidden="true" /> Corroborated
              </span>
            ) : (
              <span className="badge badge-hold">
                <AlertTriangle size={13} aria-hidden="true" />{' '}
                {result.hold_reason === 'INSUFFICIENT_CORROBORATION'
                  ? 'Insufficient Corroboration'
                  : distinctPubs <= 1
                    ? 'Single Publisher'
                    : 'Uncorroborated'}
              </span>
            )}
          </div>
          <div className="metric-sub" style={{ marginTop: '6px' }}>
            {verdict === 'BUY' || verdict === 'SELL'
              ? `${supportingPubs} Supporting Source(s)`
              : `${distinctPubs} Distinct Source(s)`}
          </div>
        </div>
      </div>

      <div className="heuristic-footnote" role="note" aria-label="Research disclaimer">
        <Info size={15} style={{ flexShrink: 0, color: 'var(--color-ink-muted)' }} aria-hidden="true" />
        <span>
          <strong>{result.disclaimer || 'Research & Market Sentiment Tool. Not Financial or Investment Advice.'}</strong> Decision formulation uses exponential recency decay (14-hour half-life) with strict corroboration gating. All thresholds are uncalibrated empirical defaults.
        </span>
      </div>
    </section>
  );
};
