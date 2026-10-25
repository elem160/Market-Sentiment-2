import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RationaleSection } from './RationaleSection';
import { PipelineRationale, ScoredArticle } from '../types';

function createMockArticle(overrides: Partial<ScoredArticle> = {}): ScoredArticle {
  return {
    article_id: 'art-1',
    title: 'Strong cloud growth for tech giants',
    canonical_url: 'https://example.com/art-1',
    canonical_publisher: 'Reuters',
    source_name: 'Reuters',
    provider: 'YFINANCE',
    published_at_utc: '2026-10-24T10:30:00Z',
    age_hours: 1.5,
    cluster_id: 'cluster-1',
    finbert_directional_score: 0.8,
    finbert_positive: 0.85,
    finbert_negative: 0.05,
    finbert_neutral: 0.1,
    finbert_confidence: 0.9,
    effective_weight: 0.45,
    final_weight: 0.45,
    is_llm_catalyst: false,
    publisher_inferred: false,
    lead_text: 'Cloud revenue acceleration reported across key enterprise segments.',
    ...overrides,
  };
}

describe('RationaleSection (Spec Sheet v2)', () => {
  const mockArticles: ScoredArticle[] = [
    createMockArticle({
      article_id: 'art-1',
      title: 'Strong cloud growth for tech giants',
      canonical_publisher: 'Reuters',
    }),
    createMockArticle({
      article_id: 'art-2',
      title: 'Regulatory scrutiny increases in EU',
      canonical_publisher: 'Bloomberg',
      provider: 'GOOGLE_RSS_AGGREGATOR',
      finbert_directional_score: -0.6,
      finbert_positive: 0.1,
      finbert_negative: 0.7,
      finbert_neutral: 0.2,
      final_weight: 0.35,
    }),
  ];

  const mockRationale: PipelineRationale = {
    summary: 'Cloud revenue acceleration overrides minor macroeconomic headwind.',
    inferences: [
      'Enterprise demand remains resilient across top tier partners.',
      'Margin expansion expected from operating efficiency initiatives.',
    ],
    observed_facts: [
      {
        statement: 'Cloud division posted 28% year-over-year revenue growth.',
        cited_article_id: 'art-1',
        impact: 'POSITIVE',
        catalyst_category: 'EARNINGS',
      },
      {
        statement: 'Antitrust regulators requested compliance documentation.',
        cited_article_id: 'art-2',
        impact: 'NEGATIVE',
        catalyst_category: 'REGULATORY',
      },
    ],
  };

  it('renders section container with id="rationale-section"', () => {
    const { container } = render(
      <RationaleSection rationale={mockRationale} articles={mockArticles} />
    );
    expect(container.querySelector('#rationale-section')).not.toBeNull();
  });

  it('renders synthesized rationale summary once without duplication', () => {
    render(<RationaleSection rationale={mockRationale} articles={mockArticles} />);
    const summaries = screen.getAllByText(
      'Cloud revenue acceleration overrides minor macroeconomic headwind.'
    );
    expect(summaries).toHaveLength(1);
  });

  it('renders inferences ledger items with correct numbering', () => {
    const { container } = render(
      <RationaleSection rationale={mockRationale} articles={mockArticles} />
    );
    expect(
      screen.getByText('Enterprise demand remains resilient across top tier partners.')
    ).toBeDefined();
    expect(
      screen.getByText('Margin expansion expected from operating efficiency initiatives.')
    ).toBeDefined();

    const ledger = container.querySelector('.sp-ledger');
    expect(ledger).not.toBeNull();
    const numbers = ledger?.querySelectorAll('.sp-ledger-n');
    expect(numbers?.[0].textContent).toBe('01');
    expect(numbers?.[1].textContent).toBe('02');
  });

  it('renders observed facts with impact badges, category, and citation metadata', () => {
    render(<RationaleSection rationale={mockRationale} articles={mockArticles} />);

    expect(
      screen.getByText('Cloud division posted 28% year-over-year revenue growth.')
    ).toBeDefined();
    expect(
      screen.getByText('Antitrust regulators requested compliance documentation.')
    ).toBeDefined();

    expect(screen.getByText(/POSITIVE/)).toBeDefined();
    expect(screen.getByText(/NEGATIVE/)).toBeDefined();
    expect(screen.getByText('EARNINGS')).toBeDefined();
    expect(screen.getByText('REGULATORY')).toBeDefined();
    expect(screen.getByText('Reuters')).toBeDefined();
    expect(screen.getByText('Bloomberg')).toBeDefined();
  });

  it('renders empty message when no observed facts are available', () => {
    const emptyRationale: PipelineRationale = {
      summary: 'Flat session with low dispersion.',
      inferences: [],
      observed_facts: [],
    };
    render(<RationaleSection rationale={emptyRationale} articles={[]} />);
    expect(
      screen.getByText('No verified catalyst statements extracted for this session window.')
    ).toBeDefined();
  });

  it('renders catalyst synthesis card when llmSummary is provided', () => {
    const { container } = render(
      <RationaleSection
        rationale={mockRationale}
        articles={mockArticles}
        llmSummary="Synthesized synthesis text highlighting major catalysts."
        modelVersions={{ llm: 'gemini-1.5-pro' }}
      />
    );

    const card = container.querySelector('#llm-synthesis-card');
    expect(card).not.toBeNull();
    expect(
      screen.getByText('Synthesized synthesis text highlighting major catalysts.')
    ).toBeDefined();
    expect(screen.getByText('Model: gemini-1.5-pro')).toBeDefined();
  });

  it('does not render catalyst synthesis card when llmSummary is absent', () => {
    const { container } = render(
      <RationaleSection rationale={mockRationale} articles={mockArticles} />
    );
    expect(container.querySelector('#llm-synthesis-card')).toBeNull();
  });
});
