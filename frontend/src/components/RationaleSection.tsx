import React from 'react';
import { PipelineRationale } from '../types';
import { Cpu, Newspaper, CheckCircle, Info } from 'lucide-react';

interface RationaleSectionProps {
  rationale: PipelineRationale;
}

export const RationaleSection: React.FC<RationaleSectionProps> = ({ rationale }) => {
  const facts = rationale?.observed_facts || [];
  const inferences = rationale?.inferences || [];
  const summary = rationale?.summary || 'No summary available.';

  const formatTime = (iso: string) => {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      return d.toISOString().replace('T', ' ').slice(11, 16) + ' UTC';
    } catch {
      return '';
    }
  };

  return (
    <div className="rationale-grid animate-fade-in" id="rationale-grid">
      {/* Column 1: Directly Observed Facts */}
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
            {facts.map((fact, idx) => (
              <li key={fact.fact_id || idx} className="fact-item">
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                  <CheckCircle size={15} style={{ color: 'var(--accent-cyan)', marginTop: '3px', flexShrink: 0 }} />
                  <span>{fact.statement}</span>
                </div>
                <div className="fact-meta">
                  <span className="fact-publisher">[{fact.source_publisher || 'Verified Source'}]</span>
                  <span>•</span>
                  <span>Published {formatTime(fact.published_at_utc)}</span>
                </div>
              </li>
            ))}
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
  );
};
