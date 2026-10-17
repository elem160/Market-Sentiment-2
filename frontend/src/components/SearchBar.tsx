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
  const [ticker, setTicker] = useState<string>(activeTicker || '');
  const [forceRefresh, setForceRefresh] = useState<boolean>(false);
  const [enableLlm, setEnableLlm] = useState<boolean>(true);

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
    <div className="glass-panel search-section animate-fade-in" id="search-section">
      <form onSubmit={handleSubmit} className="search-form">
        <div className="search-input-wrapper">
          <Search size={22} className="search-icon" />
          <input
            id="ticker-search-input"
            type="text"
            className="search-input"
            placeholder="ENTER TICKER (E.G. NVDA, EUR/USD, GC=F, BTC-USD, AAPL)..."
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            maxLength={16}
            disabled={isLoading}
            autoFocus
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
              <RefreshCw size={18} className="animate-spin-slow" />
              <span>ANALYZING...</span>
            </>
          ) : (
            <>
              <Zap size={18} />
              <span>RUN SENTIMENT</span>
            </>
          )}
        </button>
      </form>

      <div className="search-options">
        <div className="quick-chips-group">
          <span className="quick-chips-label">MULTI-ASSET QUICK CHIPS:</span>
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

        <div className="toggles-group">
          <label className="custom-checkbox" title="Bypasses the 15-minute SQLite cache to query live feeds immediately">
            <input
              id="force-refresh-checkbox"
              type="checkbox"
              checked={forceRefresh}
              onChange={(e) => setForceRefresh(e.target.checked)}
              disabled={isLoading}
            />
            <RefreshCw size={14} />
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
            <Sparkles size={14} style={{ color: '#a855f7' }} />
            <span>Nemotron 3 Catalyst Filter</span>
          </label>
        </div>
      </div>
    </div>
  );
};

