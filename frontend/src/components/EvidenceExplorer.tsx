import React, { useState } from 'react';
import { ScoredArticle, PipelineMetrics } from '../types';
import { ExternalLink, Layers, Clock, ChevronDown, ChevronUp } from 'lucide-react';
import { formatUtc } from '../utils/time';

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

  const bullishCount = retainedArticles.filter((art) => (art.finbert_directional_score ?? 0) >= threshold).length;
  const bearishCount = retainedArticles.filter((art) => (art.finbert_directional_score ?? 0) <= -threshold).length;
  const neutralCount = retainedArticles.filter((art) => Math.abs(art.finbert_directional_score ?? 0) < threshold).length;

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
    <section className="evidence-section animate-fade-in" id="evidence-explorer" aria-label="Evidence explorer">
      <div className="evidence-controls">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Layers size={18} style={{ color: 'var(--color-accent)' }} aria-hidden="true" />
          <h3 className="font-display" style={{ fontSize: '1.15rem', fontWeight: 600, color: 'var(--color-ink)' }}>
            Session News Evidence ({retainedArticles.length} Retained)
          </h3>
        </div>

        <div className="filter-tabs" role="tablist" aria-label="Sentiment filters">
          <button
            type="button"
            role="tab"
            aria-selected={filter === 'ALL'}
            className={`filter-tab ${filter === 'ALL' ? 'active' : ''}`}
            onClick={() => setFilter('ALL')}
          >
            All ({retainedArticles.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={filter === 'POSITIVE'}
            className={`filter-tab ${filter === 'POSITIVE' ? 'active' : ''}`}
            onClick={() => setFilter('POSITIVE')}
          >
            Bullish ({bullishCount})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={filter === 'NEGATIVE'}
            className={`filter-tab ${filter === 'NEGATIVE' ? 'active' : ''}`}
            onClick={() => setFilter('NEGATIVE')}
          >
            Bearish ({bearishCount})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={filter === 'NEUTRAL'}
            className={`filter-tab ${filter === 'NEUTRAL' ? 'active' : ''}`}
            onClick={() => setFilter('NEUTRAL')}
          >
            Neutral ({neutralCount})
          </button>
        </div>
      </div>

      {filteredArticles.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '36px 16px', color: 'var(--color-ink-muted)' }}>
          No retained articles match the selected sentiment filter for this session window.
        </div>
      ) : (
        <div className="article-list" role="region" aria-label="Filtered articles">
          {filteredArticles.map((art) => {
            const pos = art.finbert_positive ?? 0.1;
            const neg = art.finbert_negative ?? 0.1;
            const neu = art.finbert_neutral ?? 0.8;

            return (
              <article key={art.article_id} className="article-card">
                <div className="article-card-header">
                  {art.canonical_url ? (
                    <a
                      href={art.canonical_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="article-title-link"
                    >
                      <span>{art.title}</span>
                      <ExternalLink size={13} style={{ opacity: 0.6, flexShrink: 0 }} aria-hidden="true" />
                    </a>
                  ) : (
                    <span className="article-title-text">
                      {art.title}
                    </span>
                  )}

                  <div className="finbert-breakdown-bar" aria-label={`FinBERT scores: positive ${(pos * 100).toFixed(0)} percent, neutral ${(neu * 100).toFixed(0)} percent, negative ${(neg * 100).toFixed(0)} percent`}>
                    <span className="score-pos">+{(pos * 100).toFixed(0)}%</span>
                    <span style={{ color: 'var(--color-line)' }}>|</span>
                    <span className="score-neu">{(neu * 100).toFixed(0)}%</span>
                    <span style={{ color: 'var(--color-line)' }}>|</span>
                    <span className="score-neg">-{(neg * 100).toFixed(0)}%</span>
                  </div>
                </div>

                {art.lead_text && (
                  <p style={{ fontSize: '0.86rem', color: 'var(--color-ink-soft)', lineHeight: 1.55 }}>
                    {art.lead_text.slice(0, 500)}
                  </p>
                )}

                <div className="article-meta-row">
                  <span className="badge badge-neutral" style={{ color: 'var(--color-accent)' }}>
                    {art.canonical_publisher || art.source_name}
                  </span>
                  <span className="badge badge-neutral font-mono">
                    {art.provider}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Clock size={12} aria-hidden="true" />
                    <span>{art.published_at_utc ? `${formatUtc(art.published_at_utc)} UTC` : 'Undated'}</span>
                  </div>
                  {art.age_hours !== undefined && art.age_hours !== null && (
                    <span className="badge badge-neutral font-mono">
                      age: {art.age_hours.toFixed(1)}h
                    </span>
                  )}
                  {art.effective_weight !== undefined && art.effective_weight !== null ? (
                    <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-data)', fontSize: '0.78rem', color: 'var(--color-ink-soft)' }}>
                      Eff. Weight: {art.effective_weight.toFixed(3)}
                    </span>
                  ) : art.final_weight !== undefined && art.final_weight !== null ? (
                    <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-data)', fontSize: '0.78rem', color: 'var(--color-ink-soft)' }}>
                      Weight: {art.final_weight.toFixed(3)}
                    </span>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {excludedArticles.length > 0 && (
        <div className="excluded-articles-wrapper">
          <button
            type="button"
            className="btn-link"
            aria-expanded={showExcluded}
            aria-controls="excluded-articles-list"
            onClick={() => setShowExcluded(!showExcluded)}
          >
            {showExcluded ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
            <span>Excluded from scoring ({totalExcludedCount} total)</span>
          </button>

          {showExcluded && (
            <div id="excluded-articles-list" style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {Object.entries(excludedByReason).map(([reason, groupArticles]) => {
                const totalForReason = excludedCountsMap[reason] ?? groupArticles.length;
                return (
                  <div key={reason} className="excluded-group">
                    <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--color-caution-ink)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className="badge badge-hold" style={{ textTransform: 'uppercase' }}>
                        {reason.replace(/_/g, ' ')}
                      </span>
                      <span>
                        (Showing {groupArticles.length} of {totalForReason})
                      </span>
                    </div>

                    <div className="article-list" style={{ opacity: 0.9 }}>
                      {groupArticles.map((art) => (
                        <article key={art.article_id} className="article-card" style={{ borderLeft: '3px solid var(--color-caution)' }}>
                          <div className="article-card-header">
                            {art.canonical_url ? (
                              <a
                                href={art.canonical_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="article-title-link"
                              >
                                <span>{art.title}</span>
                                <ExternalLink size={13} style={{ opacity: 0.6, flexShrink: 0 }} aria-hidden="true" />
                              </a>
                            ) : (
                              <span className="article-title-text">
                                {art.title}
                              </span>
                            )}
                          </div>

                          {art.lead_text && (
                            <p style={{ fontSize: '0.84rem', color: 'var(--color-ink-muted)', lineHeight: 1.45 }}>
                              {art.lead_text.slice(0, 500)}
                            </p>
                          )}

                          <div className="article-meta-row">
                            <span className="badge badge-neutral" style={{ color: 'var(--color-accent)' }}>
                              {art.canonical_publisher || art.source_name}
                            </span>
                            <span className="badge badge-neutral font-mono">
                              {art.provider}
                            </span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <Clock size={12} aria-hidden="true" />
                              <span>{art.published_at_utc ? `${formatUtc(art.published_at_utc)} UTC` : 'Undated'}</span>
                            </div>
                            {art.age_hours !== undefined && art.age_hours !== null && (
                              <span className="badge badge-neutral font-mono">
                                age: {art.age_hours.toFixed(1)}h
                              </span>
                            )}
                          </div>
                        </article>
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
