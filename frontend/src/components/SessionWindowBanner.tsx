import React from 'react';
import { SessionWindow } from '../types';
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

  const isMarketOpen = Boolean(session.is_market_open);

  return (
    <aside
      id="session-window-banner"
      className="sp-context sp-sheet"
      aria-label="Market session and news temporal window"
    >
      <div className="sp-cell">
        <span className="sp-label">Session</span>
        <strong className="sp-display sp-ctx-big">{formatSessionName(session.session_type)}</strong>
      </div>

      <div className={`sp-cell ${!isMarketOpen ? 'sp-cell--hatch' : ''}`}>
        <span className="sp-label">Market status</span>
        <strong className={`sp-ctx-status ${isMarketOpen ? 'is-open' : 'is-closed'}`}>
          {isMarketOpen ? (
            <>
              <span className="sp-status-sq sp-status-sq--open" aria-hidden="true" />
              <span>OPEN (RTH)</span>
            </>
          ) : (
            <>
              <span className="sp-status-sq sp-status-sq--closed" aria-hidden="true" />
              <span>CLOSED</span>
            </>
          )}
        </strong>
      </div>

      <div className="sp-cell" title="Active news filter boundary in Eastern Time">
        <span className="sp-label">Window &middot; ET</span>
        <span className="sp-mono">
          {formatEt(session.window_start_utc)} &rarr; {formatEt(session.window_end_utc)}
        </span>
      </div>

      <div className="sp-cell" title="Active news filter boundary in Coordinated Universal Time">
        <span className="sp-label">Window &middot; UTC</span>
        <span className="sp-mono">
          {formatUtc(session.window_start_utc)} &rarr; {formatUtc(session.window_end_utc)}
        </span>
      </div>

      <div className="sp-cell">
        <span className="sp-label">Lookback</span>
        <span className="sp-mono sp-ctx-num">{(session.window_duration_hours || 0).toFixed(1)}h</span>
      </div>

      <div className="sp-cell" title="Pipeline execution timestamp">
        <span className="sp-label">Run</span>
        <span className="sp-mono">{formatUtc(session.run_timestamp_utc)}</span>
      </div>
    </aside>
  );
};
