import { test, expect } from '@playwright/test';

const DEFAULT_TICKERS = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'META', 'JPM', 'V', 'NFLX'];

test('fresh start shows default watchlist, $10k cash, and streaming prices', async ({ page }) => {
  await page.goto('/');

  const cash = page.getByTestId('cash-balance');
  await expect(cash).toBeVisible({ timeout: 10000 });
  await expect(cash).toContainText(/10[,.]?000/);

  const rows = page.locator('[data-testid^="watchlist-row-"]');
  await expect(rows).toHaveCount(10, { timeout: 10000 });

  for (const ticker of DEFAULT_TICKERS) {
    await expect(page.getByTestId(`watchlist-row-${ticker}`)).toHaveCount(1);
  }

  const aaplRow = page.getByTestId('watchlist-row-AAPL');
  await expect(aaplRow).toBeVisible();

  const initial = (await aaplRow.textContent()) ?? '';
  let changed = false;
  for (let i = 0; i < 10 && !changed; i++) {
    await page.waitForTimeout(500);
    const current = (await aaplRow.textContent()) ?? '';
    if (current !== initial && current.length > 0) changed = true;
  }
  expect(changed, 'AAPL price should update at least once within 5s of streaming').toBe(true);
});
