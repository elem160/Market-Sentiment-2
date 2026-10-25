/**
 * Formatting utilities for multi-asset ticker displays and numerical metrics.
 */

/**
 * Formats a ticker symbol for display.
 * US equities and ETFs are prefixed with a dollar sign (e.g. '$AAPL', '$NVDA', '$SPY').
 * Non-equity assets (Forex, Commodities, Crypto, Futures) are shown without a dollar sign,
 * preserving user-explicit '$' if already provided.
 *
 * @param ticker Raw ticker symbol (e.g. 'AAPL', 'EUR/USD', 'GC=F', 'BTC-USD', '$GOLD')
 * @param assetType Optional asset classification from backend ('EQUITY', 'ETF', 'FOREX', 'COMMODITY', 'CRYPTO', 'FUTURES')
 * @returns Cleanly formatted ticker display string
 */
export function formatTickerLabel(ticker: string, assetType?: string): string {
  if (!ticker) return '';
  const trimmed = ticker.trim();
  if (!trimmed) return '';
  if (trimmed.startsWith('$')) {
    return trimmed;
  }

  const normalizedType = assetType?.toUpperCase();
  if (normalizedType === 'EQUITY' || normalizedType === 'ETF') {
    return `$${trimmed}`;
  }

  if (
    normalizedType === 'FOREX' ||
    normalizedType === 'COMMODITY' ||
    normalizedType === 'CRYPTO' ||
    normalizedType === 'FUTURES'
  ) {
    return trimmed;
  }

  // Fallback heuristic when assetType is omitted:
  // Forex ('EUR/USD', 'USD/JPY'), Futures/Commodities ('GC=F', 'CL=F'), Crypto pairs ('BTC-USD', 'ETH-USD')
  if (trimmed.includes('/') || trimmed.includes('=') || trimmed.includes('-')) {
    return trimmed;
  }

  // Default to US equity representation
  return `$${trimmed}`;
}
