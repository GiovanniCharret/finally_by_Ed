import { test, expect } from '@playwright/test';

test('add and remove a ticker from the watchlist', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('[data-testid^="watchlist-row-"]')).toHaveCount(10, { timeout: 10000 });

  await page.getByTestId('watchlist-add-input').fill('BYND');
  await page.getByTestId('watchlist-add-button').click();

  const byndRow = page.getByTestId('watchlist-row-BYND');
  await expect(byndRow).toHaveCount(1, { timeout: 5000 });

  await byndRow.getByTestId('watchlist-remove').click();

  await expect(page.getByTestId('watchlist-row-BYND')).toHaveCount(0, { timeout: 5000 });
});
