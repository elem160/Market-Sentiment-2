import React from 'react';
import { AnalysisResult } from '../types';
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
        return <TrendingUp size={36} />;
      case 'SELL':
        return <TrendingDown size={36} />;
      case 'HOLD':
      default:
        return <MinusCircle size={36} />;
    }
  };

  const getCompositeColor = (score: number) => {
    if (score > 0.25) return 'var(--buy-green)';
    if (score < -0.25) return 'var(--sell-rose)';
    return 'var(--hold-amber)';
  };

  const formatScore = (val: number) => {
    return (val > 0 ? '+' : '') + (val || 0).toFixed(3);
  };

  const distinctPubs = result.metrics?.distinct_publishers ?? 0;
  const isCorroborated = distinctPubs >= 2;

  return (
    <div className={`glass-panel hero-decision-card ${verdictClass} animate-fade-in`} id="decision-hero-card">
      <div className="decision-top">
        <div className="asset-identity">
          <div className="asset-ticker-row">
            <h2 className="asset-ticker" id="result-ticker-symbol">${result.ticker}</h2>
            <span className="asset-exchange">{result.asset_type || 'US Equity'}</span>
            {result.cache_status === 'HIT' && (
              <span className="badge badge-neutral" style={{ color: 'var(--accent-cyan)' }}>
                15m Cache Hit
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
        </div>
      </div>

      <div className="metrics-strip">
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
            {((result.decision_confidence || 0) * 100).toFixed(0)}%
          </div>
          <div className="metric-sub">
            {result.decision_confidence >= 0.6
              ? 'Multi-Source Corroborated'
              : result.decision_confidence >= 0.3
              ? 'Moderate Evidence'
              : 'Low / Capped'}
          </div>
        </div>

        <div className="metric-item">
          <div className="metric-label">Evidence Quality</div>
          <div className="metric-val">
            {((result.evidence_quality || 0) * 100).toFixed(0)}%
          </div>
          <div className="metric-sub">
            {result.articles?.length || 0} Retained Articles
          </div>
        </div>

        <div className="metric-item">
          <div className="metric-label">Publisher Corroboration</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
            {isCorroborated ? (
              <span className="badge badge-buy" style={{ fontSize: '0.82rem' }}>
                <CheckCircle2 size={14} /> Corroborated
              </span>
            ) : (
              <span className="badge badge-hold" style={{ fontSize: '0.82rem' }}>
                <AlertTriangle size={14} /> {distinctPubs === 1 ? 'Single Publisher' : 'Sparse Evidence'}
              </span>
            )}
          </div>
          <div className="metric-sub" style={{ marginTop: '8px' }}>
            {distinctPubs} Distinct Source(s)
          </div>
        </div>
      </div>

      <div className="heuristic-footnote">
        <Info size={15} style={{ flexShrink: 0, color: 'var(--text-muted)' }} />
        <span>
          <strong>{result.disclaimer || 'Research & Market Sentiment Tool. Not Financial or Investment Advice.'}</strong> Decision formulation uses exponential recency decay (14-hour half-life) with strict corroboration gating. All thresholds are uncalibrated empirical defaults.
        </span>
      </div>
    </div>
  );
};
