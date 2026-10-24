import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { App } from './App';
import * as api from './services/api';
import { AnalysisResult } from './types';

function createMockResult(ticker: string, runId: string, verdict: 'BUY' | 'SELL' | 'HOLD' = 'BUY'): AnalysisResult {
  return {
    run_id: runId,
    ticker,
    company_name: `${ticker} Corp`,
    asset_type: 'EQUITY',
    decision: verdict,
    decision_confidence: 0.9,
    sentiment_score: 0.7,
    evidence_quality: 0.8,
    disclaimer: 'Research & Sentiment Experiment Only',
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
      total_latency_ms: 120,
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
      summary: 'Solid thesis for investment',
      observed_facts: [],
      inferences: ['Positive catalyst confirmed'],
    },
    model_versions: {
      sentiment_model: 'ProsusAI/finbert',
      rule_version: 'v2.1',
    },
    config_version: 'v2',
  };
}

describe('App Stale Request Prevention (Finding 3 Regression)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();

    vi.spyOn(api, 'getHealth').mockResolvedValue({
      status: 'HEALTHY',
      app_env: 'test',
      database_status: 'CONNECTED',
      finbert_status: 'READY',
      llm_configured: true,
    });

    vi.spyOn(api, 'getHistory').mockResolvedValue([
      {
        run_id: 'hist-run-1',
        ticker: 'MSFT',
        company_name: 'Microsoft Corporation',
        asset_type: 'EQUITY',
        decision: 'BUY',
        decision_confidence: 0.95,
        evidence_quality: 0.9,
        sentiment_score: 0.8,
        data_status: 'OK',
        run_timestamp_utc: '2026-10-24T10:00:00Z',
      },
    ]);
  });

  it('ignores older pending search request when user selects a historical run', async () => {
    let resolveSearchPromise!: (val: api.StartAnalysisResponse) => void;
    const searchPromise = new Promise<api.StartAnalysisResponse>((resolve) => {
      resolveSearchPromise = resolve;
    });

    vi.spyOn(api, 'startAnalysis').mockReturnValue(searchPromise);

    const histResult = createMockResult('MSFT', 'hist-run-1');
    vi.spyOn(api, 'getAnalysisResult').mockResolvedValue(histResult);

    const { container } = render(<App />);

    // Wait for history sidebar to render
    await waitFor(() => {
      expect(screen.getByText(/Recent Analysis Queries/i)).toBeDefined();
    });

    // Expand history panel
    const historyHeader = screen.getByText(/Recent Analysis Queries/i);
    fireEvent.click(historyHeader);

    await waitFor(() => {
      expect(screen.getByText('$MSFT')).toBeDefined();
    });

    // Trigger search for SLOW
    const searchInput = container.querySelector('#ticker-search-input') as HTMLInputElement;
    const form = container.querySelector('form.search-form') as HTMLFormElement;

    fireEvent.change(searchInput, { target: { value: 'SLOW' } });
    fireEvent.submit(form);

    // Verify search is initiated (stepper is visible)
    await waitFor(() => {
      expect(screen.getByText(/Validating ticker symbol SLOW/i)).toBeDefined();
    });

    // While search is still pending, user selects $MSFT from history
    const historyItem = screen.getByText('$MSFT');
    const historyRow = historyItem.closest('.history-item-row') || historyItem;
    fireEvent.click(historyRow);

    // Verify historical result is displayed and loading stepper is gone
    await waitFor(() => {
      expect(screen.getByText('Solid thesis for investment')).toBeDefined();
      expect(screen.queryByText(/Validating ticker symbol SLOW/i)).toBeNull();
    });

    // Now resolve the slow search
    const slowResult = createMockResult('SLOW', 'slow-run-99');
    await act(async () => {
      resolveSearchPromise({
        isCached: true,
        result: slowResult,
      });
    });

    // Assert: The app MUST NOT replace the selected MSFT result with SLOW
    expect(screen.queryByText('slow-run-99')).toBeNull();
    expect(container.querySelector('#result-ticker-symbol')?.textContent).toBe('$MSFT');
    expect(screen.getByText('Solid thesis for investment')).toBeDefined();
  });

  it('ignores job events from older search request when user selects a historical run', async () => {
    let capturedHandlers: api.JobEventHandlers | null = null;
    const unsubscribeMock = vi.fn();

    vi.spyOn(api, 'startAnalysis').mockResolvedValue({
      isCached: false,
      jobId: 'job-1',
      maxWaitSeconds: 30,
    });

    vi.spyOn(api, 'subscribeToJob').mockImplementation((_jobId, handlers) => {
      capturedHandlers = handlers as api.JobEventHandlers;
      return unsubscribeMock;
    });

    const histResult = createMockResult('MSFT', 'hist-run-1');
    vi.spyOn(api, 'getAnalysisResult').mockResolvedValue(histResult);

    const { container } = render(<App />);

    // Wait for history sidebar to render
    await waitFor(() => {
      expect(screen.getByText(/Recent Analysis Queries/i)).toBeDefined();
    });

    const historyHeader = screen.getByText(/Recent Analysis Queries/i);
    fireEvent.click(historyHeader);

    await waitFor(() => {
      expect(screen.getByText('$MSFT')).toBeDefined();
    });

    // 1. Search JOB1 -> starts job
    const searchInput = container.querySelector('#ticker-search-input') as HTMLInputElement;
    const form = container.querySelector('form.search-form') as HTMLFormElement;

    fireEvent.change(searchInput, { target: { value: 'JOB1' } });
    fireEvent.submit(form);

    await waitFor(() => {
      expect(api.subscribeToJob).toHaveBeenCalled();
      expect(capturedHandlers).not.toBeNull();
    });

    // 2. While job is active, user selects $MSFT from history
    const historyItem = screen.getByText('$MSFT');
    const historyRow = historyItem.closest('.history-item-row') || historyItem;
    fireEvent.click(historyRow);

    await waitFor(() => {
      expect(screen.getByText('Solid thesis for investment')).toBeDefined();
    });

    // 3. Now simulate JOB1 emitting a late completion event
    const staleResult = createMockResult('JOB1', 'stale-job-1');
    await act(async () => {
      capturedHandlers?.onComplete(staleResult);
    });

    // 4. Assert: MSFT is still displayed; stale JOB1 result was ignored
    expect(screen.queryByText('stale-job-1')).toBeNull();
    expect(container.querySelector('#result-ticker-symbol')?.textContent).toBe('$MSFT');
  });
});
