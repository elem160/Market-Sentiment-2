import React from 'react';
import { PipelineRationale, ScoredArticle } from '../types';
import { Cpu, Newspaper, CheckCircle, Info, Sparkles } from 'lucide-react';
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

  const getImpactBadgeClass = (impact?: string | null) => {
    switch (impact) {
      case 'POSITIVE':
        return 'badge-buy';
      case 'NEGATIVE':
        return 'badge-sell';
      default:
        return 'badge-hold';
    }
  };

  return (
    <div className="rationale-section animate-fade-in" id="rationale-section" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* LLM Catalyst Synthesis Card (if available) */}
      {llmSummary && (
        <div className="glass-panel section-card" id="llm-synthesis-card" style={{ borderLeft: '3px solid var(--accent-indigo)' }}>
          <div className="section-header">
            <div className="section-title">
              <Sparkles size={18} style={{ color: 'var(--accent-indigo)' }} />
              <span>LLM Catalyst Synthesis</span>
            </div>
            {modelVersions?.llm && (
              <span className="badge badge-neutral font-mono" style={{ fontSize: '0.75rem' }}>
                Model: {modelVersions.llm}
              </span>
            )}
          </div>
          <div style={{ fontSize: '0.92rem', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            {llmSummary}
          </div>
        </div>
      )}

      <div className="rationale-grid" id="rationale-grid">
        {/* Column 1: Directly Observed Facts with cited article linkage */}
        <div className="glass-panel section-card">
          <div className="section-header">
            <div className="section-title">
              <Newspaper size={18} style={{ color: 'var(--accent-cyan)' }} />
              <span>Observed & Reported Facts</span>
            </div>
            <span className="badge badge-neutral font-mono">
              {facts.length} Statements
            </span>
          </div>

          {facts.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem', padding: '16px 0' }}>
              No verified catalyst statements extracted for this session window.
            </div>
          ) : (
            <ul className="facts-list">
              {facts.map((fact, idx) => {
                const cited = fact.cited_article_id ? articlesMap.get(fact.cited_article_id) : undefined;
                return (
                  <li key={fact.cited_article_id || idx} className="fact-item">
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                      <CheckCircle size={15} style={{ color: 'var(--accent-cyan)', marginTop: '3px', flexShrink: 0 }} />
                      <span>{fact.statement}</span>
                    </div>
                    <div className="fact-meta" style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginTop: '6px' }}>
                      {cited && (
                        <span className="badge badge-neutral" style={{ fontSize: '0.72rem', color: 'var(--accent-cyan)' }}>
                          {cited.canonical_publisher || cited.source_name}
                        </span>
                      )}
                      {cited?.published_at_utc && (
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          {formatUtc(cited.published_at_utc)} UTC
                        </span>
                      )}
                      {fact.catalyst_category && (
                        <span className="badge badge-neutral" style={{ fontSize: '0.72rem' }}>
                          {fact.catalyst_category}
                        </span>
                      )}
                      {fact.impact && (
                        <span className={`badge ${getImpactBadgeClass(fact.impact)}`} style={{ fontSize: '0.72rem' }}>
                          {fact.impact}
                        </span>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Column 2: Synthesized Rationale & Inferences */}
        <div className="glass-panel section-card">
          <div className="section-header">
            <div className="section-title">
              <Cpu size={18} style={{ color: 'var(--accent-indigo)' }} />
              <span>Synthesized Directional Rationale</span>
            </div>
            <span className="badge badge-neutral">Formula & Sentiment Drivers</span>
          </div>

          <div className="rationale-body" id="synthesized-rationale-text">
            <div style={{ fontWeight: 600, marginBottom: '12px', color: 'var(--text-primary)' }}>
              {summary}
            </div>

            {inferences.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', borderTop: '1px solid var(--border-subtle)', paddingTop: '12px' }}>
                {inferences.map((inf, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '0.88rem', color: 'var(--text-secondary)' }}>
                    <Info size={14} style={{ color: 'var(--accent-cyan)', marginTop: '4px', flexShrink: 0 }} />
                    <span>{inf}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
