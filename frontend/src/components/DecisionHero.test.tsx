import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DecisionHero } from './DecisionHero';
import { AnalysisResult } from '../types';

function createHeroResult(
  decision: 'BUY' | 'SELL' | 'HOLD',
  distinctPubs: number,
  supportingPubs: number,
  holdReason: any = null
): AnalysisResult {
  return {
    run_id: 'hero-test-run',
    ticker: 'NVDA',
    company_name: 'NVIDIA Corporation',
    asset_type: 'EQUITY',
    decision,
    decision_confidence: decision === 'HOLD' ? 0.0 : 0.85,
    sentiment_score: decision === 'BUY' ? 0.6 : decision === 'SELL' ? -0.6 : 0.0,
    evidence_quality: 0.8,
    disclaimer: 'Research Only',
    pipeline_mode: 'HYBRID_FINBERT_LLM',
    cache_status: 'MISS',
    data_status: 'OK',
    hold_reason: holdReason,
    articles: [],
    warnings: [],
    metrics: {
      distinct_publishers: distinctPubs,
      supporting_publishers: supportingPubs,
      publishers_positive: decision === 'BUY' ? supportingPubs : 0,
      publishers_negative: decision === 'SELL' ? supportingPubs : 0,
      distinct_clusters: 2,
      directional_threshold: 0.15,
      articles_ingested: 5,
      articles_retained: 5,
      articles_excluded_total: 0,
      articles_deduplicated: 0,
      articles_scored_local: 5,
      articles_sent_to_llm: 5,
      completion_tokens: 0,
      prompt_tokens: 0,
      estimated_cost_usd: 0,
      excluded_missing_timestamp: 0,
      excluded_out_of_window: 0,
      stage_latencies: {},
      total_latency_ms: 100,
      total_sources: distinctPubs,
    },
    session: {
      session_type: 'REGULAR_HOURS',
      is_market_open: true,
      market_timezone: 'America/New_York',
      run_timestamp_utc: '2026-10-24T12:00:00Z',
      run_timestamp_et: '2026-10-24T08:00:00-04:00',
      window_start_utc: '2026-10-24T00:00:00Z',
      window_end_utc: '2026-10-24T12:00:00Z',
      window_start_et: '2026-10-23T20:00:00-04:00',
      window_end_et: '2026-10-24T08:00:00-04:00',
      window_duration_hours: 12.0,
    },
    rationale: {
      summary: 'Test summary',
      observed_facts: [],
      inferences: [],
    },
    model_versions: { sentiment_model: 'ProsusAI/finbert' },
    config_version: 'v2',
  };
}

describe('DecisionHero Corroboration Badge (Finding 2 Verification)', () => {
  it('renders Corroborated badge for BUY with >= 2 supporting publishers', () => {
    const result = createHeroResult('BUY', 3, 2);
    render(<DecisionHero result={result} />);

    expect(screen.getByText(/Corroborated/i)).toBeDefined();
    expect(screen.getByText(/2 Supporting Source\(s\)/i)).toBeDefined();
  });

  it('renders Single Publisher badge for BUY with 1 supporting publisher', () => {
    const result = createHeroResult('BUY', 1, 1);
    render(<DecisionHero result={result} />);

    expect(screen.getByText(/Single Publisher/i)).toBeDefined();
    expect(screen.queryByText(/^Corroborated$/i)).toBeNull();
  });

  it('renders Corroborated badge for SELL with >= 2 supporting publishers', () => {
    const result = createHeroResult('SELL', 4, 3);
    render(<DecisionHero result={result} />);

    expect(screen.getByText(/Corroborated/i)).toBeDefined();
    expect(screen.getByText(/3 Supporting Source\(s\)/i)).toBeDefined();
  });

  it('renders Single Publisher for SELL with 1 distinct publisher', () => {
    const result = createHeroResult('SELL', 1, 1);
    render(<DecisionHero result={result} />);

    expect(screen.getByText(/Single Publisher/i)).toBeDefined();
    expect(screen.queryByText(/^Corroborated$/i)).toBeNull();
  });

  it('renders Uncorroborated for SELL with 0 supporting publishers and multiple distinct publishers', () => {
    const result = createHeroResult('SELL', 2, 0);
    render(<DecisionHero result={result} />);

    expect(screen.getByText(/Uncorroborated/i)).toBeDefined();
    expect(screen.queryByText(/^Corroborated$/i)).toBeNull();
  });

  it('does NOT render Corroborated for HOLD even with high distinct publisher count', () => {
    const result = createHeroResult('HOLD', 5, 0, 'INSUFFICIENT_CORROBORATION');
    render(<DecisionHero result={result} />);

    expect(screen.getAllByText(/Insufficient Corroboration/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/^Corroborated$/i)).toBeNull();
  });

  it('renders Uncorroborated for HOLD when hold reason is not insufficient corroboration', () => {
    const result = createHeroResult('HOLD', 3, 0, 'CONFLICTING');
    render(<DecisionHero result={result} />);

    expect(screen.getByText(/Uncorroborated/i)).toBeDefined();
    expect(screen.queryByText(/^Corroborated$/i)).toBeNull();
  });

  it('formats equity ticker with dollar prefix', () => {
    const result = createHeroResult('BUY', 2, 2);
    result.ticker = 'AAPL';
    result.asset_type = 'EQUITY';
    render(<DecisionHero result={result} />);

    expect(screen.getByText('$AAPL')).toBeDefined();
  });

  it('formats forex and commodity tickers without dollar prefix', () => {
    const forexResult = createHeroResult('HOLD', 2, 0);
    forexResult.ticker = 'EUR/USD';
    forexResult.asset_type = 'FOREX';
    const { unmount } = render(<DecisionHero result={forexResult} />);

    expect(screen.getByText('EUR/USD')).toBeDefined();
    expect(screen.queryByText('$EUR/USD')).toBeNull();
    unmount();

    const commodityResult = createHeroResult('BUY', 3, 2);
    commodityResult.ticker = 'GC=F';
    commodityResult.asset_type = 'COMMODITY';
    render(<DecisionHero result={commodityResult} />);

    expect(screen.getByText('GC=F')).toBeDefined();
    expect(screen.queryByText('$GC=F')).toBeNull();
  });

  it('sets data-len="long" on ticker symbol for a 12-character ticker', () => {
    const result = createHeroResult('BUY', 2, 2);
    result.ticker = 'VERYLONGTICK';
    result.asset_type = 'FOREX';
    const { container } = render(<DecisionHero result={result} />);

    const tickerEl = container.querySelector('#result-ticker-symbol');
    expect(tickerEl?.getAttribute('data-len')).toBe('long');
  });

  it('computes gauge marker left as 0%, 50%, and 100% for scores -1, 0, and +1', () => {
    const rMin = createHeroResult('SELL', 2, 2);
    rMin.sentiment_score = -1.0;
    const { container: cMin, unmount: uMin } = render(<DecisionHero result={rMin} />);
    const markerMin = cMin.querySelector('.sp-gauge-marker') as HTMLElement;
    expect(markerMin.style.left).toBe('0%');
    uMin();

    const rMid = createHeroResult('HOLD', 2, 0);
    rMid.sentiment_score = 0.0;
    const { container: cMid, unmount: uMid } = render(<DecisionHero result={rMid} />);
    const markerMid = cMid.querySelector('.sp-gauge-marker') as HTMLElement;
    expect(markerMid.style.left).toBe('50%');
    uMid();

    const rMax = createHeroResult('BUY', 2, 2);
    rMax.sentiment_score = 1.0;
    const { container: cMax } = render(<DecisionHero result={rMax} />);
    const markerMax = cMax.querySelector('.sp-gauge-marker') as HTMLElement;
    expect(markerMax.style.left).toBe('100%');
  });

  it('applies composite tone class is-pos, is-neg, and is-flat at 0.26, -0.26, and 0.25', () => {
    const rPos = createHeroResult('BUY', 2, 2);
    rPos.sentiment_score = 0.26;
    const { container: cPos, unmount: uPos } = render(<DecisionHero result={rPos} />);
    expect(cPos.querySelector('#result-composite-score')?.classList.contains('is-pos')).toBe(true);
    uPos();

    const rNeg = createHeroResult('SELL', 2, 2);
    rNeg.sentiment_score = -0.26;
    const { container: cNeg, unmount: uNeg } = render(<DecisionHero result={rNeg} />);
    expect(cNeg.querySelector('#result-composite-score')?.classList.contains('is-neg')).toBe(true);
    uNeg();

    const rFlat = createHeroResult('HOLD', 2, 0);
    rFlat.sentiment_score = 0.25;
    const { container: cFlat } = render(<DecisionHero result={rFlat} />);
    expect(cFlat.querySelector('#result-composite-score')?.classList.contains('is-flat')).toBe(true);
  });
});
