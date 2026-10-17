import React, { useState, useEffect } from 'react';
import { Activity, Clock, ShieldAlert } from 'lucide-react';

export const Header: React.FC = () => {
  const [timeUtc, setTimeUtc] = useState<string>('');
  const [timeEt, setTimeEt] = useState<string>('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTimeUtc(now.toUTCString().slice(17, 25) + ' UTC');
      setTimeEt(
        new Intl.DateTimeFormat('en-US', {
          timeZone: 'America/New_York',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        }).format(now) + ' ET'
      );
    };

    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <>
      {/* Top Permanent Non-Advisory Legal Disclaimer */}
      <div className="disclaimer-strip" id="legal-disclaimer-strip">
        <ShieldAlert size={16} />
        <span>
          <strong>RESEARCH & SENTIMENT EXPERIMENT ONLY:</strong> Not investment advice or solicitation. Directional classifications (BUY/HOLD/SELL) are algorithmic heuristic models based purely on current-session public news sentiment.
        </span>
      </div>

      <header className="app-header">
        <div className="header-brand">
          <div className="brand-icon">
            <Activity size={24} />
          </div>
          <div>
            <h1 className="brand-title">SENTIMENT PULSE</h1>
            <div className="brand-subtitle">Real-Time Market Sentiment Intelligence</div>
          </div>
        </div>

        <div className="header-clocks">
          <div className="clock-item">
            <span className="clock-dot"></span>
            <Clock size={13} />
            <span id="header-clock-et">{timeEt}</span>
          </div>
          <div className="clock-item">
            <span className="clock-dot" style={{ background: '#38bdf8', boxShadow: '0 0 6px #38bdf8' }}></span>
            <span id="header-clock-utc">{timeUtc}</span>
          </div>
        </div>
      </header>
    </>
  );
};
