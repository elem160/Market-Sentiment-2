import React from 'react';
import { SessionWindow } from '../types';
import { Calendar, Clock, Globe } from 'lucide-react';

interface SessionWindowBannerProps {
  window: SessionWindow;
}

export const SessionWindowBanner: React.FC<SessionWindowBannerProps> = ({ window }) => {
  const formatSessionName = (raw: string) => {
    return (raw || 'UNKNOWN').replace(/_/g, ' ');
  };

  const formatDate = (iso: string) => {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      return d.toISOString().replace('T', ' ').slice(0, 19);
    } catch {
      return iso;
    }
  };

  return (
    <div className="session-banner animate-fade-in" id="session-window-banner">
      <div className="session-info">
        <span className="session-badge">{formatSessionName(window.session_type)}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Calendar size={14} style={{ color: 'var(--text-muted)' }} />
          <span>Market Status: <strong style={{ color: window.is_market_open ? '#10b981' : '#f59e0b' }}>
            {window.is_market_open ? 'OPEN (RTH)' : 'CLOSED'}
          </strong></span>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '18px', flexWrap: 'wrap' }}>
        <div className="session-time-text" title="Active news filter boundary in Eastern Time">
          <Clock size={13} style={{ display: 'inline', marginRight: '4px', verticalAlign: '-1px' }} />
          <span>ET: </span>
          <span style={{ color: 'var(--text-primary)' }}>{formatDate(window.window_start_et)} &rarr; {formatDate(window.window_end_et)}</span>
        </div>

        <div className="session-time-text" title="Active news filter boundary in Coordinated Universal Time">
          <Globe size={13} style={{ display: 'inline', marginRight: '4px', verticalAlign: '-1px' }} />
          <span>UTC: </span>
          <span style={{ color: 'var(--text-primary)' }}>{formatDate(window.window_start_utc)} &rarr; {formatDate(window.window_end_utc)}</span>
        </div>

        <div className="badge badge-neutral font-mono">
          {(window.window_duration_hours || 0).toFixed(1)}h lookback
        </div>

        <div className="badge badge-neutral font-mono" title="Pipeline execution timestamp">
          Run: {formatDate(window.run_timestamp_utc)}
        </div>
      </div>
    </div>
  );
};
