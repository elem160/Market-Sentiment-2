import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LandingHero } from './LandingHero';

describe('LandingHero Component', () => {
  it('renders the welcome region and exact introductory copy', () => {
    render(<LandingHero />);

    const region = screen.getByRole('region', { name: /Welcome and usage introduction/i });
    expect(region).toBeDefined();

    expect(screen.getByText('Session-anchored news sentiment')).toBeDefined();
    expect(screen.getByRole('heading', { level: 2 })).toBeDefined();

    const expectedParagraph =
      'Enter any US equity, ETF, forex pair (e.g. EUR/USD), commodity future (e.g. GC=F), or crypto asset to execute session-anchored news ingestion, FinBERT neural scoring, and corroboration synthesis.';
    expect(screen.getByText(expectedParagraph)).toBeDefined();
  });

  it('renders all 5 spec table rows with exact labels and values', () => {
    render(<LandingHero />);

    expect(screen.getByText('Scoring model')).toBeDefined();
    expect(screen.getByText('FinBERT')).toBeDefined();

    expect(screen.getByText('Recency half-life')).toBeDefined();
    expect(screen.getByText('14 h')).toBeDefined();

    expect(screen.getByText('Corroboration gate')).toBeDefined();
    expect(screen.getByText('≥ 2 publishers')).toBeDefined();

    expect(screen.getByText('Result cache')).toBeDefined();
    expect(screen.getByText('15 min')).toBeDefined();

    expect(screen.getByText('Instruments')).toBeDefined();
    expect(screen.getByText('Equity · ETF · FX · Futures · Crypto')).toBeDefined();
  });
});
