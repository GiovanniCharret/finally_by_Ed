import { test, expect, Page } from '@playwright/test';

const cashToNumber = async (loc: ReturnType<Page['getByTestId']>): Promise<number> => {
  const text = (await loc.textContent()) ?? '';
  const m = text.replace(/[$,\s]/g, '').match(/-?\d+(\.\d+)?/);
  return m ? parseFloat(m[0]) : NaN;
};

const setQuantity = async (page: Page, value: string): Promise<void> => {
  const qty = page.getByTestId('trade-quantity');
  await qty.click({ clickCount: 3 });
  await page.keyboard.type(value);
  await expect(qty).toHaveValue(value);
};

const aaplRowQty = async (page: Page): Promise<number> => {
  const row = page
    .getByTestId('positions-table')
    .locator('tr, [role="row"]')
    .filter({ hasText: 'AAPL' });
  const count = await row.count();
  if (count === 0) return 0;
  const cells = row.first().locator('td, [role="cell"]');
  const cellCount = await cells.count();
  if (cellCount < 2) return 0;
  const qtyText = ((await cells.nth(1).textContent()) ?? '').replace(/[$,\s]/g, '');
  const m = qtyText.match(/-?\d+(\.\d+)?/);
  return m ? parseFloat(m[0]) : NaN;
};

test('buy and sell shares of AAPL', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('cash-balance')).toBeVisible({ timeout: 10000 });

  const cashLoc = page.getByTestId('cash-balance');
  await expect(cashLoc).toContainText('$', { timeout: 10000 });
  const startingCash = await cashToNumber(cashLoc);
  expect(startingCash).toBeGreaterThan(0);

  const startingQty = await aaplRowQty(page);

  await page.getByTestId('trade-ticker').fill('AAPL');
  await setQuantity(page, '1');
  await page.getByTestId('trade-buy').click();

  const aaplPosition = page
    .getByTestId('positions-table')
    .locator('tr, [role="row"]')
    .filter({ hasText: 'AAPL' });
  await expect(aaplPosition).toHaveCount(1, { timeout: 5000 });

  await expect.poll(async () => await aaplRowQty(page), { timeout: 5000 }).toBe(startingQty + 1);
  await expect.poll(async () => await cashToNumber(cashLoc), { timeout: 5000 }).toBeLessThan(startingCash);
  const cashAfterBuy = await cashToNumber(cashLoc);

  await page.getByTestId('trade-ticker').fill('AAPL');
  await setQuantity(page, '1');
  await page.getByTestId('trade-sell').click();

  await expect
    .poll(async () => await aaplRowQty(page), { timeout: 5000 })
    .toBe(startingQty);

  await expect.poll(async () => await cashToNumber(cashLoc), { timeout: 5000 }).toBeGreaterThan(cashAfterBuy);
});
