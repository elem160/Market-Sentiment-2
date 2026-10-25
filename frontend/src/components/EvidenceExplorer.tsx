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
    <div className="glass-panel evidence-section animate-fade-in" id="evidence-explorer">
      <div className="evidence-controls">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Layers size={20} style={{ color: 'var(--accent-cyan)' }} />
          <h3 className="font-display" style={{ fontSize: '1.15rem', fontWeight: 700 }}>
            Session News Evidence ({retainedArticles.length} Retained)
          </h3>
        </div>

        <div className="filter-tabs">
          <button
            className={`filter-tab ${filter === 'ALL' ? 'active' : ''}`}
            onClick={() => setFilter('ALL')}
          >
            All ({retainedArticles.length})
          </button>
          <button
            className={`filter-tab ${filter === 'POSITIVE' ? 'active' : ''}`}
            onClick={() => setFilter('POSITIVE')}
          >
            Bullish ({bullishCount})
          </button>
          <button
            className={`filter-tab ${filter === 'NEGATIVE' ? 'active' : ''}`}
            onClick={() => setFilter('NEGATIVE')}
          >
            Bearish ({bearishCount})
          </button>
          <button
            className={`filter-tab ${filter === 'NEUTRAL' ? 'active' : ''}`}
            onClick={() => setFilter('NEUTRAL')}
          >
            Neutral ({neutralCount})
          </button>
        </div>
      </div>

      {filteredArticles.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
          No retained articles match the selected sentiment filter for this session window.
        </div>
      ) : (
        <div className="article-list">
          {filteredArticles.map((art) => {
            const pos = art.finbert_positive ?? 0.1;
            const neg = art.finbert_negative ?? 0.1;
            const neu = art.finbert_neutral ?? 0.8;

            return (
              <div key={art.article_id} className="article-card">
                <div className="article-card-header">
                  {art.canonical_url ? (
                    <a
                      href={art.canonical_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="article-title-link"
                    >
                      <span>{art.title}</span>
                      <ExternalLink size={14} style={{ opacity: 0.6, flexShrink: 0 }} />
                    </a>
                  ) : (
                    <span className="article-title-text" style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      {art.title}
                    </span>
                  )}

                  <div className="finbert-breakdown-bar">
                    <span className="score-pos">Pos: {(pos * 100).toFixed(0)}%</span>
                    <span>|</span>
                    <span className="score-neu">Neu: {(neu * 100).toFixed(0)}%</span>
                    <span>|</span>
                    <span className="score-neg">Neg: {(neg * 100).toFixed(0)}%</span>
                  </div>
                </div>

                {art.lead_text && (
                  <p style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {art.lead_text.slice(0, 500)}
                  </p>
                )}

                <div className="article-meta-row">
                  <span className="badge badge-neutral" style={{ color: 'var(--accent-cyan)' }}>
                    {art.canonical_publisher || art.source_name}
                  </span>
                  <span className="badge badge-neutral font-mono" style={{ fontSize: '0.72rem' }}>
                    {art.provider}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <Clock size={12} />
                    <span>{art.published_at_utc ? `${formatUtc(art.published_at_utc)} UTC` : 'Undated'}</span>
                  </div>
                  {art.age_hours !== undefined && art.age_hours !== null && (
                    <span className="badge badge-neutral font-mono" style={{ fontSize: '0.72rem' }}>
                      age at run: {art.age_hours.toFixed(1)}h
                    </span>
                  )}
                  {art.effective_weight !== undefined && art.effective_weight !== null ? (
                    <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--accent-cyan)' }}>
                      Eff. Weight: {art.effective_weight.toFixed(3)}
                    </span>
                  ) : art.final_weight !== undefined && art.final_weight !== null ? (
                    <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)' }}>
                      Weight: {art.final_weight.toFixed(3)}
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {excludedArticles.length > 0 && (
        <div className="excluded-articles-wrapper" style={{ marginTop: '24px', borderTop: '1px solid var(--border-subtle)', paddingTop: '16px' }}>
          <button
            type="button"
            className="btn-link"
            aria-expanded={showExcluded}
            aria-controls="excluded-articles-list"
            onClick={() => setShowExcluded(!showExcluded)}
          >
            {showExcluded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            <span>Excluded Articles ({totalExcludedCount} total)</span>
          </button>

          {showExcluded && (
            <div id="excluded-articles-list" style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {Object.entries(excludedByReason).map(([reason, groupArticles]) => {
                const totalForReason = excludedCountsMap[reason] ?? groupArticles.length;
                return (
                  <div key={reason} className="excluded-group">
                    <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f59e0b', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className="badge badge-hold" style={{ textTransform: 'uppercase' }}>
                        {reason.replace(/_/g, ' ')}
                      </span>
                      <span>
                        (Showing {groupArticles.length} of {totalForReason})
                      </span>
                    </div>

                    <div className="article-list" style={{ opacity: 0.9 }}>
                      {groupArticles.map((art) => (
                        <div key={art.article_id} className="article-card" style={{ borderLeft: '3px solid #f59e0b' }}>
                          <div className="article-card-header">
                            {art.canonical_url ? (
                              <a
                                href={art.canonical_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="article-title-link"
                              >
                                <span>{art.title}</span>
                                <ExternalLink size={14} style={{ opacity: 0.6, flexShrink: 0 }} />
                              </a>
                            ) : (
                              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                                {art.title}
                              </span>
                            )}
                          </div>

                          {art.lead_text && (
                            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                              {art.lead_text.slice(0, 500)}
                            </p>
                          )}

                          <div className="article-meta-row">
                            <span className="badge badge-neutral" style={{ color: 'var(--accent-cyan)' }}>
                              {art.canonical_publisher || art.source_name}
                            </span>
                            <span className="badge badge-neutral font-mono" style={{ fontSize: '0.72rem' }}>
                              {art.provider}
                            </span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <Clock size={12} />
                              <span>{art.published_at_utc ? `${formatUtc(art.published_at_utc)} UTC` : 'Undated'}</span>
                            </div>
                            {art.age_hours !== undefined && art.age_hours !== null && (
                              <span className="badge badge-neutral font-mono" style={{ fontSize: '0.72rem' }}>
                                age at run: {art.age_hours.toFixed(1)}h
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
