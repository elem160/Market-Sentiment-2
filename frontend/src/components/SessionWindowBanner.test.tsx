import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SessionWindowBanner } from './SessionWindowBanner';
import { SessionWindow } from '../types';

const mockOpenSession: SessionWindow = {
  session_type: 'REGULAR_HOURS',
  is_market_open: true,
  market_timezone: 'America/New_York',
  run_timestamp_utc: '2026-10-25T14:30:00Z',
  run_timestamp_et: '2026-10-25T10:30:00-04:00',
  window_start_utc: '2026-10-25T00:00:00Z',
  window_end_utc: '2026-10-25T14:30:00Z',
  window_start_et: '2026-10-24T20:00:00-04:00',
  window_end_et: '2026-10-25T10:30:00-04:00',
  window_duration_hours: 14.5,
};

const mockClosedSession: SessionWindow = {
  ...mockOpenSession,
  is_market_open: false,
  session_type: 'WEEKEND_SESSION',
};

describe('SessionWindowBanner (Spec Sheet v2)', () => {
  it('returns null when no session is provided', () => {
    const { container } = render(<SessionWindowBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('renders 6 spec cells and OPEN (RTH) status when market is open', () => {
    const { container } = render(<SessionWindowBanner session={mockOpenSession} />);

    expect(container.querySelector('#session-window-banner')).not.toBeNull();
    expect(screen.getByText('REGULAR HOURS')).toBeDefined();
    expect(screen.getByText('OPEN (RTH)')).toBeDefined();
    expect(container.querySelector('.sp-status-sq--open')).not.toBeNull();

    // Lookback label and value
    expect(screen.getByText('Lookback')).toBeDefined();
    expect(screen.getByText('14.5h')).toBeDefined();
  });

  it('renders CLOSED status and hatch cell when market is closed', () => {
    const { container } = render(<SessionWindowBanner session={mockClosedSession} />);

    expect(screen.getByText('WEEKEND SESSION')).toBeDefined();
    expect(screen.getByText('CLOSED')).toBeDefined();
    expect(container.querySelector('.sp-status-sq--closed')).not.toBeNull();
    expect(container.querySelector('.sp-cell--hatch')).not.toBeNull();
  });
});
