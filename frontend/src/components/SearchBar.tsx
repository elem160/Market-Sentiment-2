import React, { useState } from 'react';
import { RefreshCw, Sparkles } from 'lucide-react';

interface SearchBarProps {
  onSearch: (ticker: string, forceRefresh: boolean, enableLlm: boolean) => void;
  isLoading: boolean;
  activeTicker?: string;
}

const POPULAR_TICKERS = [
  { label: '$NVDA', value: 'NVDA' },
  { label: '$AAPL', value: 'AAPL' },
  { label: 'EUR/USD', value: 'EUR/USD' },
  { label: 'USD/JPY', value: 'USD/JPY' },
  { label: 'GC=F (Gold)', value: 'GC=F' },
  { label: 'BTC-USD', value: 'BTC-USD' },
];

export const SearchBar: React.FC<SearchBarProps> = ({ onSearch, isLoading, activeTicker }) => {
  const [prevActiveTicker, setPrevActiveTicker] = useState(activeTicker);
  const [ticker, setTicker] = useState<string>(activeTicker || '');
  const [forceRefresh, setForceRefresh] = useState<boolean>(false);
  const [enableLlm, setEnableLlm] = useState<boolean>(true);

  if (activeTicker !== prevActiveTicker) {
    setPrevActiveTicker(activeTicker);
    setTicker(activeTicker || '');
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanTicker = ticker.trim().toUpperCase();
    if (cleanTicker && !isLoading) {
      onSearch(cleanTicker, forceRefresh, enableLlm);
    }
  };

  const handleChipClick = (t: string) => {
    setTicker(t);
    if (!isLoading) {
      onSearch(t, forceRefresh, enableLlm);
    }
  };

  return (
    <section id="search-section" className="sp-input sp-sheet" aria-label="Asset analysis input">
      <div className="sp-cell sp-sec-head">
        <span className="sp-sec-index">01</span>
        <span className="sp-label">Input</span>
        <span className="sp-label">Run an analysis</span>
      </div>

      <div className="sp-cell sp-input-main">
        <label htmlFor="ticker-search-input" className="sp-label">
          Asset symbol
        </label>
        <form className="search-form sp-input-form" onSubmit={handleSubmit}>
          <input
            id="ticker-search-input"
            type="text"
            className="sp-input-field"
            placeholder="ENTER TICKER"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            maxLength={16}
            disabled={isLoading}
            aria-describedby="ticker-format-helper"
          />
          <button
            id="run-analysis-btn"
            type="submit"
            className="sp-btn sp-btn--xl"
            disabled={isLoading || !ticker.trim()}
          >
            {isLoading ? (
              <>
                <RefreshCw size={18} aria-hidden="true" />
                <span>ANALYZING...</span>
              </>
            ) : (
              <>
                <span>RUN SENTIMENT</span>
                <span aria-hidden="true">&rarr;</span>
              </>
            )}
          </button>
        </form>
        <span id="ticker-format-helper" className="sp-helper">
          Supported instruments: US equities, ETFs, Forex pairs (EUR/USD), Commodities/Futures (GC=F), and Cryptocurrencies (BTC-USD).
        </span>
      </div>

      <div className="sp-chip-strip" role="group" aria-label="Multi-asset quick chips">
        <span className="sp-label sp-chip-label">Quick chips</span>
        {POPULAR_TICKERS.map((chip) => (
          <button
            key={chip.value}
            type="button"
            id={`quick-chip-${chip.value.toLowerCase().replace(/[^a-z0-9]/g, '-')}`}
            className="sp-chip"
            onClick={() => handleChipClick(chip.value)}
            disabled={isLoading}
          >
            {chip.label}
          </button>
        ))}
      </div>

      <div className="sp-options" role="group" aria-label="Run options">
        <span className="sp-label">Run options</span>
        <label className="sp-toggle" title="Bypasses the session cache to query live feeds immediately">
          <input
            id="force-refresh-checkbox"
            type="checkbox"
            checked={forceRefresh}
            onChange={(e) => setForceRefresh(e.target.checked)}
            disabled={isLoading}
          />
          <span className="sp-toggle-box" aria-hidden="true" />
          <RefreshCw size={14} aria-hidden="true" />
          <span>Force Fresh Run</span>
        </label>

        <label className="sp-toggle" title="Activates LLM catalyst verification via Nemotron 3 Ultra">
          <input
            id="enable-llm-checkbox"
            type="checkbox"
            checked={enableLlm}
            onChange={(e) => setEnableLlm(e.target.checked)}
            disabled={isLoading}
          />
          <span className="sp-toggle-box" aria-hidden="true" />
          <Sparkles size={14} aria-hidden="true" />
          <span>Nemotron 3 Catalyst Filter</span>
        </label>
      </div>
    </section>
  );
};
