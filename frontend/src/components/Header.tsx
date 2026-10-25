import React, { useState, useEffect } from 'react';

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
      {/* Top Permanent Non-Advisory Legal Disclaimer Strip */}
      <div id="legal-disclaimer-strip" className="sp-legal" role="region" aria-label="Research Disclaimer">
        <span className="sp-tag sp-tag--accent">Research only</span>
        <span>
          <strong>RESEARCH &amp; SENTIMENT EXPERIMENT ONLY:</strong> Not investment advice or solicitation. Directional classifications (BUY/HOLD/SELL) are algorithmic heuristic models based purely on current-session public news sentiment.
        </span>
      </div>

      {/* Sticky Top Navigation */}
      <header className="sp-nav">
        <div className="sp-nav-brand">
          <h1 className="sp-display sp-nav-title">Sentiment Pulse</h1>
          <span className="sp-label sp-nav-sub">Real-Time Market Sentiment Intelligence</span>
        </div>

        <div className="sp-nav-clocks" role="group" aria-label="Session clocks">
          <div className="sp-clock" title="Eastern Time (NYSE/NASDAQ Market Anchor)">
            <span className="sp-label">ET</span>
            <span id="header-clock-et" className="sp-mono" aria-label={`Eastern Time: ${timeEt}`}>
              {timeEt}
            </span>
          </div>
          <div className="sp-clock" title="Coordinated Universal Time">
            <span className="sp-label">UTC</span>
            <span id="header-clock-utc" className="sp-mono" aria-label={`UTC: ${timeUtc}`}>
              {timeUtc}
            </span>
          </div>
        </div>
      </header>
    </>
  );
};
