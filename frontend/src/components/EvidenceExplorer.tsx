import React, { useState } from 'react';
import { ScoredArticle, PipelineMetrics } from '../types';
import { EvidenceRow } from './EvidenceRow';

interface EvidenceExplorerProps {
  articles: ScoredArticle[];
  metrics?: PipelineMetrics;
}

type FilterMode = 'ALL' | 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';

export const EvidenceExplorer: React.FC<EvidenceExplorerProps> = ({ articles, metrics }) => {
  const [filter, setFilter] = useState<FilterMode>('ALL');
  const [showExcluded, setShowExcluded] = useState<boolean>(false);

  const threshold = metrics?.directional_threshold ?? 0.15;
  const articleList = articles || [];
  const retainedArticles = articleList.filter((art) => !art.exclusion_reason);
  const excludedArticles = articleList.filter((art) => Boolean(art.exclusion_reason));

  const bullishCount = retainedArticles.filter(
    (art) => (art.finbert_directional_score ?? 0) >= threshold
  ).length;
  const bearishCount = retainedArticles.filter(
    (art) => (art.finbert_directional_score ?? 0) <= -threshold
  ).length;
  const neutralCount = retainedArticles.filter(
    (art) => Math.abs(art.finbert_directional_score ?? 0) < threshold
  ).length;

  const filteredArticles = retainedArticles.filter((art) => {
    const score = art.finbert_directional_score ?? 0;
    if (filter === 'POSITIVE') return score >= threshold;
    if (filter === 'NEGATIVE') return score <= -threshold;
    if (filter === 'NEUTRAL') return Math.abs(score) < threshold;
    return true;
  });

  // Group excluded articles by reason
  const excludedByReason: Record<string, ScoredArticle[]> = {};
  for (const art of excludedArticles) {
    const reason = art.exclusion_reason || 'UNSPECIFIED';
    if (!excludedByReason[reason]) {
      excludedByReason[reason] = [];
    }
    excludedByReason[reason].push(art);
  }

  const totalExcludedCount = metrics?.articles_excluded_total ?? excludedArticles.length;
  const excludedCountsMap = metrics?.excluded_counts ?? {};

  return (
    <section id="evidence-explorer" className="sp-evidence" aria-label="Evidence explorer">
      <div className="sp-sec-head">
        <span className="sp-sec-index">05</span>
        <span className="sp-label">Evidence</span>
        <h3 className="sp-display sp-sec-word">
          Evi<em>dence</em>
        </h3>
        <p className="sp-label sp-evidence-subtitle">
          Session News Evidence ({retainedArticles.length} Retained)
        </p>
      </div>

      <div className="sp-filter" role="tablist" aria-label="Sentiment filters">
        <button
          type="button"
          role="tab"
          aria-selected={filter === 'ALL'}
          className={`filter-tab sp-filter-tab ${filter === 'ALL' ? 'active' : ''}`}
          onClick={() => setFilter('ALL')}
        >
          All ({retainedArticles.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={filter === 'POSITIVE'}
          className={`filter-tab sp-filter-tab ${filter === 'POSITIVE' ? 'active' : ''}`}
          onClick={() => setFilter('POSITIVE')}
        >
          Bullish ({bullishCount})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={filter === 'NEGATIVE'}
          className={`filter-tab sp-filter-tab ${filter === 'NEGATIVE' ? 'active' : ''}`}
          onClick={() => setFilter('NEGATIVE')}
        >
          Bearish ({bearishCount})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={filter === 'NEUTRAL'}
          className={`filter-tab sp-filter-tab ${filter === 'NEUTRAL' ? 'active' : ''}`}
          onClick={() => setFilter('NEUTRAL')}
        >
          Neutral ({neutralCount})
        </button>
      </div>

      {filteredArticles.length === 0 ? (
        <div className="sp-empty-filter sp-cell--hatch">
          <p>No retained articles match the selected sentiment filter for this session window.</p>
        </div>
      ) : (
        <div id="evidence-articles-list" className="sp-ledger-table" role="region" aria-label="Filtered articles">
          <div className="sp-ledger-head sp-label" aria-hidden="true">
            <span>#</span>
            <span>Headline</span>
            <span>Source</span>
            <span>Time</span>
            <span>Sentiment</span>
            <span>Weight</span>
            <span />
          </div>
          {filteredArticles.map((art, i) => (
            <EvidenceRow key={art.article_id || i} art={art} index={i} showSentiment={true} />
          ))}
        </div>
      )}

      {excludedArticles.length > 0 && (
        <div className="sp-excluded-wrap">
          <button
            type="button"
            className="sp-excl-toggle"
            aria-expanded={showExcluded}
            aria-controls="excluded-articles-list"
            onClick={() => setShowExcluded(!showExcluded)}
          >
            <span>Excluded from scoring ({totalExcludedCount} total)</span>
            <span className="sp-mono">{showExcluded ? '−' : '+'}</span>
          </button>

          {showExcluded && (
            <div id="excluded-articles-list" className="sp-excluded-list sp-sheet sp-cell--hatch">
              {Object.entries(excludedByReason).map(([reason, groupArticles]) => {
                const totalForReason = excludedCountsMap[reason] ?? groupArticles.length;
                return (
                  <div key={reason} className="sp-excluded-group">
                    <div className="sp-excluded-group-head">
                      <span className="sp-tag sp-tag--hatch">
                        {reason.replace(/_/g, ' ')}
                      </span>
                      <span className="sp-mono sp-excluded-count">
                        (Showing {groupArticles.length} of {totalForReason})
                      </span>
                    </div>

                    <div className="sp-excluded-rows">
                      {groupArticles.map((art, idx) => (
                        <EvidenceRow
                          key={art.article_id || idx}
                          art={art}
                          index={idx}
                          showSentiment={false}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </section>
  );
};
