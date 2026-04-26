import { test, expect } from '@playwright/test';

test('portfolio heatmap and P&L chart render after a trade', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('cash-balance')).toBeVisible({ timeout: 10000 });

  await page.getByTestId('trade-ticker').fill('AAPL');
  await page.getByTestId('trade-quantity').fill('1');
  await page.getByTestId('trade-buy').click();

  const aaplRow = page
    .getByTestId('positions-table')
    .locator('tr, [role="row"]')
    .filter({ hasText: 'AAPL' });
  await expect(aaplRow).toHaveCount(1, { timeout: 5000 });

  const heatmap = page.getByTestId('heatmap');
  await expect(heatmap).toBeVisible();
  const heatmapBox = await heatmap.boundingBox();
  expect(heatmapBox?.width ?? 0).toBeGreaterThan(0);
  expect(heatmapBox?.height ?? 0).toBeGreaterThan(0);

  const pnl = page.getByTestId('pnl-chart');
  await expect(pnl).toBeVisible();
  const pnlBox = await pnl.boundingBox();
  expect(pnlBox?.width ?? 0).toBeGreaterThan(0);
  expect(pnlBox?.height ?? 0).toBeGreaterThan(0);
});
