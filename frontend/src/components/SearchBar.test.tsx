import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SearchBar } from './SearchBar';

describe('SearchBar (Spec Sheet v2)', () => {
  it('renders input section, contract IDs, and default state', () => {
    const handleSearch = vi.fn();
    const { container } = render(<SearchBar onSearch={handleSearch} isLoading={false} />);

    expect(container.querySelector('#search-section')).not.toBeNull();
    expect(container.querySelector('form.search-form')).not.toBeNull();
    expect(container.querySelector('#ticker-search-input')).not.toBeNull();
    expect(container.querySelector('#run-analysis-btn')).not.toBeNull();
    expect(container.querySelector('#force-refresh-checkbox')).not.toBeNull();
    expect(container.querySelector('#enable-llm-checkbox')).not.toBeNull();
    expect(container.querySelector('#ticker-format-helper')).not.toBeNull();

    // Check all 6 quick chips
    expect(container.querySelector('#quick-chip-nvda')).not.toBeNull();
    expect(container.querySelector('#quick-chip-aapl')).not.toBeNull();
    expect(container.querySelector('#quick-chip-eur-usd')).not.toBeNull();
    expect(container.querySelector('#quick-chip-usd-jpy')).not.toBeNull();
    expect(container.querySelector('#quick-chip-gc-f')).not.toBeNull();
    expect(container.querySelector('#quick-chip-btc-usd')).not.toBeNull();

    // Default toggle states
    const forceRefreshBox = container.querySelector('#force-refresh-checkbox') as HTMLInputElement;
    const enableLlmBox = container.querySelector('#enable-llm-checkbox') as HTMLInputElement;
    expect(forceRefreshBox.checked).toBe(false);
    expect(enableLlmBox.checked).toBe(true);

    // Initial button text
    expect(screen.getByText('RUN SENTIMENT')).toBeDefined();
  });

  it('uppercases input and submits on form submit', () => {
    const handleSearch = vi.fn();
    const { container } = render(<SearchBar onSearch={handleSearch} isLoading={false} />);

    const input = container.querySelector('#ticker-search-input') as HTMLInputElement;
    const form = container.querySelector('form.search-form') as HTMLFormElement;

    fireEvent.change(input, { target: { value: 'aapl' } });
    expect(input.value).toBe('AAPL');

    fireEvent.submit(form);
    expect(handleSearch).toHaveBeenCalledWith('AAPL', false, true);
  });

  it('submits on quick chip click', () => {
    const handleSearch = vi.fn();
    const { container } = render(<SearchBar onSearch={handleSearch} isLoading={false} />);

    const chip = container.querySelector('#quick-chip-gc-f') as HTMLButtonElement;
    fireEvent.click(chip);

    expect(handleSearch).toHaveBeenCalledWith('GC=F', false, true);
  });

  it('passes toggled options to search handler', () => {
    const handleSearch = vi.fn();
    const { container } = render(<SearchBar onSearch={handleSearch} isLoading={false} />);

    const forceRefreshBox = container.querySelector('#force-refresh-checkbox') as HTMLInputElement;
    const enableLlmBox = container.querySelector('#enable-llm-checkbox') as HTMLInputElement;
    const input = container.querySelector('#ticker-search-input') as HTMLInputElement;
    const form = container.querySelector('form.search-form') as HTMLFormElement;

    fireEvent.click(forceRefreshBox);
    fireEvent.click(enableLlmBox);
    expect(forceRefreshBox.checked).toBe(true);
    expect(enableLlmBox.checked).toBe(false);

    fireEvent.change(input, { target: { value: 'MSFT' } });
    fireEvent.submit(form);

    expect(handleSearch).toHaveBeenCalledWith('MSFT', true, false);
  });

  it('disables controls and displays loading text while isLoading is true', () => {
    const handleSearch = vi.fn();
    const { container } = render(<SearchBar onSearch={handleSearch} isLoading={true} activeTicker="NVDA" />);

    const input = container.querySelector('#ticker-search-input') as HTMLInputElement;
    const button = container.querySelector('#run-analysis-btn') as HTMLButtonElement;
    const chip = container.querySelector('#quick-chip-nvda') as HTMLButtonElement;

    expect(input.disabled).toBe(true);
    expect(button.disabled).toBe(true);
    expect(chip.disabled).toBe(true);
    expect(screen.getByText('ANALYZING...')).toBeDefined();
  });
});
