import { test, expect } from '@playwright/test';

test.describe('SentimentPulse Visual Regression Suite', () => {
  test('empty state renders correctly', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#legal-disclaimer-strip')).toBeVisible();
    await expect(page.locator('#search-section')).toBeVisible();
    await expect(page.locator('#ticker-search-input')).toBeVisible();
    await expect(page.locator('#run-analysis-btn')).toBeVisible();
  });

  test('history drawer expands and loads historical analysis', async ({ page }) => {
    await page.goto('/');
    const historyToggle = page.locator('.history-toggle-btn');
    if (await historyToggle.isVisible()) {
      await historyToggle.click();
      await expect(page.locator('#recent-history-grid')).toBeVisible();
      const firstRow = page.locator('.history-item-row').first();
      await expect(firstRow).toBeVisible();
      await firstRow.click();
      await expect(page.locator('#decision-hero-card')).toBeVisible();
      await expect(page.locator('#result-ticker-symbol')).toBeVisible();
      await expect(page.locator('#result-verdict-pill')).toBeVisible();
    }
  });

  test('evidence explorer filter tabs switch correctly', async ({ page }) => {
    await page.goto('/');
    const historyToggle = page.locator('.history-toggle-btn');
    if (await historyToggle.isVisible()) {
      await historyToggle.click();
      const firstRow = page.locator('.history-item-row').first();
      await firstRow.click();
      await expect(page.locator('#evidence-explorer')).toBeVisible();

      const bullishTab = page.locator('.filter-tab', { hasText: 'Bullish' });
      await bullishTab.click();
      await expect(bullishTab).toHaveClass(/active/);

      const allTab = page.locator('.filter-tab', { hasText: 'All' });
      await allTab.click();
      await expect(allTab).toHaveClass(/active/);
    }
  });
});
