import { test, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
const evidence = resolve(
  process.env.H002_WEB_EVIDENCE ?? process.env.H001_WEB_EVIDENCE ?? '../../../evidence',
);
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
  await page.getByLabel('Upload file').setInputFiles({
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
  await page.getByRole('button', { name: 'Stop all', exact: true }).click();
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
  await expect(page.getByText('0 / 480,000 tokens · 0%')).toBeVisible();
  await page.getByLabel('Upload file').setInputFiles({
    name: 'photo.png',
    mimeType: 'image/png',
    buffer: Buffer.from('fixture bytes, not a real model input'),
  });
  await expect(page.getByText('photo.png', { exact: true })).toBeVisible();
  await expect(page.getByText(/PDF, source, text and image files/)).toBeVisible();
  const { calls } = await (await request.get('/__fixture/calls')).json();
  expect(calls.filter((call: { action: string }) => call.action === 'create')).toHaveLength(1);
  expect(calls.find((call: { action: string }) => call.action === 'upload').field).toBe(true);
});

test('v0.0.2 fixture: progress settles, lifecycle stays singular and reply files stay scoped', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1440, height: 1080 });
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'Investigate a streaming pipeline' }),
  ).toBeVisible();
  const initialReply = page.locator('[data-run-id="fixture/initial-run"]');
  await expect(initialReply.locator('.progress-panel')).not.toHaveAttribute('open', '');
  await expect(initialReply.getByRole('img', { name: 'pipeline.svg' })).toBeVisible();
  await expect(initialReply.getByRole('img', { name: 'pipeline.svg' })).toHaveJSProperty(
    'naturalWidth',
    600,
  );
  const uploaded = page.getByRole('link', { name: 'sample-log.txt', exact: true });
  await expect(uploaded).toHaveAttribute(
    'href',
    '/api/attachments/fixture%2Finitial-upload/download',
  );
  const zip = initialReply.getByRole('link', { name: 'Download all ZIP' });
  await expect(zip).toHaveAttribute(
    'href',
    '/api/sessions/fixture%2Fchat-a/runs/fixture%2Finitial-run/artifacts.zip',
  );
  const zipDownload = page.waitForEvent('download');
  await zip.click();
  expect((await zipDownload).suggestedFilename()).toBe('fixture-reply.zip');
  const zipCalls = (await (await request.get('/__fixture/calls')).json()).calls.filter(
    (call: { action: string }) => call.action === 'zip',
  );
  expect(zipCalls).toEqual([{ action: 'zip', id, runId: 'fixture/initial-run' }]);
  const input = page.getByRole('textbox', { name: 'Message' });
  await input.fill('Check a second turn');
  await input.press('Enter');
  await expect(input).toHaveValue('Check a second turn\n');
  await input.press('Control+Enter');
  await expect(page.getByText('Checking the fixture pipeline', { exact: true })).toBeVisible();
  const snapshot = await (await request.get('/api/sessions/' + encodeURIComponent(id))).json();
  const run = snapshot.runs.find((run: { status: string }) => run.status === 'running');
  const intermediate = snapshot.messages.find(
    (message: { runId: string; role: string }) =>
      message.runId === run.id && message.role === 'assistant',
  );
  const activity = snapshot.activities.find(
    (activity: { runId: string }) => activity.runId === run.id,
  );
  const reply = page.locator(`[data-run-id="${run.id}"]`);
  await expect(reply.locator('.progress-panel')).toHaveAttribute('open', '');
  await request.post('/__fixture/event', {
    data: {
      sessionId: id,
      type: 'subagents',
      runId: run.id,
      data: {
        runId: run.id,
        summary: { known: true, active: 2, completed: 0, failed: 0, cancelled: 0 },
      },
    },
  });
  const working = page.getByRole('status', { name: 'Run status' });
  await expect(working).toContainText('Active subagents: 2');
  expect(await working.evaluate((element) => element.closest('.composer') === null)).toBe(true);
  await mkdir(evidence, { recursive: true });
  await page.evaluate(() => {
    const label = document.createElement('div');
    label.textContent = 'v0.0.2 FIXTURE · NOT LIVE INFERENCE';
    label.style.cssText =
      'position:fixed;top:0;right:0;background:#303a31;color:white;padding:5px 10px;font:10px monospace;z-index:100;';
    document.body.append(label);
  });
  await page.screenshot({
    path: resolve(evidence, 'v002-fixture-desktop-running.png'),
    fullPage: true,
  });
  const finishedAt = '2026-09-22T10:24:04.000Z';
  for (const status of ['pending', 'in_progress', 'completed']) {
    await request.post('/__fixture/event', {
      data: {
        sessionId: id,
        type: 'activity',
        runId: run.id,
        data: {
          activity: {
            ...activity,
            status,
            updatedAt: finishedAt,
            ...(status === 'completed' ? { finishedAt } : {}),
          },
        },
      },
    });
  }
  await request.post('/__fixture/event', {
    data: {
      sessionId: id,
      type: 'message',
      runId: run.id,
      data: { message: { ...intermediate, streamState: 'completed' } },
    },
  });
  await request.post('/__fixture/event', {
    data: {
      sessionId: id,
      type: 'message',
      runId: run.id,
      data: {
        message: {
          id: 'assistant/final-second',
          role: 'assistant',
          content: 'The second turn has its own final answer and output file.',
          phase: 'final',
          streamState: 'completed',
          createdAt: finishedAt,
          runId: run.id,
        },
      },
    },
  });
  await request.post('/__fixture/event', {
    data: {
      sessionId: id,
      type: 'artifact',
      runId: run.id,
      data: {
        artifact: {
          id: 'fixture/second-notes',
          name: 'second-turn.txt',
          mimeType: 'text/plain',
          size: 48,
          downloadUrl: '/api/artifacts/fixture%2Fsecond-notes/download',
          runId: run.id,
          messageId: 'assistant/final-second',
        },
      },
    },
  });
  await request.post('/__fixture/event', {
    data: {
      sessionId: id,
      type: 'run',
      runId: run.id,
      data: {
        run: {
          ...run,
          status: 'completed',
          finalMessageId: 'assistant/final-second',
          artifactIds: ['fixture/second-notes'],
          subagents: { known: true, active: 0, completed: 2, failed: 0, cancelled: 0 },
          updatedAt: finishedAt,
        },
      },
    },
  });
  await request.post('/__fixture/event', {
    data: { sessionId: id, type: 'state', runId: run.id, data: { status: 'idle' } },
  });
  await request.post('/__fixture/event', {
    data: { sessionId: id, type: 'done', runId: run.id, data: { runId: run.id } },
  });
  await expect(reply.getByRole('region', { name: 'Final answer' })).toBeVisible();
  await expect(reply.locator('.progress-panel')).not.toHaveAttribute('open', '');
  await reply.locator('.progress-panel > summary').click();
  await expect(reply.getByText('Checking the fixture pipeline', { exact: true })).toBeVisible();
  await reply.locator('.activity > summary').click();
  await expect(
    reply.getByRole('list', { name: 'Lifecycle activity' }).locator(':scope > li'),
  ).toHaveCount(1);
  await expect(reply.getByText('npm test -- fixture', { exact: true })).toBeVisible();
  await expect(reply.getByText('4.0 s', { exact: false })).toBeVisible();
  await expect(reply.getByRole('link', { name: /second-turn.txt/ })).toBeVisible();
  await expect(reply.getByRole('link', { name: 'Download all ZIP' })).toHaveCount(0);
  await expect(initialReply.getByRole('link', { name: /second-turn.txt/ })).toHaveCount(0);
  await expect(working).toContainText('Active subagents: 0');
  await page.screenshot({
    path: resolve(evidence, 'v002-fixture-desktop-final.png'),
    fullPage: true,
  });
  await page.reload();
  await expect(reply.locator('.progress-panel')).not.toHaveAttribute('open', '');
  await expect(reply.getByRole('link', { name: /second-turn.txt/ })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(input).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({
    path: resolve(evidence, 'v002-fixture-mobile-final.png'),
    fullPage: true,
  });
});
