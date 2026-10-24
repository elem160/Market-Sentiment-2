import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getHealth, startAnalysis, getAnalysisResult, getHistory } from './api';

describe('Frontend API Service', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('getHealth', () => {
    it('requests /api/v1/health and returns health response', async () => {
      const mockHealthData = {
        status: 'HEALTHY',
        model_name: 'ProsusAI/finbert',
        device: 'cpu',
        db_connected: true,
        rss_providers: {
          yahoo: 'OK',
          seeking_alpha: 'OK',
        },
      };

      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockHealthData,
      } as Response);

      const data = await getHealth();

      expect(fetchSpy).toHaveBeenCalledTimes(1);
      expect(fetchSpy).toHaveBeenCalledWith('/api/v1/health');
      expect(data).toEqual(mockHealthData);
    });

    it('throws formatted error when /api/v1/health fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: async () => ({ detail: 'Database connection failed' }),
      } as Response);

      await expect(getHealth()).rejects.toThrow('Database connection failed');
    });
  });

  describe('startAnalysis', () => {
    it('sends POST to /api/v1/analyze with ticker and options', async () => {
      const mockResult = {
        run_id: 'test-run-123',
        ticker: 'AAPL',
        verdict: 'BUY',
        decision: 'BUY',
        confidence: 0.85,
        score: 0.65,
        articles: [],
        metrics: {
          total_articles: 5,
          raw_count: 5,
          filtered_count: 0,
          relevant_articles: 5,
          effective_articles: 4,
          distinct_publishers: 3,
          supporting_publishers: 3,
          opposing_publishers: 0,
          inferred_publishers: 0,
          conflict_ratio: 0.0,
          corroboration_ratio: 1.0,
          max_single_publisher_weight: 0.35,
          mean_impact_score: 0.65,
          median_impact_score: 0.65,
          min_impact_score: 0.5,
          max_impact_score: 0.8,
        },
        session: {
          session_type: 'REGULAR',
          as_of_utc: '2026-10-24T12:00:00Z',
          session_window_start_utc: '2026-10-24T00:00:00Z',
          session_window_end_utc: '2026-10-24T12:00:00Z',
        },
        rationale: ['Strong bullish momentum'],
        model_versions: {
          sentiment_model: 'ProsusAI/finbert',
          rule_version: 'v2.1',
        },
        data_status: 'FRESH',
        is_cacheable: true,
      };

      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResult,
      } as Response);

      const res = await startAnalysis('AAPL', true, false);

      expect(fetchSpy).toHaveBeenCalledWith('/api/v1/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker: 'AAPL',
          force_refresh: true,
          enable_llm: false,
        }),
      });
      expect(res.isCached).toBe(true);
      expect(res.result).toEqual(mockResult);
    });
  });

  describe('getAnalysisResult', () => {
    it('calls /api/v1/analysis/{run_id}', async () => {
      const mockResult = { run_id: 'run-xyz', ticker: 'MSFT' };
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => mockResult,
      } as Response);

      const res = await getAnalysisResult('run-xyz');
      expect(fetchSpy).toHaveBeenCalledWith('/api/v1/analysis/run-xyz');
      expect(res).toEqual(mockResult);
    });
  });

  describe('getHistory', () => {
    it('calls /api/v1/history with limit', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => [],
      } as Response);

      const res = await getHistory(10);
      expect(fetchSpy).toHaveBeenCalledWith('/api/v1/history?limit=10');
      expect(res).toEqual([]);
    });
  });
});
