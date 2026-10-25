import React, { useEffect, useState } from 'react';
import { HistoryItem, DecisionVerdict } from '../types';
import { getHistory } from '../services/api';
import { formatTickerLabel } from '../utils/formatters';
import { ArrowRight } from 'lucide-react';

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
        return <span className="sp-tag sp-tag--buy font-mono">BUY</span>;
      case 'SELL':
        return <span className="sp-tag sp-tag--sell font-mono">SELL</span>;
      case 'HOLD':
      default:
        return <span className="sp-tag sp-tag--hatch font-mono">HOLD</span>;
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
    <section
      id="recent-history-panel"
      className="sp-history sp-sheet"
      aria-label="Recent analysis history"
    >
      <button
        type="button"
        className="history-toggle-btn sp-history-toggle"
        aria-expanded={isOpen}
        aria-controls="recent-history-grid"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="sp-history-toggle-left">
          <span className="sp-sec-index">07</span>
          <span className="sp-history-title">
            Recent Analysis Queries ({history.length})
          </span>
        </div>
        <span className="sp-mono">{isOpen ? 'Collapse −' : 'Expand +'}</span>
      </button>

      {isOpen && (
        <div id="recent-history-grid" className="sp-history-list">
          {history.map((item) => (
            <button
              type="button"
              key={item.run_id}
              className="history-item-row sp-hrow"
              onClick={() => onSelectRun(item.run_id)}
              aria-label={`View analysis for ${item.ticker}`}
            >
              <span className="sp-hrow-ticker sp-display">
                {formatTickerLabel(item.ticker, item.asset_type)}
              </span>

              <div className="sp-hrow-tags">
                {getVerdictBadge(item.decision)}
                {item.asset_type && item.asset_type !== 'EQUITY' && (
                  <span className="sp-tag font-mono">{item.asset_type}</span>
                )}
                {item.data_status === 'NO_FRESH_NEWS' && (
                  <span className="sp-tag sp-tag--hatch font-mono">No News</span>
                )}
                {item.data_status === 'NO_RELEVANT_NEWS' && (
                  <span className="sp-tag sp-tag--hatch font-mono">No Relevant</span>
                )}
                {item.data_status === 'DEGRADED' && (
                  <span className="sp-tag sp-tag--sell font-mono">Degraded</span>
                )}
              </div>

              <div />

              <span className="sp-mono sp-hrow-time">
                {formatTimeWithTz(item.run_timestamp_utc)}
              </span>

              <span className="sp-hrow-arrow">
                <ArrowRight size={14} aria-hidden="true" />
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
};
