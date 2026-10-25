import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EvidenceExplorer } from './EvidenceExplorer';
import { ScoredArticle, PipelineMetrics } from '../types';

function createMockArticle(overrides: Partial<ScoredArticle> = {}): ScoredArticle {
  return {
    article_id: 'art-default',
    title: 'Default Test Article Title',
    canonical_url: 'https://example.com/art',
    canonical_publisher: 'Financial Times',
    source_name: 'Financial Times',
    provider: 'YFINANCE',
    published_at_utc: '2026-10-24T10:00:00Z',
    age_hours: 2.0,
    cluster_id: 'cluster-1',
    finbert_directional_score: 0.5,
    finbert_positive: 0.7,
    finbert_negative: 0.1,
    finbert_neutral: 0.2,
    finbert_confidence: 0.8,
    effective_weight: 0.35,
    final_weight: 0.35,
    is_llm_catalyst: false,
    publisher_inferred: false,
    lead_text: 'Lead summary text for the article.',
    ...overrides,
  };
}

describe('EvidenceExplorer (Spec Sheet v2)', () => {
  const mockArticles: ScoredArticle[] = [
    createMockArticle({
      article_id: 'art-bullish',
      title: 'Bullish Surge on Record Margins',
      canonical_url: 'https://example.com/art-bullish',
      canonical_publisher: 'Wall Street Journal',
      provider: 'YFINANCE',
      finbert_directional_score: 0.65,
      finbert_positive: 0.8,
      finbert_negative: 0.05,
      finbert_neutral: 0.15,
      effective_weight: 0.42,
      lead_text: 'Record operating margins reported across cloud and enterprise units.',
    }),
    createMockArticle({
      article_id: 'art-bearish',
      title: 'Bearish Warning on Supply Chain Snarls',
      canonical_url: '', // Unlinked article
      canonical_publisher: 'Financial Times',
      provider: 'GOOGLE_RSS_AGGREGATOR',
      finbert_directional_score: -0.45,
      finbert_positive: 0.1,
      finbert_negative: 0.75,
      finbert_neutral: 0.15,
      final_weight: 0.38,
      lead_text: 'Significant slowdown observed in component replenishment cycle.',
    }),
    createMockArticle({
      article_id: 'art-neutral',
      title: 'Neutral Market Hold Pattern Continues',
      canonical_url: 'https://example.com/art-neutral',
      canonical_publisher: 'CNBC',
      provider: 'YFINANCE',
      finbert_directional_score: 0.05,
      finbert_positive: 0.2,
      finbert_negative: 0.2,
      finbert_neutral: 0.6,
      effective_weight: 0.2,
      lead_text: 'Trading volumes remain flat awaiting scheduled central bank commentary.',
    }),
    createMockArticle({
      article_id: 'art-excluded-1',
      title: 'Duplicate Wire Report',
      canonical_url: 'https://example.com/art-excluded-1',
      source_name: 'AP News',
      provider: 'GOOGLE_RSS_AGGREGATOR',
      exclusion_reason: 'DUPLICATE_SYNDICATION',
      finbert_directional_score: 0.5,
      lead_text: 'Duplicate content from wire syndicate.',
    }),
    createMockArticle({
      article_id: 'art-excluded-2',
      title: 'Outdated Pre-Window Speculation',
      canonical_url: 'https://example.com/art-excluded-2',
      source_name: 'Market Blog',
      provider: 'GOOGLE_RSS_AGGREGATOR',
      exclusion_reason: 'TIMESTAMP_OUT_OF_WINDOW',
      finbert_directional_score: -0.2,
      lead_text: 'Dated article published prior to session window.',
    }),
  ];

  const mockMetrics: PipelineMetrics = {
    distinct_publishers: 3,
    supporting_publishers: 2,
    publishers_positive: 1,
    publishers_negative: 1,
    distinct_clusters: 2,
    directional_threshold: 0.15,
    articles_ingested: 5,
    articles_retained: 3,
    articles_excluded_total: 2,
    articles_deduplicated: 1,
    articles_scored_local: 3,
    articles_sent_to_llm: 3,
    completion_tokens: 0,
    prompt_tokens: 0,
    estimated_cost_usd: 0,
    excluded_missing_timestamp: 0,
    excluded_out_of_window: 1,
    stage_latencies: {},
    total_latency_ms: 100,
    total_sources: 3,
  };

  it('renders section container with id="evidence-explorer"', () => {
    const { container } = render(
      <EvidenceExplorer articles={mockArticles} metrics={mockMetrics} />
    );
    expect(container.querySelector('#evidence-explorer')).not.toBeNull();
  });

  it('calculates filter partition counts matching articles per category', () => {
    render(<EvidenceExplorer articles={mockArticles} metrics={mockMetrics} />);

    // Retained total is 3
    expect(screen.getByRole('tab', { name: 'All (3)' })).toBeDefined();
    // Bullish: 1 article (score 0.65 >= 0.15)
    expect(screen.getByRole('tab', { name: 'Bullish (1)' })).toBeDefined();
    // Bearish: 1 article (score -0.45 <= -0.15)
    expect(screen.getByRole('tab', { name: 'Bearish (1)' })).toBeDefined();
    // Neutral: 1 article (|0.05| < 0.15)
    expect(screen.getByRole('tab', { name: 'Neutral (1)' })).toBeDefined();
  });

  it('filters rows and updates aria-selected on tab clicks', () => {
    const { container } = render(
      <EvidenceExplorer articles={mockArticles} metrics={mockMetrics} />
    );

    const allTab = screen.getByRole('tab', { name: 'All (3)' });
    const bullishTab = screen.getByRole('tab', { name: 'Bullish (1)' });
    const bearishTab = screen.getByRole('tab', { name: 'Bearish (1)' });
    const neutralTab = screen.getByRole('tab', { name: 'Neutral (1)' });

    // Initial state: ALL active
    expect(allTab.getAttribute('aria-selected')).toBe('true');
    expect(allTab.className).toContain('active');
    expect(container.querySelector('#evidence-articles-list')).not.toBeNull();
    expect(screen.getByText('Bullish Surge on Record Margins')).toBeDefined();
    expect(screen.getByText('Bearish Warning on Supply Chain Snarls')).toBeDefined();
    expect(screen.getByText('Neutral Market Hold Pattern Continues')).toBeDefined();

    // Click Bullish tab
    fireEvent.click(bullishTab);
    expect(bullishTab.getAttribute('aria-selected')).toBe('true');
    expect(bullishTab.className).toContain('active');
    expect(allTab.getAttribute('aria-selected')).toBe('false');
    expect(screen.getByText('Bullish Surge on Record Margins')).toBeDefined();
    expect(screen.queryByText('Bearish Warning on Supply Chain Snarls')).toBeNull();
    expect(screen.queryByText('Neutral Market Hold Pattern Continues')).toBeNull();

    // Click Bearish tab
    fireEvent.click(bearishTab);
    expect(bearishTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.queryByText('Bullish Surge on Record Margins')).toBeNull();
    expect(screen.getByText('Bearish Warning on Supply Chain Snarls')).toBeDefined();

    // Click Neutral tab
    fireEvent.click(neutralTab);
    expect(neutralTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByText('Neutral Market Hold Pattern Continues')).toBeDefined();
    expect(screen.queryByText('Bullish Surge on Record Margins')).toBeNull();
  });

  it('expands and collapses article drawer, toggles aria-expanded, and reveals lead_text', () => {
    render(<EvidenceExplorer articles={mockArticles} metrics={mockMetrics} />);

    const toggleButtons = screen.getAllByRole('button', { name: 'Details +' });
    const firstToggle = toggleButtons[0];

    expect(firstToggle.getAttribute('aria-expanded')).toBe('false');
    expect(
      screen.queryByText('Record operating margins reported across cloud and enterprise units.')
    ).toBeNull();

    // Expand
    fireEvent.click(firstToggle);
    expect(firstToggle.getAttribute('aria-expanded')).toBe('true');
    expect(firstToggle.textContent).toContain('Less −');
    expect(
      screen.getByText('Record operating margins reported across cloud and enterprise units.')
    ).toBeDefined();

    // Collapse
    fireEvent.click(firstToggle);
    expect(firstToggle.getAttribute('aria-expanded')).toBe('false');
    expect(firstToggle.textContent).toContain('Details +');
    expect(
      screen.queryByText('Record operating margins reported across cloud and enterprise units.')
    ).toBeNull();
  });

  it('renders contract test classes: evidence-item, article-title-link, and article-title-text', () => {
    const { container } = render(
      <EvidenceExplorer articles={mockArticles} metrics={mockMetrics} />
    );

    const items = container.querySelectorAll('.evidence-item');
    expect(items.length).toBeGreaterThanOrEqual(3);

    // Linked article has .article-title-link
    const linkedTitle = screen.getByRole('link', { name: /Bullish Surge on Record Margins/i });
    expect(linkedTitle.className).toContain('article-title-link');

    // Unlinked article has .article-title-text
    const unlinkedTitle = screen.getByText('Bearish Warning on Supply Chain Snarls');
    expect(unlinkedTitle.className).toContain('article-title-text');
  });

  it('expands/collapses excluded articles accordion, toggles aria-expanded, keeps aria-controls="excluded-articles-list"', () => {
    const { container } = render(
      <EvidenceExplorer articles={mockArticles} metrics={mockMetrics} />
    );

    const exclToggle = screen.getByRole('button', {
      name: /Excluded from scoring \(2 total\)/i,
    });
    expect(exclToggle.getAttribute('aria-controls')).toBe('excluded-articles-list');
    expect(exclToggle.getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('#excluded-articles-list')).toBeNull();

    // Expand excluded block
    fireEvent.click(exclToggle);
    expect(exclToggle.getAttribute('aria-expanded')).toBe('true');
    const exclList = container.querySelector('#excluded-articles-list');
    expect(exclList).not.toBeNull();
    expect(screen.getByText('Duplicate Wire Report')).toBeDefined();
    expect(screen.getByText('Outdated Pre-Window Speculation')).toBeDefined();
    expect(screen.getByText('DUPLICATE SYNDICATION')).toBeDefined();
    expect(screen.getByText('TIMESTAMP OUT OF WINDOW')).toBeDefined();

    // Collapse excluded block
    fireEvent.click(exclToggle);
    expect(exclToggle.getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('#excluded-articles-list')).toBeNull();
  });

  it('renders empty message when no retained articles match a filter', () => {
    const onlyBullishArticles: ScoredArticle[] = [
      createMockArticle({
        article_id: 'art-only-pos',
        title: 'Only Bullish News',
        published_at_utc: '2026-10-24T12:00:00Z',
        finbert_directional_score: 0.9,
      }),
    ];

    render(<EvidenceExplorer articles={onlyBullishArticles} metrics={mockMetrics} />);

    // Click Bearish tab (count is 0)
    const bearishTab = screen.getByRole('tab', { name: 'Bearish (0)' });
    fireEvent.click(bearishTab);

    expect(
      screen.getByText(
        'No retained articles match the selected sentiment filter for this session window.'
      )
    ).toBeDefined();
  });
});
