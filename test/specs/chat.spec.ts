import { test, expect } from '@playwright/test';

test('chat panel sends a message and receives a response', async ({ page }) => {
  await page.goto('/');

  const input = page.getByTestId('chat-input');
  const send = page.getByTestId('chat-send');
  await expect(input).toBeVisible({ timeout: 10000 });

  await input.fill('What is my cash balance?');
  await send.click();

  await expect(page.getByTestId('chat-msg-user').last()).toContainText(/cash balance/i, { timeout: 5000 });

  const assistant = page.getByTestId('chat-msg-assistant').last();
  await expect(assistant).toBeVisible({ timeout: 15000 });
  const text = (await assistant.textContent()) ?? '';
  expect(text.trim().length).toBeGreaterThan(0);
});
