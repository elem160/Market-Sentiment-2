import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SectionRail, SECTION_ITEMS } from './SectionRail';

describe('SectionRail Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders exactly 7 section items in an ordered list inside a nav', () => {
    render(<SectionRail />);

    const nav = screen.getByRole('navigation', { name: /Page sections/i });
    expect(nav).toBeDefined();

    const listItems = nav.querySelectorAll('li');
    expect(listItems.length).toBe(7);

    for (const item of SECTION_ITEMS) {
      expect(screen.getByText(item.n)).toBeDefined();
      expect(screen.getByText(item.label)).toBeDefined();
    }
  });

  it('renders disabled spans when target section IDs are not in the document', () => {
    render(<SectionRail />);

    const disabledItems = screen.getAllByRole('generic', { hidden: true })
      .filter((el) => el.getAttribute('aria-disabled') === 'true');
    expect(disabledItems.length).toBe(7);
  });

  it('renders interactive anchor links when target section IDs exist in the DOM', () => {
    const section1 = document.createElement('div');
    section1.id = 'search-section';
    document.body.appendChild(section1);

    const section3 = document.createElement('div');
    section3.id = 'decision-hero-card';
    document.body.appendChild(section3);

    try {
      render(<SectionRail />);

      const links = screen.getAllByRole('link');
      expect(links.length).toBe(2);

      const linkHrefs = links.map((link) => link.getAttribute('href'));
      expect(linkHrefs).toContain('#search-section');
      expect(linkHrefs).toContain('#decision-hero-card');
    } finally {
      document.body.removeChild(section1);
      document.body.removeChild(section3);
    }
  });

  it('does not crash in environments where IntersectionObserver is undefined', () => {
    const originalIntersectionObserver = globalThis.IntersectionObserver;
    // @ts-expect-error simulating environment without IntersectionObserver
    delete globalThis.IntersectionObserver;

    try {
      expect(() => render(<SectionRail />)).not.toThrow();
    } finally {
      globalThis.IntersectionObserver = originalIntersectionObserver;
    }
  });

  it('does not crash in environments where MutationObserver is undefined', () => {
    const originalMutationObserver = globalThis.MutationObserver;
    // @ts-expect-error simulating environment without MutationObserver
    delete globalThis.MutationObserver;

    try {
      expect(() => render(<SectionRail />)).not.toThrow();
    } finally {
      globalThis.MutationObserver = originalMutationObserver;
    }
  });
});
