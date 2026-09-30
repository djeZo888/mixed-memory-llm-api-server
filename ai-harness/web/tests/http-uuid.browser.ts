import { test, expect } from '@playwright/test';

// Resolve a non-localhost HTTP origin to the local fixture, so Chromium uses
// its real insecure-context API boundary instead of mocking randomUUID away.
test.use({ launchOptions: { args: ['--host-resolver-rules=MAP h036-http.test 127.0.0.1'] } });

test.beforeEach(async ({ request }) => {
  await request.post('/__fixture/reset');
});

test('plain HTTP composer submits a secure v4 UUID when randomUUID is unavailable', async ({ page, request }) => {
  await page.goto('http://h036-http.test:4193/');
  expect(await page.evaluate(() => ({
    secure: isSecureContext,
    uuid: typeof crypto.randomUUID,
    random: typeof crypto.getRandomValues,
  }))).toEqual({ secure: false, uuid: 'undefined', random: 'function' });
  const composer = page.getByRole('textbox', { name: 'Message' });
  await composer.fill('Check secure HTTP submission IDs');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText('Checking the fixture pipeline', { exact: true })).toBeVisible();
  const { calls } = await (await request.get('/__fixture/calls')).json();
  const sends = calls.filter((call: { action: string }) => call.action === 'send');
  expect(sends).toHaveLength(1);
  expect(sends[0].submissionId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  expect(sends[0].text).toBe('Check secure HTTP submission IDs');
  await expect(composer).toHaveValue('');
});

test('composer retains the draft and makes no POST if secure randomness is unavailable', async ({ page, request }) => {
  await page.addInitScript(() => {
    Object.defineProperty(crypto, 'getRandomValues', { value: undefined });
  });
  await page.goto('http://h036-http.test:4193/');
  const composer = page.getByRole('textbox', { name: 'Message' });
  await composer.fill('Retain this unsent draft');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByRole('alert')).toContainText('Secure random IDs are unavailable');
  await expect(composer).toHaveValue('Retain this unsent draft');
  const { calls } = await (await request.get('/__fixture/calls')).json();
  expect(calls.filter((call: { action: string }) => call.action === 'send')).toHaveLength(0);
});
