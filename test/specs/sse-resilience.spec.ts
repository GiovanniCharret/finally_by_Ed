import { test, expect } from '@playwright/test';

test('SSE connection indicator shows connected and prices flow', async ({ page }) => {
  await page.goto('/');

  const dot = page.getByTestId('connection-dot');
  await expect(dot).toBeVisible({ timeout: 10000 });

  const aaplRow = page.getByTestId('watchlist-row-AAPL');
  await expect(aaplRow).toBeVisible();

  const samples = new Set<string>();
  for (let i = 0; i < 12; i++) {
    const txt = (await aaplRow.textContent()) ?? '';
    samples.add(txt);
    await page.waitForTimeout(500);
  }
  expect(samples.size, 'AAPL row content should change at least once across ~6s of streaming').toBeGreaterThan(1);
});
