import React, { useState, useEffect } from 'react';

export const SECTION_ITEMS = [
  { n: '01', id: 'search-section', label: 'Input' },
  { n: '02', id: 'session-window-banner', label: 'Context' },
  { n: '03', id: 'decision-hero-card', label: 'Signal' },
  { n: '04', id: 'rationale-section', label: 'Rationale' },
  { n: '05', id: 'evidence-explorer', label: 'Evidence' },
  { n: '06', id: 'pipeline-telemetry-strip', label: 'Run log' },
  { n: '07', id: 'recent-history-panel', label: 'History' },
] as const;

export const SectionRail: React.FC = () => {
  const [presentIds, setPresentIds] = useState<Set<string>>(() => new Set());
  const [activeId, setActiveId] = useState<string>('');

  useEffect(() => {
    const checkPresence = () => {
      const found = new Set<string>();
      for (const item of SECTION_ITEMS) {
        if (typeof document !== 'undefined' && document.getElementById(item.id)) {
          found.add(item.id);
        }
      }
      setPresentIds((prev) => {
        const prevJoined = Array.from(prev).sort().join(',');
        const nextJoined = Array.from(found).sort().join(',');
        return prevJoined === nextJoined ? prev : found;
      });
    };

    checkPresence();

    if (typeof MutationObserver === 'undefined') {
      return;
    }

    let rafId: number | null = null;
    const observer = new MutationObserver(() => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        checkPresence();
      });
    });

    const mainEl = document.querySelector('main');
    if (mainEl) {
      observer.observe(mainEl, { childList: true, subtree: true });
    }

    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id);
          }
        }
      },
      { rootMargin: '-40% 0px -55% 0px' }
    );

    const observedElements: Element[] = [];
    for (const item of SECTION_ITEMS) {
      const el = document.getElementById(item.id);
      if (el) {
        observer.observe(el);
        observedElements.push(el);
      }
    }

    return () => {
      observer.disconnect();
    };
  }, [presentIds]);

  return (
    <nav className="sp-rail" aria-label="Page sections">
      <ol className="sp-rail-list">
        {SECTION_ITEMS.map((item) => {
          const isPresent = presentIds.has(item.id);
          const isActive = activeId === item.id;

          return (
            <li key={item.id}>
              {isPresent ? (
                <a
                  href={`#${item.id}`}
                  className="sp-rail-item"
                  aria-current={isActive ? 'location' : undefined}
                >
                  <span className="sp-rail-n">{item.n}</span>
                  <span className="sp-rail-lbl">{item.label}</span>
                </a>
              ) : (
                <span className="sp-rail-item" aria-disabled="true">
                  <span className="sp-rail-n">{item.n}</span>
                  <span className="sp-rail-lbl">{item.label}</span>
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
};
