import { test, expect, Page } from '@playwright/test';
import { MOCK_HEALTH, MOCK_HISTORY, FIXTURE_BUY_CORROBORATED } from './fixtures';

async function setupMocks(page: Page) {
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

  await page.route('**/api/v1/analyze', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(FIXTURE_BUY_CORROBORATED),
    });
  });
}

test.describe('Design Conformance Spec (Section 12.3)', () => {
  test.beforeEach(async ({ page: _page }, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop', 'Conformance tests run viewports explicitly in desktop project');
  });

  for (const width of [1440, 375]) {
    test(`Empty state conformance (${width}px)`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await setupMocks(page);
      await page.goto('/');

      await expect(page.locator('#legal-disclaimer-strip')).toBeVisible();

      // 1. Body background luminance > 0.8
      const luminance = await page.evaluate(() => {
        const bg = window.getComputedStyle(document.body).backgroundColor;
        const m = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
        if (!m) return 1;
        const r = parseInt(m[1], 10) / 255;
        const g = parseInt(m[2], 10) / 255;
        const b = parseInt(m[3], 10) / 255;
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      });
      expect(luminance).toBeGreaterThan(0.8);

      // 2. Count of elements with border-top-left-radius > 0 is 0
      const radiusViolations = await page.evaluate(() => {
        const all = Array.from(document.querySelectorAll('*'));
        return all
          .filter((el) => {
            const r = parseFloat(window.getComputedStyle(el).borderTopLeftRadius);
            return r > 0;
          })
          .map((el) => el.tagName + (el.className ? `.${el.className}` : ''));
      });
      expect(radiusViolations).toEqual([]);

      // 3. Count of elements with backdrop-filter ≠ none is 0
      const backdropViolations = await page.evaluate(() => {
        const all = Array.from(document.querySelectorAll('*'));
        return all
          .filter((el) => {
            const s = window.getComputedStyle(el);
            const bf = s.backdropFilter || (s as any).webkitBackdropFilter;
            return bf && bf !== 'none';
          })
          .map((el) => el.tagName + (el.className ? `.${el.className}` : ''));
      });
      expect(backdropViolations).toEqual([]);

      // 4. Count of elements with box-shadow ≠ none is 0 (when nothing is focused)
      const shadowViolations = await page.evaluate(() => {
        const all = Array.from(document.querySelectorAll('*'));
        return all
          .filter((el) => {
            const bs = window.getComputedStyle(el).boxShadow;
            return bs && bs !== 'none';
          })
          .map((el) => el.tagName + (el.className ? `.${el.className}` : ''));
      });
      expect(shadowViolations).toEqual([]);

      // 5. No linear/radial-gradient except repeating-linear-gradient
      const gradientViolations = await page.evaluate(() => {
        const all = Array.from(document.querySelectorAll('*'));
        return all
          .filter((el) => {
            const bg = window.getComputedStyle(el).backgroundImage;
            if (!bg || bg === 'none') return false;
            const hasLinear =
              bg.includes('linear-gradient(') && !bg.includes('repeating-linear-gradient(');
            const hasRadial = bg.includes('radial-gradient(');
            return hasLinear || hasRadial;
          })
          .map((el) => el.tagName + (el.className ? `.${el.className}` : ''));
      });
      expect(gradientViolations).toEqual([]);

      // 6. #legal-disclaimer-strip visible and text not clipped
      const legalClipped = await page.evaluate(() => {
        const strip = document.getElementById('legal-disclaimer-strip');
        if (!strip) return true;
        return strip.scrollWidth > strip.clientWidth + 2;
      });
      expect(legalClipped).toBe(false);
    });

    test(`BUY result conformance (${width}px)`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await setupMocks(page);
      await page.goto('/');

      await page.locator('#ticker-search-input').fill('NVDA');
      await page.locator('#run-analysis-btn').click();

      await expect(page.locator('#decision-hero-card')).toBeVisible();

      // 1. Body luminance
      const luminance = await page.evaluate(() => {
        const bg = window.getComputedStyle(document.body).backgroundColor;
        const m = bg.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
        if (!m) return 1;
        const r = parseInt(m[1], 10) / 255;
        const g = parseInt(m[2], 10) / 255;
        const b = parseInt(m[3], 10) / 255;
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
      });
      expect(luminance).toBeGreaterThan(0.8);

      // 2. No border-radius > 0
      const radiusViolations = await page.evaluate(() => {
        const all = Array.from(document.querySelectorAll('*'));
        return all
          .filter((el) => {
            const r = parseFloat(window.getComputedStyle(el).borderTopLeftRadius);
            return r > 0;
          })
          .map((el) => el.tagName + (el.className ? `.${el.className}` : ''));
      });
      expect(radiusViolations).toEqual([]);

      // 3. No backdrop-filter
      const backdropViolations = await page.evaluate(() => {
        const all = Array.from(document.querySelectorAll('*'));
        return all
          .filter((el) => {
            const s = window.getComputedStyle(el);
            const bf = s.backdropFilter || (s as any).webkitBackdropFilter;
            return bf && bf !== 'none';
          })
          .map((el) => el.tagName + (el.className ? `.${el.className}` : ''));
      });
      expect(backdropViolations).toEqual([]);

      // 4. No box-shadow when nothing focused
      const shadowViolations = await page.evaluate(() => {
        const all = Array.from(document.querySelectorAll('*'));
        return all
          .filter((el) => {
            const bs = window.getComputedStyle(el).boxShadow;
            return bs && bs !== 'none';
          })
          .map((el) => el.tagName + (el.className ? `.${el.className}` : ''));
      });
      expect(shadowViolations).toEqual([]);

      // 5. No linear/radial gradient
      const gradientViolations = await page.evaluate(() => {
        const all = Array.from(document.querySelectorAll('*'));
        return all
          .filter((el) => {
            const bg = window.getComputedStyle(el).backgroundImage;
            if (!bg || bg === 'none') return false;
            const hasLinear =
              bg.includes('linear-gradient(') && !bg.includes('repeating-linear-gradient(');
            const hasRadial = bg.includes('radial-gradient(');
            return hasLinear || hasRadial;
          })
          .map((el) => el.tagName + (el.className ? `.${el.className}` : ''));
      });
      expect(gradientViolations).toEqual([]);

      // 6. #result-ticker-symbol text equals $NVDA
      const tickerText = await page.locator('#result-ticker-symbol').innerText();
      expect(tickerText.trim()).toBe('$NVDA');

      // 7. At 1440: h2 inside #decision-hero-card font-size >= 96px
      if (width === 1440) {
        const fontSize = await page.evaluate(() => {
          const h2 = document.querySelector('#decision-hero-card h2');
          return h2 ? parseFloat(window.getComputedStyle(h2).fontSize) : 0;
        });
        expect(fontSize).toBeGreaterThanOrEqual(96);
      }
    });
  }

  // 8. Horizontal scroll check at 320, 375, 768
  for (const w of [320, 375, 768]) {
    test(`No horizontal scroll at ${w}px`, async ({ page }) => {
      await page.setViewportSize({ width: w, height: 800 });
      await setupMocks(page);
      await page.goto('/');

      await page.locator('#ticker-search-input').fill('NVDA');
      await page.locator('#run-analysis-btn').click();
      await expect(page.locator('#decision-hero-card')).toBeVisible();

      const noHorizontalScroll = await page.evaluate((width) => {
        return document.documentElement.scrollWidth <= width;
      }, w);
      expect(noHorizontalScroll).toBe(true);
    });
  }

  // 9. Section Rail visibility check (1440 visible, 1024 hidden)
  test('Section rail is visible at 1440px and hidden at 1024px', async ({ page }) => {
    await setupMocks(page);

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    const rail1440 = page.locator('nav[aria-label="Page sections"]');
    await expect(rail1440).toBeVisible();

    await page.setViewportSize({ width: 1024, height: 768 });
    await expect(rail1440).toBeHidden();
  });
});
