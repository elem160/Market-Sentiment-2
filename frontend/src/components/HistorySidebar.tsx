import React, { useEffect, useState } from 'react';
import { HistoryItem, DecisionVerdict } from '../types';
import { getHistory } from '../services/api';
import { formatTickerLabel } from '../utils/formatters';
import { History, ArrowRight, Clock } from 'lucide-react';

interface HistorySidebarProps {
  onSelectRun: (runId: string) => void;
  refreshTrigger: number;
}

export const HistorySidebar: React.FC<HistorySidebarProps> = ({ onSelectRun, refreshTrigger }) => {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [isOpen, setIsOpen] = useState<boolean>(false);

  useEffect(() => {
    getHistory(15).then(setHistory).catch(() => {});
  }, [refreshTrigger]);

  const getVerdictBadge = (v: DecisionVerdict | string) => {
    switch (v) {
      case 'BUY':
        return <span className="badge badge-buy font-mono">BUY</span>;
      case 'SELL':
        return <span className="badge badge-sell font-mono">SELL</span>;
      case 'HOLD':
      default:
        return <span className="badge badge-hold font-mono">HOLD</span>;
    }
  };

  const formatTimeWithTz = (iso?: string | null) => {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return '';
      return `${new Intl.DateTimeFormat('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
        timeZone: 'UTC',
      }).format(d)} UTC`;
    } catch {
      return '';
    }
  };

  if (history.length === 0) return null;

  return (
    <section className="glass-panel" style={{ padding: '16px 20px' }} id="recent-history-panel" aria-label="Recent analysis history">
      <button
        type="button"
        className="history-toggle-btn"
        aria-expanded={isOpen}
        aria-controls="recent-history-grid"
        onClick={() => setIsOpen(!isOpen)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          color: 'inherit',
          fontFamily: 'inherit',
          minHeight: '44px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.9rem', fontWeight: 600 }}>
          <History size={16} style={{ color: 'var(--color-accent)' }} aria-hidden="true" />
          <span>Recent Analysis Queries ({history.length})</span>
        </div>
        <span style={{ fontSize: '0.8rem', color: 'var(--color-accent)' }}>
          {isOpen ? 'Collapse ▲' : 'Expand ▼'}
        </span>
      </button>

      {isOpen && (
        <div
          id="recent-history-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: '10px',
            marginTop: '14px',
          }}
        >
          {history.map((item) => (
            <button
              type="button"
              key={item.run_id}
              className="history-item-row"
              onClick={() => onSelectRun(item.run_id)}
              aria-label={`View analysis for ${item.ticker}`}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span className="font-display" style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--color-ink)' }}>
                  {formatTickerLabel(item.ticker, item.asset_type)}
                </span>
                {getVerdictBadge(item.decision)}
                {item.asset_type && item.asset_type !== 'EQUITY' && (
                  <span className="badge badge-neutral font-mono">
                    {item.asset_type}
                  </span>
                )}
                {item.data_status === 'NO_FRESH_NEWS' && (
                  <span className="badge badge-hold font-mono">
                    No News
                  </span>
                )}
                {item.data_status === 'NO_RELEVANT_NEWS' && (
                  <span className="badge badge-hold font-mono">
                    No Relevant
                  </span>
                )}
                {item.data_status === 'DEGRADED' && (
                  <span className="badge badge-sell font-mono">
                    Degraded
                  </span>
                )}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', color: 'var(--color-ink-muted)' }}>
                <Clock size={11} aria-hidden="true" />
                <span>{formatTimeWithTz(item.run_timestamp_utc)}</span>
                <ArrowRight size={13} style={{ color: 'var(--color-accent)' }} aria-hidden="true" />
              </div>
            </button>
          ))}
        </div>
      )}
    </section>
  );
};
