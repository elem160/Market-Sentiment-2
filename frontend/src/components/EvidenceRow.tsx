import React, { useState } from 'react';
import { ScoredArticle } from '../types';
import { ExternalLink } from 'lucide-react';
import { formatUtc } from '../utils/time';

interface EvidenceRowProps {
  art: ScoredArticle;
  index: number;
  showSentiment?: boolean;
}

export const EvidenceRow: React.FC<EvidenceRowProps> = ({ art, index, showSentiment = true }) => {
  const [open, setOpen] = useState(false);

  const pos = art.finbert_positive ?? 0.1;
  const neg = art.finbert_negative ?? 0.1;
  const neu = art.finbert_neutral ?? 0.8;

  const posPct = Math.round(pos * 100);
  const neuPct = Math.round(neu * 100);
  const negPct = Math.round(neg * 100);

  const dirScore = art.finbert_directional_score ?? 0;
  const scoreTone = dirScore > 0.15 ? 'is-pos' : dirScore < -0.15 ? 'is-neg' : 'is-flat';
  const signedScore = (dirScore > 0 ? '+' : '') + dirScore.toFixed(2);

  const rowId = art.article_id ? `row-${art.article_id}` : `row-${index}`;

  const weightStr =
    art.effective_weight != null
      ? `Eff. Weight: ${art.effective_weight.toFixed(3)}`
      : art.final_weight != null
      ? `Weight: ${art.final_weight.toFixed(3)}`
      : '—';

  return (
    <article className="sp-row evidence-item" data-open={open}>
      <div className="sp-row-main">
        <span className="sp-mono sp-row-n">{String(index + 1).padStart(2, '0')}</span>

        <div className="sp-row-title">
          {art.canonical_url ? (
            <a
              href={art.canonical_url}
              target="_blank"
              rel="noopener noreferrer"
              className="sp-row-link article-title-link"
            >
              <span>{art.title}</span>
              <ExternalLink size={14} aria-hidden="true" />
            </a>
          ) : (
            <span className="sp-row-link article-title-text">{art.title}</span>
          )}
        </div>

        <div className="sp-row-src">
          <strong>{art.canonical_publisher || art.source_name}</strong>
          <span className="sp-mono">{art.provider}</span>
        </div>

        <div className="sp-row-time sp-mono">
          <span>{art.published_at_utc ? `${formatUtc(art.published_at_utc)} UTC` : 'Undated'}</span>
          {art.age_hours != null && <span>age: {art.age_hours.toFixed(1)}h</span>}
        </div>

        {showSentiment ? (
          <div
            className="sp-row-sent"
            aria-label={`FinBERT scores: positive ${posPct} percent, neutral ${neuPct} percent, negative ${negPct} percent`}
          >
            <span className={`sp-mono sp-row-score ${scoreTone}`}>{signedScore}</span>
            <span className="sp-tri" aria-hidden="true">
              <i style={{ width: `${posPct}%` }} className="p" />
              <i style={{ width: `${neuPct}%` }} className="u" />
              <i style={{ width: `${negPct}%` }} className="n" />
            </span>
          </div>
        ) : (
          <div className="sp-row-sent" />
        )}

        <div className="sp-row-w sp-mono">{weightStr}</div>

        <button
          type="button"
          className="sp-row-toggle"
          aria-expanded={open}
          aria-controls={`${rowId}-detail`}
          onClick={() => setOpen(!open)}
        >
          {open ? 'Less −' : 'Details +'}
        </button>
      </div>

      {open && (
        <div id={`${rowId}-detail`} className="sp-row-detail">
          {art.lead_text && <p className="sp-row-lead">{art.lead_text.slice(0, 500)}</p>}
          <div className="sp-mono sp-row-pct">
            +{posPct}% pos &middot; {neuPct}% neu &middot; &minus;{negPct}% neg
          </div>
        </div>
      )}
    </article>
  );
};
