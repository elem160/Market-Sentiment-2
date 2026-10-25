import React, { useState } from 'react';
import { Search, Zap, RefreshCw, Sparkles } from 'lucide-react';

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
    <section className="search-section animate-fade-in" id="search-section" aria-label="Asset analysis input">
      <div className="sp-field-group">
        <label htmlFor="ticker-search-input" className="sp-field-label">
          Asset symbol
        </label>
        <form onSubmit={handleSubmit} className="search-form">
          <div className="search-input-wrapper">
            <Search size={20} className="search-icon" aria-hidden="true" />
            <input
              id="ticker-search-input"
              type="text"
              className="search-input"
              placeholder="ENTER TICKER (E.G. NVDA, EUR/USD, GC=F, BTC-USD, AAPL)..."
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              maxLength={16}
              disabled={isLoading}
              aria-describedby="ticker-format-helper"
            />
          </div>
          <button
            id="run-analysis-btn"
            type="submit"
            className="btn btn-primary"
            disabled={isLoading || !ticker.trim()}
          >
            {isLoading ? (
              <>
                <RefreshCw size={18} className="animate-spin-slow" aria-hidden="true" />
                <span>ANALYZING...</span>
              </>
            ) : (
              <>
                <Zap size={18} aria-hidden="true" />
                <span>RUN SENTIMENT</span>
              </>
            )}
          </button>
        </form>
        <span id="ticker-format-helper" className="sp-helper-text">
          Supported instruments: US equities, ETFs, Forex pairs (EUR/USD), Commodities/Futures (GC=F), and Cryptocurrencies (BTC-USD).
        </span>
      </div>

      <div className="search-options">
        <div className="quick-chips-group" role="group" aria-label="Multi-asset quick chips">
          <span className="quick-chips-label">Quick chips:</span>
          {POPULAR_TICKERS.map((chip) => (
            <button
              key={chip.value}
              type="button"
              id={`quick-chip-${chip.value.toLowerCase().replace(/[^a-z0-9]/g, '-')}`}
              className="btn-chip"
              onClick={() => handleChipClick(chip.value)}
              disabled={isLoading}
            >
              {chip.label}
            </button>
          ))}
        </div>

        <div className="toggles-group" role="group" aria-label="Run options">
          <span className="sp-options-legend">Run options:</span>
          <label className="custom-checkbox" title="Bypasses the session cache to query live feeds immediately">
            <input
              id="force-refresh-checkbox"
              type="checkbox"
              checked={forceRefresh}
              onChange={(e) => setForceRefresh(e.target.checked)}
              disabled={isLoading}
            />
            <RefreshCw size={14} aria-hidden="true" />
            <span>Force Fresh Run</span>
          </label>

          <label className="custom-checkbox" title="Activates LLM catalyst verification via Nemotron 3 Ultra">
            <input
              id="enable-llm-checkbox"
              type="checkbox"
              checked={enableLlm}
              onChange={(e) => setEnableLlm(e.target.checked)}
              disabled={isLoading}
            />
            <Sparkles size={14} aria-hidden="true" />
            <span>Nemotron 3 Catalyst Filter</span>
          </label>
        </div>
      </div>
    </section>
  );
};
