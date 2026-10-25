import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LoadingStepper } from './LoadingStepper';

describe('LoadingStepper (Spec Sheet v2)', () => {
  it('renders giant 3-digit counter, progressbar, and live status message', () => {
    const { container } = render(
      <LoadingStepper
        stage="FILTERING_DEDUPLICATING"
        progressPct={0.37}
        message="Validating ticker symbol NVDA..."
        ticker="NVDA"
      />
    );

    // Section and header
    expect(container.querySelector('#analysis-stepper')).not.toBeNull();
    expect(screen.getByText(/Running pipeline for \$NVDA/i)).toBeDefined();

    // Giant 3-digit counter
    expect(container.querySelector('.sp-counter')?.textContent).toBe('037%');

    // Progressbar ruler
    const ruler = container.querySelector('.sp-ruler');
    expect(ruler).not.toBeNull();
    expect(ruler?.getAttribute('aria-valuenow')).toBe('37');

    // Live status message with role="status"
    const statusMsg = container.querySelector('.sp-loading-msg[role="status"]');
    expect(statusMsg).not.toBeNull();
    expect(statusMsg?.textContent).toContain('Validating ticker symbol NVDA...');
  });

  it('marks stages correctly as done, active, and queued', () => {
    const { container } = render(
      <LoadingStepper
        stage="FINBERT_SCORING"
        progressPct={0.65}
        message="Running FinBERT model..."
        ticker="EUR/USD"
      />
    );

    const stages = container.querySelectorAll('.sp-stage');
    expect(stages.length).toBe(6);

    // Stages 0, 1, 2 should be done
    expect(stages[0].classList.contains('is-done')).toBe(true);
    expect(stages[0].querySelector('.sp-tag')?.textContent).toBe('DONE');
    expect(stages[1].classList.contains('is-done')).toBe(true);
    expect(stages[2].classList.contains('is-done')).toBe(true);

    // Stage 3 (FINBERT_SCORING) is active
    expect(stages[3].classList.contains('is-active')).toBe(true);
    expect(stages[3].querySelector('.sp-tag')?.textContent).toBe('RUNNING');

    // Stages 4, 5 are queued
    expect(stages[4].classList.contains('is-queued')).toBe(true);
    expect(stages[4].querySelector('.sp-tag')?.textContent).toBe('QUEUED');
    expect(stages[5].classList.contains('is-queued')).toBe(true);
  });
});
