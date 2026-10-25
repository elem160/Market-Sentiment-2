import React from 'react';
import { PipelineRationale, ScoredArticle } from '../types';
import { formatUtc } from '../utils/time';

interface RationaleSectionProps {
  rationale: PipelineRationale;
  articles?: ScoredArticle[];
  llmSummary?: string | null;
  modelVersions?: Record<string, string>;
}

export const RationaleSection: React.FC<RationaleSectionProps> = ({
  rationale,
  articles = [],
  llmSummary,
  modelVersions,
}) => {
  const facts = rationale?.observed_facts || [];
  const inferences = rationale?.inferences || [];
  const summary = rationale?.summary || 'No summary available.';

  // Build article lookup map by article_id for fact citations
  const articlesMap = new Map<string, ScoredArticle>();
  for (const art of articles) {
    if (art.article_id) {
      articlesMap.set(art.article_id, art);
    }
  }

  return (
    <section
      id="rationale-section"
      className="sp-rationale"
      aria-label="Analysis method and rationale"
    >
      <div className="sp-sec-head">
        <span className="sp-sec-index">04</span>
        <span className="sp-label">Rationale</span>
        <h3 className="sp-display sp-sec-word">
          Why <em>this</em> call
        </h3>
      </div>

      {llmSummary && (
        <div id="llm-synthesis-card" className="sp-sheet sp-llm">
          <div className="sp-cell sp-cell--slab">
            <div className="sp-llm-head">
              <span className="sp-label">Catalyst synthesis</span>
              {modelVersions?.llm && (
                <span className="sp-tag font-mono">Model: {modelVersions.llm}</span>
              )}
            </div>
            <p className="sp-llm-body">{llmSummary}</p>
          </div>
        </div>
      )}

      <div id="rationale-grid" className="sp-sheet sp-rationale-grid">
        <div className="sp-cell sp-rationale-left">
          <span className="sp-label">Synthesized directional rationale</span>
          <div id="synthesized-rationale-text">
            <p className="sp-pull">{summary}</p>
            {inferences.length > 0 && (
              <ol className="sp-ledger">
                {inferences.map((inf, i) => (
                  <li key={i}>
                    <span className="sp-mono sp-ledger-n">{String(i + 1).padStart(2, '0')}</span>
                    <span>{inf}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
          <span className="sp-label sp-formula">Formula &amp; sentiment drivers</span>
        </div>

        <div className="sp-cell sp-rationale-right">
          <div className="sp-facts-head">
            <span className="sp-label">Observed &amp; reported facts</span>
            <span className="sp-tag">{facts.length} Statements</span>
          </div>

          {facts.length === 0 ? (
            <p className="sp-empty">
              No verified catalyst statements extracted for this session window.
            </p>
          ) : (
            <ul className="sp-facts" aria-label="Observed catalyst statements">
              {facts.map((fact, idx) => {
                const cited = fact.cited_article_id
                  ? articlesMap.get(fact.cited_article_id)
                  : undefined;

                const impactTone =
                  fact.impact === 'POSITIVE'
                    ? 'is-pos'
                    : fact.impact === 'NEGATIVE'
                    ? 'is-neg'
                    : 'is-flat';

                const impactPrefix =
                  fact.impact === 'POSITIVE' ? '▲ ' : fact.impact === 'NEGATIVE' ? '▼ ' : '■ ';

                return (
                  <li key={fact.cited_article_id || idx}>
                    <span className="sp-mono sp-fact-n">
                      {String(idx + 1).padStart(2, '0')}
                    </span>
                    <div className="sp-fact-content">
                      <p>{fact.statement}</p>
                      <div className="sp-fact-meta sp-mono">
                        {cited && (
                          <span className="sp-fact-pub">
                            {cited.canonical_publisher || cited.source_name}
                          </span>
                        )}
                        {cited?.published_at_utc && (
                          <span>{formatUtc(cited.published_at_utc)} UTC</span>
                        )}
                        {fact.catalyst_category && (
                          <span className="sp-tag sp-tag--cat">{fact.catalyst_category}</span>
                        )}
                        {fact.impact && (
                          <span className={`sp-impact ${impactTone}`}>
                            {impactPrefix}
                            {fact.impact}
                          </span>
                        )}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
};
