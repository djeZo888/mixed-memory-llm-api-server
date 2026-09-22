import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
const evidence = resolve(process.env.H001_WEB_EVIDENCE ?? '../../../evidence');
const id = 'fixture/chat-a';
test.beforeEach(async ({ request }) => {
  await request.post('/__fixture/reset');
});
test('desktop contract fixture: send, upload, stop, reconnect, handoff, download and 202 delete', async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1080 });
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'Investigate a streaming pipeline' }),
  ).toBeVisible();
  await expect(page.getByText('Estimated context')).toBeVisible();
  await expect(page.getByText('123,456 / 480,000 tokens · 25.7%')).toBeVisible();
  await mkdir(evidence, { recursive: true });
  // Labels are test-run overlays, never shipped application content.
  await page.evaluate(() => {
    const label = document.createElement('div');
    label.id = 'fixture-label';
    label.textContent = 'CONTRACT FIXTURE · NOT LIVE INFERENCE';
    label.style.cssText =
      'position:fixed;top:0;right:0;background:#303a31;color:white;padding:5px 10px;font:10px monospace;z-index:100;';
    document.body.append(label);
  });
  await page.screenshot({
    path: resolve(evidence, 'fixture-desktop-conversation.png'),
    fullPage: true,
  });
  const artifact = page.getByRole('link', { name: /streaming-review.md/ });
  await expect(artifact).toHaveAttribute(
    'href',
    '/api/artifacts/fixture%2Freview%20notes/download',
  );
  const download = page.waitForEvent('download');
  await artifact.click();
  expect((await download).suggestedFilename()).toBe('streaming-review.md');
  await page
    .getByLabel('Upload file')
    .setInputFiles({
      name: 'notes.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('fixture notes'),
    });
  await expect(page.getByText('notes.txt', { exact: true })).toBeVisible();
  await page.getByRole('textbox', { name: 'Message' }).fill('Review the attached notes');
  await page.getByRole('button', { name: 'Send message' }).click();
  await expect(page.getByText('Checking the fixture pipeline', { exact: true })).toBeVisible();
  let response = await request.get('/__fixture/calls');
  let calls = (await response.json()).calls;
  expect(
    calls.find((call: { action: string; field?: boolean }) => call.action === 'upload').field,
  ).toBe(true);
  expect(
    calls.find((call: { action: string }) => call.action === 'send').attachmentIds,
  ).toHaveLength(1);
  const live = await request.get('/api/sessions/' + encodeURIComponent(id));
  const history = await live.json();
  const delta = history.events.find((event: { type: string }) => event.type === 'assistant_delta');
  await request.post('/__fixture/replay', { data: { sessionId: id, id: delta.id } });
  await expect(page.getByText('Checking the fixture pipeline', { exact: true })).toHaveCount(1);
  await request.post('/__fixture/disconnect', { data: { sessionId: id } });
  await request.post('/__fixture/event', {
    data: {
      sessionId: id,
      type: 'assistant_delta',
      data: { messageId: delta.data.messageId, text: ' after reconnect.' },
    },
  });
  await expect(
    page.getByText('Checking the fixture pipeline after reconnect.', { exact: true }),
  ).toBeVisible();
  await expect(page.locator('.connection')).toContainText('Connected');
  response = await request.get('/__fixture/calls');
  calls = (await response.json()).calls;
  expect(
    calls.filter((call: { action: string }) => call.action === 'subscribe').length,
  ).toBeGreaterThan(1);
  expect(calls.filter((call: { action: string }) => call.action === 'cancel')).toHaveLength(0);
  await page.reload();
  await expect(
    page.getByText('Checking the fixture pipeline after reconnect.', { exact: true }),
  ).toBeVisible();
  expect(
    (await (await request.get('/__fixture/calls')).json()).calls.filter(
      (call: { action: string }) => call.action === 'cancel',
    ),
  ).toHaveLength(0);
  await page.getByRole('button', { name: 'Stop', exact: true }).click();
  await expect(page.locator('.badge')).toHaveText('interrupted');
  await page.getByRole('button', { name: 'Continue in new chat' }).click();
  await expect(page.getByRole('heading', { name: 'Continued: streaming pipeline' })).toBeVisible();
  await expect(
    page.getByRole('button', { name: /Investigate a streaming pipeline interrupted/ }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Delete chat Continued: streaming pipeline' }).click();
  await page.getByRole('button', { name: 'Delete chat', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Delete chat Continued: streaming pipeline' }),
  ).toHaveCount(0);
  await expect(
    page.getByRole('heading', { name: 'Investigate a streaming pipeline' }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByText('Review the attached notes', { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});
test('mobile fixture: no horizontal overflow, sidebar focus, unknown context and real status events', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('textbox', { name: 'Message' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'New chat', exact: true })).not.toBeVisible();
  await page.keyboard.press('Tab');
  expect(await page.evaluate(() => document.activeElement?.closest('aside') === null)).toBe(true);
  await page.getByRole('button', { name: 'Open chat list' }).click();
  await expect(page.getByRole('button', { name: 'New chat', exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Open chat list' })).toBeFocused();
  await request.post('/__fixture/event', {
    data: {
      sessionId: id,
      type: 'context',
      data: {
        context: {
          used: null,
          limit: 480000,
          estimated: true,
          stale: true,
          updatedAt: '2026-09-22T10:24:00Z',
        },
      },
    },
  });
  await expect(page.getByText('Context unavailable · stale')).toBeVisible();
  await expect(page.getByRole('meter')).toHaveCount(0);
  for (const status of [
    'queued',
    'running',
    'compacting',
    'cancelling',
    'interrupted',
    'failed',
    'idle',
  ]) {
    await request.post('/__fixture/event', {
      data: { sessionId: id, type: 'state', data: { status } },
    });
    await expect(page.locator('.badge')).toHaveText(status);
  }
  await page.evaluate(() => {
    const label = document.createElement('div');
    label.textContent = 'FIXTURE · NOT LIVE';
    label.style.cssText =
      'position:fixed;top:0;right:0;background:#303a31;color:white;padding:3px 7px;font:8px monospace;z-index:100;';
    document.body.append(label);
  });
  await mkdir(evidence, { recursive: true });
  await page.screenshot({
    path: resolve(evidence, 'fixture-mobile-conversation.png'),
    fullPage: true,
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page
    .getByLabel('Upload file')
    .setInputFiles({ name: 'photo.png', mimeType: 'image/png', buffer: Buffer.from('fixture') });
  await expect(page.getByRole('alert')).toContainText('Image uploads are unavailable');
});

test('fixture new-chat and image callback are gated by explicit health capability', async ({
  page,
  request,
}) => {
  await request.post('/__fixture/vision', { data: { enabled: true } });
  await page.goto('/');
  await page.getByRole('button', { name: 'New chat', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'New fixture conversation' })).toBeVisible();
  await page
    .getByLabel('Upload file')
    .setInputFiles({
      name: 'photo.png',
      mimeType: 'image/png',
      buffer: Buffer.from('fixture bytes, not a real model input'),
    });
  await expect(page.getByText('photo.png', { exact: true })).toBeVisible();
  await expect(page.getByText('PDF, source, text and image files')).toBeVisible();
  const { calls } = await (await request.get('/__fixture/calls')).json();
  expect(calls.filter((call: { action: string }) => call.action === 'create')).toHaveLength(1);
  expect(calls.find((call: { action: string }) => call.action === 'upload').field).toBe(true);
});
