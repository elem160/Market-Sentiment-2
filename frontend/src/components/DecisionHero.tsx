import React from 'react';
import { AnalysisResult } from '../types';
import { formatTickerLabel } from '../utils/formatters';
import {
  TrendingUp,
  TrendingDown,
  MinusCircle,
  AlertTriangle,
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
        return <TrendingUp size={28} aria-hidden="true" />;
      case 'SELL':
        return <TrendingDown size={28} aria-hidden="true" />;
      case 'HOLD':
      default:
        return <MinusCircle size={28} aria-hidden="true" />;
    }
  };

  const compositeTone = (s: number) => (s > 0.25 ? 'is-pos' : s < -0.25 ? 'is-neg' : 'is-flat');

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

  const tickerLabel = formatTickerLabel(result.ticker, result.asset_type);

  return (
    <section
      id="decision-hero-card"
      className={`sp-signal ${verdictClass}`}
      aria-label="Directional market sentiment classification"
    >
      <div className="sp-sec-head sp-signal-head">
        <span className="sp-sec-index">03</span>
        <span className="sp-label">Signal</span>
        <span className="sp-label">Current algorithmic classification</span>
      </div>

      <div className="sp-signal-main sp-sheet">
        <div className="sp-cell sp-signal-id">
          <div className="sp-tags">
            <span className="sp-tag">{result.asset_type || 'US Equity'}</span>
            {result.cache_status === 'HIT' && (
              <span className="sp-tag sp-tag--accent">Cached Result</span>
            )}
            {result.data_status === 'NO_FRESH_NEWS' && (
              <span className="sp-tag sp-tag--hatch">No Fresh News</span>
            )}
            {result.data_status === 'NO_RELEVANT_NEWS' && (
              <span className="sp-tag sp-tag--hatch">No Relevant News</span>
            )}
            {result.data_status === 'DEGRADED' && (
              <span className="sp-tag sp-tag--sell">Degraded</span>
            )}
          </div>
          <h2
            id="result-ticker-symbol"
            className="sp-display sp-ticker"
            data-len={tickerLabel.length > 8 ? 'long' : 'short'}
          >
            {tickerLabel}
          </h2>
          <div className="sp-company">{result.company_name}</div>
        </div>

        <div className={`sp-cell sp-cell--slab sp-verdict ${verdictClass}`}>
          <span className="sp-label">Classification</span>
          <div id="result-verdict-pill" className="sp-verdict-word sp-display">
            {getVerdictIcon()}
            <span>{verdict}</span>
          </div>
          {verdict === 'HOLD' && result.hold_reason && (
            <div className="sp-hold-reason sp-mono">
              Reason: {formatHoldReason(result.hold_reason)}
            </div>
          )}
        </div>
      </div>

      {result.data_status === 'NO_FRESH_NEWS' && (
        <div className="sp-notice" role="status">
          <AlertTriangle size={18} aria-hidden="true" style={{ flexShrink: 0 }} />
          <span>
            <strong>NO FRESH NEWS IN SESSION:</strong> Zero articles satisfied current session window freshness criteria. The HOLD verdict is an uncorroborated default for zero active headlines.
          </span>
        </div>
      )}

      {result.data_status === 'NO_RELEVANT_NEWS' && (
        <div className="sp-notice" role="status">
          <AlertTriangle size={18} aria-hidden="true" style={{ flexShrink: 0 }} />
          <span>
            <strong>NO RELEVANT NEWS IN SESSION:</strong> Ingested articles did not pass multi-asset entity relevance filters for this symbol. The HOLD verdict is an evidence-free default.
          </span>
        </div>
      )}

      {result.data_status === 'DEGRADED' && (
        <div className="sp-notice sp-notice--degraded" role="alert">
          <AlertTriangle size={18} aria-hidden="true" style={{ flexShrink: 0 }} />
          <span>
            <strong>DEGRADED INGESTION:</strong> All external RSS news feeds failed during ingestion sweep. Analysis was completed using partial sources only and will not be cached.
          </span>
        </div>
      )}

      <div className="sp-metrics sp-sheet" role="group" aria-label="Supporting metrics">
        <div className="sp-cell sp-metric sp-metric--wide">
          <span className="sp-label">Composite Sentiment</span>
          <div
            id="result-composite-score"
            className={`sp-score sp-mono ${compositeTone(result.sentiment_score)}`}
          >
            {formatScore(result.sentiment_score)}
          </div>
          <div className="sp-gauge" aria-hidden="true">
            <div className="sp-gauge-zone" />
            <div
              className="sp-gauge-marker"
              style={{
                left: `${Math.min(100, Math.max(0, ((result.sentiment_score + 1) / 2) * 100))}%`,
              }}
            />
          </div>
          <div className="sp-gauge-scale sp-mono" aria-hidden="true">
            <span>&minus;1.00</span>
            <span>0</span>
            <span>+1.00</span>
          </div>
          <div className="sp-metric-sub">Range [-1.00 to +1.00]</div>
        </div>

        <div className="sp-cell sp-metric">
          <span className="sp-label">Confidence Level</span>
          <div id="result-confidence-score" className="sp-score-sm sp-mono">
            {isEvidenceFreeHold ? 'n/a' : `${((result.decision_confidence || 0) * 100).toFixed(0)}%`}
          </div>
          {!isEvidenceFreeHold && (
            <div className="sp-seg" aria-hidden="true">
              {Array.from({ length: 10 }).map((_, i) => (
                <span
                  key={i}
                  className={i < Math.round((result.decision_confidence || 0) * 10) ? 'on' : ''}
                />
              ))}
            </div>
          )}
          <div className="sp-metric-sub">
            {isEvidenceFreeHold
              ? (result.hold_reason === 'SPARSE_EVIDENCE' ? 'Sparse Evidence' : 'Evidence-Free HOLD')
              : result.decision_confidence >= 0.7
              ? 'High Confidence'
              : result.decision_confidence >= 0.4
              ? 'Moderate Confidence'
              : 'Low / Capped'}
          </div>
        </div>

        <div className="sp-cell sp-metric">
          <span className="sp-label">Evidence Quality</span>
          <div className="sp-score-sm sp-mono">
            {((result.evidence_quality || 0) * 100).toFixed(0)}%
          </div>
          <div className="sp-seg" aria-hidden="true">
            {Array.from({ length: 10 }).map((_, i) => (
              <span
                key={i}
                className={i < Math.round((result.evidence_quality || 0) * 10) ? 'on' : ''}
              />
            ))}
          </div>
          <div className="sp-metric-sub">
            {result.metrics?.articles_retained ?? (result.articles?.filter(a => !a.exclusion_reason).length || 0)} Retained Articles
          </div>
        </div>

        <div className="sp-cell sp-metric">
          <span className="sp-label">Publisher Corroboration</span>
          <div>
            {isCorroborated ? (
              <span className="sp-tag sp-tag--buy">
                <CheckCircle2 size={13} aria-hidden="true" /> Corroborated
              </span>
            ) : (
              <span className="sp-tag sp-tag--hatch">
                <AlertTriangle size={13} aria-hidden="true" />{' '}
                {result.hold_reason === 'INSUFFICIENT_CORROBORATION'
                  ? 'Insufficient Corroboration'
                  : distinctPubs <= 1
                  ? 'Single Publisher'
                  : 'Uncorroborated'}
              </span>
            )}
          </div>
          <div className="sp-metric-sub">
            {verdict === 'BUY' || verdict === 'SELL'
              ? `${supportingPubs} Supporting Source(s)`
              : `${distinctPubs} Distinct Source(s)`}
          </div>
        </div>
      </div>

      <div className="sp-footnote sp-cell--slab" role="note" aria-label="Research disclaimer">
        <span className="sp-tag sp-tag--accent">Research use only</span>
        <span>
          <strong>{result.disclaimer || 'Research & Market Sentiment Tool. Not Financial or Investment Advice.'}</strong> Decision formulation uses exponential recency decay (14-hour half-life) with strict corroboration gating. All thresholds are uncalibrated empirical defaults.
        </span>
      </div>
    </section>
  );
};
