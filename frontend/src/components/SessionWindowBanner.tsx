import React from 'react';
import { SessionWindow } from '../types';
import { Calendar, Clock, Globe } from 'lucide-react';
import { formatEt, formatUtc } from '../utils/time';

interface SessionWindowBannerProps {
  session?: SessionWindow;
  window?: SessionWindow; // backwards compatible
}

export const SessionWindowBanner: React.FC<SessionWindowBannerProps> = ({ session: sessionProp, window: windowProp }) => {
  const session = sessionProp || windowProp;
  if (!session) return null;

  const formatSessionName = (raw: string) => {
    return (raw || 'UNKNOWN').replace(/_/g, ' ');
  };

  return (
    <div className="session-banner animate-fade-in" id="session-window-banner">
      <div className="session-info">
        <span className="session-badge">{formatSessionName(session.session_type)}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Calendar size={14} style={{ color: 'var(--text-muted)' }} />
          <span>Market Status: <strong style={{ color: session.is_market_open ? '#10b981' : '#f59e0b' }}>
            {session.is_market_open ? 'OPEN (RTH)' : 'CLOSED'}
          </strong></span>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '18px', flexWrap: 'wrap' }}>
        <div className="session-time-text" title="Active news filter boundary in Eastern Time">
          <Clock size={13} style={{ display: 'inline', marginRight: '4px', verticalAlign: '-1px' }} />
          <span>ET: </span>
          <span style={{ color: 'var(--text-primary)' }}>
            {formatEt(session.window_start_utc)} &rarr; {formatEt(session.window_end_utc)}
          </span>
        </div>

        <div className="session-time-text" title="Active news filter boundary in Coordinated Universal Time">
          <Globe size={13} style={{ display: 'inline', marginRight: '4px', verticalAlign: '-1px' }} />
          <span>UTC: </span>
          <span style={{ color: 'var(--text-primary)' }}>
            {formatUtc(session.window_start_utc)} &rarr; {formatUtc(session.window_end_utc)}
          </span>
        </div>

        <div className="badge badge-neutral font-mono">
          {(session.window_duration_hours || 0).toFixed(1)}h lookback
        </div>

        <div className="badge badge-neutral font-mono" title="Pipeline execution timestamp">
          Run: {formatUtc(session.run_timestamp_utc)}
        </div>
      </div>
    </div>
  );
};

