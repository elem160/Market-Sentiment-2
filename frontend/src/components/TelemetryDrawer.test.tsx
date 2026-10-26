import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TelemetryDrawer } from './TelemetryDrawer';
import { AnalysisResult } from '../types';

function createTelemetryResult(overrides: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    run_id: 'telem-run-1',
    ticker: 'AAPL',
    company_name: 'Apple Inc.',
    asset_type: 'EQUITY',
    decision: 'BUY',
    decision_confidence: 0.9,
    sentiment_score: 0.7,
    evidence_quality: 0.85,
    disclaimer: 'Research Only',
    pipeline_mode: 'HYBRID_FINBERT_LLM',
    cache_status: 'MISS',
    data_status: 'OK',
    articles: [],
    warnings: [],
    metrics: {
      distinct_publishers: 3,
      supporting_publishers: 3,
      publishers_positive: 3,
      publishers_negative: 0,
      distinct_clusters: 2,
      directional_threshold: 0.15,
      articles_ingested: 10,
      articles_retained: 8,
      articles_excluded_total: 2,
      articles_deduplicated: 1,
      articles_scored_local: 8,
      articles_sent_to_llm: 5,
      completion_tokens: 150,
      prompt_tokens: 420,
      estimated_cost_usd: 0.0012,
      excluded_missing_timestamp: 0,
      excluded_out_of_window: 1,
      stage_latencies: {},
      total_latency_ms: 145,
      total_sources: 3,
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
      summary: 'Solid earnings results drive sentiment.',
      observed_facts: [],
      inferences: [],
    },
    model_versions: {
      finbert: 'v1.4',
      llm: 'gemini-1.5-pro',
      sentiment_model: 'ProsusAI/finbert',
      rule_version: 'v2.1',
    },
    config_version: 'v2',
    ...overrides,
  };
}

describe('TelemetryDrawer (Spec Sheet v2)', () => {
  it('renders container with id="pipeline-telemetry-strip" and title cell', () => {
    const result = createTelemetryResult();
    const { container } = render(<TelemetryDrawer result={result} />);

    expect(container.querySelector('#pipeline-telemetry-strip')).not.toBeNull();
    expect(screen.getByText('06')).toBeDefined();
    expect(screen.getByText('Run log')).toBeDefined();
  });

  it('renders execution latency and ingestion metrics', () => {
    const result = createTelemetryResult();
    render(<TelemetryDrawer result={result} />);

    expect(screen.getByText(/Execution Latency/i)).toBeDefined();
    expect(screen.getByText('145 ms')).toBeDefined();

    expect(screen.getByText(/Ingestion & Filtering/i)).toBeDefined();
    expect(screen.getByText(/10 Ingested → 8 Retained \(2 Excluded\)/)).toBeDefined();
  });

  it('renders LLM estimated cost and model engine info', () => {
    const result = createTelemetryResult();
    render(<TelemetryDrawer result={result} />);

    expect(screen.getByText(/Estimated LLM Cost/i)).toBeDefined();
    expect(screen.getByText(/\$0\.0012 USD \(420 tok\)/)).toBeDefined();

    expect(screen.getByText(/Model Engine/i)).toBeDefined();
    expect(screen.getByText('FinBERT: v1.4 | LLM: gemini-1.5-pro')).toBeDefined();
  });

  it('renders cache status cell with is-hit class on HIT', () => {
    const hitResult = createTelemetryResult({ cache_status: 'HIT' });
    const { container } = render(<TelemetryDrawer result={hitResult} />);

    const hitCell = container.querySelector('.sp-runlog-cell.is-hit');
    expect(hitCell).not.toBeNull();
    expect(hitCell?.textContent).toContain('Cache Status');
    expect(hitCell?.textContent).toContain('HIT');
  });

  it('renders cache status cell without is-hit on MISS', () => {
    const missResult = createTelemetryResult({ cache_status: 'MISS' });
    const { container } = render(<TelemetryDrawer result={missResult} />);

    expect(container.querySelector('.sp-runlog-cell.is-hit')).toBeNull();
    expect(screen.getByText('MISS')).toBeDefined();
  });
});
