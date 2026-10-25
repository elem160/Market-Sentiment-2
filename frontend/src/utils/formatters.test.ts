import { describe, it, expect } from 'vitest';
import { formatTickerLabel } from './formatters';

describe('formatTickerLabel', () => {
  it('formats equities and ETFs with dollar prefix', () => {
    expect(formatTickerLabel('AAPL', 'EQUITY')).toBe('$AAPL');
    expect(formatTickerLabel('NVDA', 'equity')).toBe('$NVDA');
    expect(formatTickerLabel('SPY', 'ETF')).toBe('$SPY');
    expect(formatTickerLabel('QQQ', 'etf')).toBe('$QQQ');
  });

  it('preserves user-explicit dollar sign without doubling', () => {
    expect(formatTickerLabel('$AAPL', 'EQUITY')).toBe('$AAPL');
    expect(formatTickerLabel('$GOLD', 'EQUITY')).toBe('$GOLD');
    expect(formatTickerLabel('$SPY')).toBe('$SPY');
  });

  it('formats forex pairs without dollar prefix', () => {
    expect(formatTickerLabel('EUR/USD', 'FOREX')).toBe('EUR/USD');
    expect(formatTickerLabel('USD/JPY', 'FOREX')).toBe('USD/JPY');
    expect(formatTickerLabel('EURUSD', 'FOREX')).toBe('EURUSD');
  });

  it('formats commodities and futures without dollar prefix', () => {
    expect(formatTickerLabel('GC=F', 'COMMODITY')).toBe('GC=F');
    expect(formatTickerLabel('CL=F', 'FUTURES')).toBe('CL=F');
    expect(formatTickerLabel('ES=F', 'FUTURES')).toBe('ES=F');
  });

  it('formats cryptocurrencies without dollar prefix', () => {
    expect(formatTickerLabel('BTC-USD', 'CRYPTO')).toBe('BTC-USD');
    expect(formatTickerLabel('ETH-USD', 'CRYPTO')).toBe('ETH-USD');
    expect(formatTickerLabel('BTC/USD', 'crypto')).toBe('BTC/USD');
  });

  it('uses fallback heuristics when assetType is omitted', () => {
    expect(formatTickerLabel('AAPL')).toBe('$AAPL');
    expect(formatTickerLabel('MSFT')).toBe('$MSFT');
    expect(formatTickerLabel('EUR/USD')).toBe('EUR/USD');
    expect(formatTickerLabel('GC=F')).toBe('GC=F');
    expect(formatTickerLabel('BTC-USD')).toBe('BTC-USD');
  });

  it('handles empty or whitespace inputs gracefully', () => {
    expect(formatTickerLabel('')).toBe('');
    expect(formatTickerLabel('   ')).toBe('');
  });
});
