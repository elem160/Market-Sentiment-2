import React from 'react';

export const LandingHero: React.FC = () => {
  return (
    // eslint-disable-next-line jsx-a11y/no-redundant-roles
    <section className="sp-landing sp-sheet" role="region" aria-label="Welcome and usage introduction">
      <div className="sp-cell sp-landing-title">
        <span className="sp-label">Session-anchored news sentiment</span>
        <h2 className="sp-display">
          Live Market <em>Sentiment</em> <span className="sp-amp">&amp;</span> Catalyst Intelligence
        </h2>
      </div>

      <div className="sp-cell sp-landing-copy">
        <p>
          Enter any US equity, ETF, forex pair (e.g. EUR/USD), commodity future (e.g. GC=F), or crypto asset to execute session-anchored news ingestion, FinBERT neural scoring, and corroboration synthesis.
        </p>
      </div>

      <dl className="sp-cell sp-spec" aria-label="System status and parameters">
        <div className="sp-spec-row sp-spec-row--highlight">
          <dt>Scoring model</dt>
          <dd>FinBERT</dd>
        </div>
        <div className="sp-spec-row">
          <dt>Recency half-life</dt>
          <dd>14 h</dd>
        </div>
        <div className="sp-spec-row">
          <dt>Corroboration gate</dt>
          <dd>≥ 2 publishers</dd>
        </div>
        <div className="sp-spec-row">
          <dt>Result cache</dt>
          <dd>15 min</dd>
        </div>
        <div className="sp-spec-row">
          <dt>Instruments</dt>
          <dd>Equity · ETF · FX · Futures · Crypto</dd>
        </div>
      </dl>
    </section>
  );
};
