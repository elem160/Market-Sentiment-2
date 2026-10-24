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
});
