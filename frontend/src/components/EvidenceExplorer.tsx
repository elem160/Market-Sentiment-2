import React, { useState } from 'react';
import { ScoredArticle } from '../types';
import { ExternalLink, Layers, Clock } from 'lucide-react';

interface EvidenceExplorerProps {
  articles: ScoredArticle[];
}

type FilterMode = 'ALL' | 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';

export const EvidenceExplorer: React.FC<EvidenceExplorerProps> = ({ articles }) => {
  const [filter, setFilter] = useState<FilterMode>('ALL');

  const articleList = articles || [];

  const filteredArticles = articleList.filter((art) => {
    const pos = art.finbert_positive ?? 0;
    const neg = art.finbert_negative ?? 0;

    if (filter === 'POSITIVE') return pos > 0.45 && pos > neg;
    if (filter === 'NEGATIVE') return neg > 0.45 && neg > pos;
    if (filter === 'NEUTRAL') return (art.finbert_neutral ?? 0) >= 0.5;
    return true;
  });

  const formatTimestamp = (iso: string) => {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      return d.toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
    } catch {
      return iso;
    }
  };

  return (
    <div className="glass-panel evidence-section animate-fade-in" id="evidence-explorer">
      <div className="evidence-controls">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Layers size={20} style={{ color: 'var(--accent-cyan)' }} />
          <h3 className="font-display" style={{ fontSize: '1.15rem', fontWeight: 700 }}>
            Session News Evidence ({articleList.length})
          </h3>
        </div>

        <div className="filter-tabs">
          <button
            className={`filter-tab ${filter === 'ALL' ? 'active' : ''}`}
            onClick={() => setFilter('ALL')}
          >
            All ({articleList.length})
          </button>
          <button
            className={`filter-tab ${filter === 'POSITIVE' ? 'active' : ''}`}
            onClick={() => setFilter('POSITIVE')}
          >
            Bullish
          </button>
          <button
            className={`filter-tab ${filter === 'NEGATIVE' ? 'active' : ''}`}
            onClick={() => setFilter('NEGATIVE')}
          >
            Bearish
          </button>
          <button
            className={`filter-tab ${filter === 'NEUTRAL' ? 'active' : ''}`}
            onClick={() => setFilter('NEUTRAL')}
          >
            Neutral
          </button>
        </div>
      </div>

      {filteredArticles.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
          No articles match the selected sentiment filter for this session window.
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
                  <a
                    href={art.canonical_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="article-title-link"
                  >
                    <span>{art.title}</span>
                    <ExternalLink size={14} style={{ opacity: 0.6, flexShrink: 0 }} />
                  </a>

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
                    {art.lead_text}
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
                    <span>{formatTimestamp(art.published_at_utc)}</span>
                  </div>
                  {art.final_weight !== undefined && (
                    <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)' }}>
                      Weight: {art.final_weight.toFixed(3)}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
