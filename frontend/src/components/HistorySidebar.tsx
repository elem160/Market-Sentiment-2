import React, { useEffect, useState } from 'react';
import { HistoryItem, DecisionVerdict } from '../types';
import { getHistory } from '../services/api';
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

  const getVerdictBadge = (v: DecisionVerdict) => {
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

  const formatTime = (iso?: string | null) => {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return '';
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  if (history.length === 0) return null;

  return (
    <div className="glass-panel" style={{ padding: '16px 20px' }} id="recent-history-panel">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: 'pointer',
        }}
        onClick={() => setIsOpen(!isOpen)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.9rem', fontWeight: 600 }}>
          <History size={16} style={{ color: 'var(--accent-cyan)' }} />
          <span>Recent Analysis Queries ({history.length})</span>
        </div>
        <span style={{ fontSize: '0.8rem', color: 'var(--accent-cyan)' }}>
          {isOpen ? 'Collapse ▲' : 'Expand ▼'}
        </span>
      </div>

      {isOpen && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: '10px',
            marginTop: '14px',
          }}
        >
          {history.map((item) => (
            <div
              key={item.run_id}
              className="history-item-row"
              onClick={() => onSelectRun(item.run_id)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span className="font-display" style={{ fontWeight: 800, fontSize: '1rem' }}>
                  ${item.ticker}
                </span>
                {getVerdictBadge(item.decision)}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                <Clock size={11} />
                <span>{formatTime(item.run_timestamp_utc)}</span>
                <ArrowRight size={13} style={{ color: 'var(--accent-cyan)' }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
