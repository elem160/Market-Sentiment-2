import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { HistorySidebar } from './HistorySidebar';
import * as api from '../services/api';
import { HistoryItem } from '../types';

describe('HistorySidebar (Spec Sheet v2)', () => {
  const mockHistory: HistoryItem[] = [
    {
      run_id: 'hist-1',
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
    {
      run_id: 'hist-2',
      ticker: 'EUR/USD',
      company_name: 'Euro / US Dollar',
      asset_type: 'FOREX',
      decision: 'HOLD',
      decision_confidence: 0.0,
      evidence_quality: 0.5,
      sentiment_score: 0.0,
      data_status: 'NO_FRESH_NEWS',
      run_timestamp_utc: '2026-10-24T09:30:00Z',
    },
    {
      run_id: 'hist-3',
      ticker: 'TSLA',
      company_name: 'Tesla Inc',
      asset_type: 'EQUITY',
      decision: 'SELL',
      decision_confidence: 0.85,
      evidence_quality: 0.75,
      sentiment_score: -0.6,
      data_status: 'DEGRADED',
      run_timestamp_utc: '2026-10-24T08:15:00Z',
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when history is empty', async () => {
    vi.spyOn(api, 'getHistory').mockResolvedValue([]);
    const handleSelect = vi.fn();
    const { container } = render(
      <HistorySidebar onSelectRun={handleSelect} refreshTrigger={0} />
    );

    await waitFor(() => {
      expect(container.firstChild).toBeNull();
    });
  });

  it('renders #recent-history-panel and collapsed toggle when history is available', async () => {
    vi.spyOn(api, 'getHistory').mockResolvedValue(mockHistory);
    const handleSelect = vi.fn();
    const { container } = render(
      <HistorySidebar onSelectRun={handleSelect} refreshTrigger={0} />
    );

    await waitFor(() => {
      expect(container.querySelector('#recent-history-panel')).not.toBeNull();
    });

    const toggleBtn = container.querySelector('.history-toggle-btn');
    expect(toggleBtn).not.toBeNull();
    expect(toggleBtn?.getAttribute('aria-expanded')).toBe('false');
    expect(toggleBtn?.getAttribute('aria-controls')).toBe('recent-history-grid');
    expect(screen.getByText('07')).toBeDefined();
    expect(screen.getByText(/Recent Analysis Queries \(3\)/)).toBeDefined();
    expect(screen.getByText('Expand +')).toBeDefined();
    expect(container.querySelector('#recent-history-grid')).toBeNull();
  });

  it('expands list, reveals .history-item-row items, and handles selection', async () => {
    vi.spyOn(api, 'getHistory').mockResolvedValue(mockHistory);
    const handleSelect = vi.fn();
    const { container } = render(
      <HistorySidebar onSelectRun={handleSelect} refreshTrigger={0} />
    );

    await waitFor(() => {
      expect(container.querySelector('.history-toggle-btn')).not.toBeNull();
    });

    const toggleBtn = container.querySelector('.history-toggle-btn')!;
    fireEvent.click(toggleBtn);

    expect(toggleBtn.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('Collapse −')).toBeDefined();
    expect(container.querySelector('#recent-history-grid')).not.toBeNull();

    // Check row items
    const rows = container.querySelectorAll('.history-item-row');
    expect(rows).toHaveLength(3);

    // Tickers format check: $MSFT should appear exactly once in .sp-hrow-ticker
    expect(screen.getByText('$MSFT')).toBeDefined();
    expect(screen.getByText('EUR/USD')).toBeDefined();
    expect(screen.getByText('$TSLA')).toBeDefined();

    // Badges check
    expect(screen.getByText('BUY')).toBeDefined();
    expect(screen.getByText('HOLD')).toBeDefined();
    expect(screen.getByText('SELL')).toBeDefined();
    expect(screen.getByText('FOREX')).toBeDefined();
    expect(screen.getByText('No News')).toBeDefined();
    expect(screen.getByText('Degraded')).toBeDefined();

    // Click on row 1
    fireEvent.click(rows[0]);
    expect(handleSelect).toHaveBeenCalledWith('hist-1');

    // Click on row 2
    fireEvent.click(rows[1]);
    expect(handleSelect).toHaveBeenCalledWith('hist-2');
  });

  it('re-fetches history when refreshTrigger increments', async () => {
    const getHistorySpy = vi.spyOn(api, 'getHistory').mockResolvedValue(mockHistory);
    const handleSelect = vi.fn();
    const { rerender } = render(
      <HistorySidebar onSelectRun={handleSelect} refreshTrigger={0} />
    );

    await waitFor(() => {
      expect(getHistorySpy).toHaveBeenCalledTimes(1);
    });

    rerender(<HistorySidebar onSelectRun={handleSelect} refreshTrigger={1} />);

    await waitFor(() => {
      expect(getHistorySpy).toHaveBeenCalledTimes(2);
    });
  });
});
