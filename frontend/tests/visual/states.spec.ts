import { test, expect, Page } from '@playwright/test';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import {
  MOCK_HEALTH,
  MOCK_HISTORY,
  FIXTURE_BUY_CORROBORATED,
  FIXTURE_HOLD_NO_FRESH_NEWS,
  FIXTURE_SELL_DEGRADED,
  FIXTURE_WITH_EXCLUDED,
} from './fixtures';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PHASE = process.env.UI_PHASE || 'before';
const OUT_DIR = path.resolve(__dirname, '__out__', PHASE);

const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 768, height: 1024 },
  { width: 375, height: 812 },
];

test.beforeAll(() => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
});

async function setupDefaultMocks(page: Page) {
  await page.route('**/api/v1/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_HEALTH),
    });
  });

  await page.route('**/api/v1/history**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_HISTORY),
    });
  });
}

async function captureState(page: Page, stateName: string, width: number) {
  const filePath = path.join(OUT_DIR, `${stateName}-${width}.png`);
  await page.screenshot({ path: filePath, fullPage: true, animations: 'disabled' });
}

test.describe('Visual States Harness', () => {
  test.beforeEach(async (_, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop', 'States run viewports explicitly in desktop project');
  });

  for (const vp of VIEWPORTS) {
    test.describe(`Viewport ${vp.width}x${vp.height}`, () => {
      test.beforeEach(async ({ page }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });
      });

      test(`empty state (${vp.width})`, async ({ page }) => {
        await setupDefaultMocks(page);
        await page.goto('/');
        await expect(page.locator('#legal-disclaimer-strip')).toBeVisible();
        await expect(page.locator('#search-section')).toBeVisible();
        await expect(page.locator('#ticker-search-input')).toBeVisible();
        await captureState(page, 'empty', vp.width);
      });

      test(`loading state (~37%) (${vp.width})`, async ({ page }) => {
        await setupDefaultMocks(page);

        await page.route('**/api/v1/analyze', async (route) => {
          await route.fulfill({
            status: 202,
            contentType: 'application/json',
            body: JSON.stringify({
              job_id: 'job-mock-loading',
              ticker: 'NVDA',
              status: 'PROCESSING',
              max_wait_seconds: 150,
              coalesced: false,
              events_url: '/api/v1/jobs/job-mock-loading/events',
              poll_url: '/api/v1/jobs/job-mock-loading',
            }),
          });
        });

        await page.route('**/api/v1/jobs/job-mock-loading/events', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'text/event-stream',
            body: 'event: progress\ndata: {"job_id":"job-mock-loading","ticker":"NVDA","status":"PROCESSING","stage":"FILTERING_DEDUPLICATING","progress_pct":0.37,"message":"Clustering and deduplicating news feeds..."}\n\n',
          });
        });

        await page.route('**/api/v1/jobs/job-mock-loading', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              job_id: 'job-mock-loading',
              ticker: 'NVDA',
              status: 'PROCESSING',
              stage: 'FILTERING_DEDUPLICATING',
              progress_pct: 0.37,
              message: 'Clustering and deduplicating news feeds...',
              created_at: '2026-10-25T12:00:00Z',
              updated_at: '2026-10-25T12:00:01Z',
            }),
          });
        });

        await page.goto('/');
        await page.locator('#ticker-search-input').fill('NVDA');
        await page.locator('#run-analysis-btn').click();

        await expect(page.locator('#analysis-stepper')).toBeVisible();
        await expect(page.locator('#analysis-stepper')).toContainText('37%');
        await captureState(page, 'loading', vp.width);
      });

      test(`BUY result (${vp.width})`, async ({ page }) => {
        await setupDefaultMocks(page);

        await page.route('**/api/v1/analyze', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(FIXTURE_BUY_CORROBORATED),
          });
        });

        await page.goto('/');
        await page.locator('#ticker-search-input').fill('NVDA');
        await page.locator('#run-analysis-btn').click();

        await expect(page.locator('#decision-hero-card')).toBeVisible();
        await expect(page.locator('#result-verdict-pill')).toContainText('BUY');
        await expect(page.locator('#result-ticker-symbol')).toContainText('NVDA');
        await captureState(page, 'buy', vp.width);
      });

      test(`HOLD no-news result (${vp.width})`, async ({ page }) => {
        await setupDefaultMocks(page);

        await page.route('**/api/v1/analyze', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(FIXTURE_HOLD_NO_FRESH_NEWS),
          });
        });

        await page.goto('/');
        await page.locator('#ticker-search-input').fill('INTC');
        await page.locator('#run-analysis-btn').click();

        await expect(page.locator('#decision-hero-card')).toBeVisible();
        await expect(page.locator('#result-verdict-pill')).toContainText('HOLD');
        await expect(page.getByText('NO FRESH NEWS IN SESSION:')).toBeVisible();
        await captureState(page, 'hold-no-news', vp.width);
      });

      test(`SELL degraded result (${vp.width})`, async ({ page }) => {
        await setupDefaultMocks(page);

        await page.route('**/api/v1/analyze', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(FIXTURE_SELL_DEGRADED),
          });
        });

        await page.goto('/');
        await page.locator('#ticker-search-input').fill('TSLA');
        await page.locator('#run-analysis-btn').click();

        await expect(page.locator('#decision-hero-card')).toBeVisible();
        await expect(page.locator('#result-verdict-pill')).toContainText('SELL');
        await expect(page.getByText('DEGRADED INGESTION:')).toBeVisible();
        await captureState(page, 'sell-degraded', vp.width);
      });

      test(`evidence filtered to empty (${vp.width})`, async ({ page }) => {
        await setupDefaultMocks(page);

        await page.route('**/api/v1/analyze', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(FIXTURE_BUY_CORROBORATED),
          });
        });

        await page.goto('/');
        await page.locator('#ticker-search-input').fill('NVDA');
        await page.locator('#run-analysis-btn').click();

        await expect(page.locator('#evidence-explorer')).toBeVisible();
        const bearishTab = page.locator('.filter-tab', { hasText: 'Bearish' });
        await bearishTab.click();
        await expect(
          page.getByText('No retained articles match the selected sentiment filter for this session window.')
        ).toBeVisible();
        await captureState(page, 'filter-empty', vp.width);
      });

      test(`excluded expanded (${vp.width})`, async ({ page }) => {
        await setupDefaultMocks(page);

        await page.route('**/api/v1/analyze', async (route) => {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(FIXTURE_WITH_EXCLUDED),
          });
        });

        await page.goto('/');
        await page.locator('#ticker-search-input').fill('AMD');
        await page.locator('#run-analysis-btn').click();

        await expect(page.locator('#evidence-explorer')).toBeVisible();
        const excludedBtn = page.locator('button[aria-controls="excluded-articles-list"]');
        await expect(excludedBtn).toBeVisible();
        await excludedBtn.click();
        await expect(page.locator('#excluded-articles-list')).toBeVisible();
        await captureState(page, 'excluded-expanded', vp.width);
      });

      test(`history expanded (${vp.width})`, async ({ page }) => {
        await setupDefaultMocks(page);

        await page.goto('/');
        const historyToggle = page.locator('.history-toggle-btn');
        await expect(historyToggle).toBeVisible();
        await historyToggle.click();
        await expect(page.locator('#recent-history-grid')).toBeVisible();
        await expect(page.locator('.history-item-row').first()).toBeVisible();
        await captureState(page, 'history-expanded', vp.width);
      });

      test(`error state (${vp.width})`, async ({ page }) => {
        await setupDefaultMocks(page);

        await page.route('**/api/v1/analyze', async (route) => {
          await route.fulfill({
            status: 500,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'Ingestion pipeline error: failed to connect to upstream data provider' }),
          });
        });

        await page.goto('/');
        await page.locator('#ticker-search-input').fill('ERR');
        await page.locator('#run-analysis-btn').click();

        await expect(page.locator('[role="alert"]')).toBeVisible();
        await expect(page.locator('[role="alert"]')).toContainText('Ingestion pipeline error');
        await captureState(page, 'error', vp.width);
      });
    });
  }
});
