import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

// Browser contract fixtures only. No inference, native image call or deployed evidence.
const sessionId = 'fixture/chat-a';
const initialRun = 'fixture/initial-run';
const secondRun = 'fixture/image-turn-2';
const at = '2026-09-23T10:00:00.000Z';
const source = {
  fileId: 'fixture/source-image',
  name: 'original-photo.png',
  sha256: 'a'.repeat(64),
  width: 2560,
  height: 1440,
};
const makeJob = (id: string, changes: Record<string, unknown> = {}) => ({
  id,
  sessionId,
  runId: initialRun,
  requestId: `request-${id}`,
  operation: 'edit',
  state: 'awaiting_approval',
  model: 'Qwen-Image-2.1',
  prompt: 'Change the cup to blue; preserve the scene.',
  seed: 42,
  requestedSize: '1920x1080',
  references: [source],
  createdAt: at,
  cancelRequested: false,
  adjustment: {
    sources: [source],
    targetSize: '1920x1080',
    reason:
      'Fit the original proportionally within the qualified canvas; no cropping or stretching.',
  },
  ...changes,
});
const makeArtifact = (id: string, name: string, runId = initialRun) => ({
  id,
  name,
  runId,
  messageId: runId === initialRun ? 'assistant/initial' : 'assistant/image-turn-2',
  mimeType: 'image/png',
  size: 12345,
  downloadUrl: `/api/artifacts/${encodeURIComponent(id)}/download`,
  previewUrl: `/api/files/${encodeURIComponent(id)}/preview`,
});
async function event(request: APIRequestContext, type: string, data: unknown, runId = initialRun) {
  const response = await request.post('/__fixture/event', {
    data: { sessionId, type, data, runId },
  });
  expect(response.ok()).toBe(true);
  return (await response.json()).event;
}
async function secondReply(request: APIRequestContext) {
  await event(
    request,
    'run',
    {
      run: {
        id: secondRun,
        kind: 'message',
        status: 'completed',
        createdAt: at,
        updatedAt: at,
        finalMessageId: 'assistant/image-turn-2',
        artifactIds: [],
        subagents: { known: true, active: 0, completed: 0, failed: 0, cancelled: 0 },
      },
    },
    secondRun,
  );
  await event(
    request,
    'message',
    {
      message: {
        id: 'assistant/image-turn-2',
        role: 'assistant',
        content: 'The second turn has its own image request.',
        runId: secondRun,
        createdAt: at,
        phase: 'final',
        streamState: 'completed',
      },
    },
    secondRun,
  );
}
const card = (page: Page, id: string) =>
  page.getByRole('region', { name: `Image job ${id}`, exact: true });
async function calls(request: APIRequestContext) {
  return (await (await request.get('/__fixture/calls')).json()).calls as Array<
    Record<string, unknown>
  >;
}
async function seed(
  request: APIRequestContext,
  jobs: ReturnType<typeof makeJob>[],
  artifacts: ReturnType<typeof makeArtifact>[] = [],
) {
  expect(
    (await request.post('/__fixture/images', { data: { sessionId, jobs, artifacts } })).ok(),
  ).toBe(true);
}
async function evidence(page: Page, name: string) {
  const root = resolve(process.env.H003_WEB_EVIDENCE ?? '../../.h003-evidence/browser');
  await mkdir(root, { recursive: true });
  await page.evaluate(() => {
    if (document.getElementById('image-fixture-label')) return;
    const label = document.createElement('div');
    label.id = 'image-fixture-label';
    label.textContent = 'IMAGE CONTRACT FIXTURE · NOT LIVE INFERENCE';
    label.style.cssText =
      'position:fixed;top:0;right:0;background:#303a31;color:white;padding:5px 10px;font:10px monospace;z-index:100;';
    document.body.append(label);
  });
  await page.screenshot({ path: resolve(root, name), fullPage: true });
}

test.beforeEach(async ({ request }) => {
  await request.post('/__fixture/reset');
});

test('image approval and rejection use real browser clicks bound to their stored jobs', async ({
  page,
  request,
}) => {
  await secondReply(request);
  const approve = makeJob('fixture/approve');
  const reject = makeJob('fixture/reject', { runId: secondRun, seed: 7 });
  await seed(request, [approve, reject]);
  await page.setViewportSize({ width: 1440, height: 1080 });
  await page.goto('/');
  await expect(card(page, approve.id)).toBeVisible();
  await expect(card(page, approve.id)).toContainText('2560');
  await expect(card(page, approve.id)).toContainText('1440');
  await expect(card(page, approve.id)).toContainText('1920');
  await expect(card(page, approve.id)).toContainText('1080');
  await expect(card(page, approve.id)).toContainText(source.name);
  await expect(card(page, approve.id)).toContainText(approve.adjustment.reason);
  await expect(
    page
      .locator(`[data-run-id="${initialRun}"]`)
      .getByRole('region', { name: `Image job ${approve.id}`, exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(`[data-run-id="${secondRun}"]`)
      .getByRole('region', { name: `Image job ${reject.id}`, exact: true }),
  ).toBeVisible();
  expect((await calls(request)).filter((call) => call.action === 'image-approval')).toEqual([]);
  await card(page, approve.id).scrollIntoViewIfNeeded();
  await evidence(page, 'image-approval-required.png');

  await card(page, approve.id).getByRole('button', { name: 'Approve resize', exact: true }).click();
  await expect(card(page, approve.id)).toContainText(/queued/i);
  await expect(
    card(page, approve.id).getByRole('button', { name: 'Approve resize', exact: true }),
  ).toHaveCount(0);
  await card(page, reject.id).getByRole('button', { name: 'Reject change', exact: true }).click();
  await expect(card(page, reject.id)).toContainText(/cancelled/i);
  expect((await calls(request)).filter((call) => call.action === 'image-approval')).toEqual([
    { action: 'image-approval', id: sessionId, jobId: approve.id, body: { decision: 'approve' } },
    { action: 'image-approval', id: sessionId, jobId: reject.id, body: { decision: 'reject' } },
  ]);
  expect((await calls(request)).filter((call) => call.action === 'send')).toEqual([]);
  const persisted = await (
    await request.get(`/api/sessions/${encodeURIComponent(sessionId)}/image-jobs`)
  ).json();
  expect(persisted.jobs.find((job: { id: string }) => job.id === approve.id).adjustment).toEqual(
    approve.adjustment,
  );
  await page.reload();
  await expect(card(page, approve.id)).toContainText(/queued/i);
  await expect(card(page, reject.id)).toContainText(/cancelled/i);
  await card(page, reject.id).scrollIntoViewIfNeeded();
  await evidence(page, 'image-rejection-persisted.png');
});

test('image SSE and reconnect snapshots retain run association and cancellation drains active work', async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await secondReply(request);
  let active = makeJob('fixture/active', {
    operation: 'generation',
    state: 'queued',
    references: [],
    adjustment: undefined,
    queuePosition: 2,
  });
  const later = makeJob('fixture/later', {
    runId: secondRun,
    state: 'queued',
    queuePosition: 3,
    adjustment: undefined,
  });
  await seed(request, [active, later]);
  await page.goto('/');
  await expect(card(page, active.id)).toContainText(/queued/i);
  await expect(card(page, active.id)).toContainText('2');
  active = makeJob(active.id, {
    ...active,
    state: 'running',
    queuePosition: undefined,
    startedAt: at,
    elapsedMs: 1500,
  });
  const started = await event(request, 'image_job', { job: active });
  await expect(card(page, active.id)).toContainText(/running/i);
  await request.post('/__fixture/replay', { data: { sessionId, id: started.id } });
  await expect(card(page, active.id)).toHaveCount(1);

  // No event carries this failure: the next connection must re-fetch persisted jobs.
  const failed = {
    ...later,
    state: 'failed',
    finishedAt: at,
    error: {
      code: 'unsupported_size',
      message: 'Editing at 1920x1080 is not qualified for two references.',
    },
  };
  await seed(request, [active, failed]);
  await request.post('/__fixture/disconnect', { data: { sessionId } });
  await expect(card(page, failed.id)).toContainText(failed.error.message);
  await expect(card(page, failed.id)).toContainText(/failed/i);
  await expect(page.locator('.connection')).toContainText('Connected');
  await expect(
    page
      .locator(`[data-run-id="${secondRun}"]`)
      .getByRole('region', { name: `Image job ${failed.id}`, exact: true }),
  ).toBeVisible();
  await expect(
    page
      .locator(`[data-run-id="${secondRun}"]`)
      .getByRole('region', { name: `Image job ${active.id}`, exact: true }),
  ).toHaveCount(0);
  expect(
    (await calls(request)).filter((call) => call.action === 'image-jobs').length,
  ).toBeGreaterThan(1);
  expect((await calls(request)).filter((call) => call.action === 'image-cancel')).toEqual([]);

  await card(page, active.id)
    .getByRole('button', { name: 'Cancel image job', exact: true })
    .click();
  await expect(card(page, active.id)).toContainText(/drain/i);
  const running = (
    await (await request.get(`/api/sessions/${encodeURIComponent(sessionId)}/image-jobs`)).json()
  ).jobs.find((job: { id: string }) => job.id === active.id);
  expect(running.state).toBe('running');
  expect(running.cancelRequested).toBe(true);
  await event(request, 'image_job', { job: { ...running, state: 'saving', elapsedMs: 2500 } });
  await expect(card(page, active.id)).toContainText(/saving/i);
  await event(request, 'image_job', {
    job: { ...running, state: 'cancelled', finishedAt: at, elapsedMs: 3000 },
  });
  await expect(card(page, active.id)).toContainText(/cancelled/i);
  await page.reload();
  await expect(card(page, active.id)).toContainText(/cancelled/i);
  await expect(card(page, failed.id)).toContainText(failed.error.message);
  expect((await calls(request)).filter((call) => call.action === 'image-cancel')).toHaveLength(1);
  expect(errors).toEqual([]);
});

test('generated image preview, download and reuse preserve originals and send explicit artifact references', async ({
  page,
  request,
}) => {
  const original = makeArtifact('fixture/generated-original', 'original-generation.png');
  const edited = makeArtifact('fixture/generated-edit', 'edited-version.png');
  const completed = makeJob('fixture/completed', {
    operation: 'generation',
    state: 'completed',
    references: [],
    adjustment: undefined,
    actualSize: '1920x1080',
    artifactId: original.id,
    finishedAt: at,
    elapsedMs: 2500,
  });
  await seed(request, [completed], [original, edited]);
  await page.setViewportSize({ width: 1440, height: 1080 });
  await page.goto('/');
  const reply = page.locator(`[data-run-id="${initialRun}"]`);
  await expect(card(page, completed.id)).toContainText(/completed/i);
  await expect(card(page, completed.id)).toContainText('42');
  await expect(card(page, completed.id)).toContainText('Qwen-Image-2.1');
  await expect(reply.getByRole('img', { name: original.name, exact: true })).toHaveJSProperty(
    'naturalWidth',
    1920,
  );
  await expect(reply.getByRole('img', { name: edited.name, exact: true })).toHaveJSProperty(
    'naturalHeight',
    1080,
  );
  const download = page.waitForEvent('download');
  await reply.getByRole('link', { name: new RegExp(original.name) }).click();
  expect((await download).suggestedFilename()).toBe(original.name);
  const zip = page.waitForEvent('download');
  await reply.getByRole('link', { name: 'Download all ZIP', exact: true }).click();
  expect((await zip).suggestedFilename()).toBe('fixture-reply.zip');
  await reply.getByRole('img', { name: edited.name, exact: true }).scrollIntoViewIfNeeded();
  await evidence(page, 'image-original-and-edit-previews.png');

  // Select only the edited version, then independently attach an ordinary file.
  await reply
    .locator('.artifact-entry')
    .filter({ hasText: edited.name })
    .getByRole('button', { name: 'Use for next edit', exact: true })
    .click();
  await page.getByLabel('Upload file').setInputFiles({
    name: 'instructions.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('Keep the original composition.'),
  });
  await page
    .getByRole('textbox', { name: 'Message', exact: true })
    .fill('Make the handle green in this edited image.');
  await expect(
    page.getByRole('list', { name: 'Image edit references', exact: true }),
  ).toContainText(edited.name);
  await page.getByRole('textbox', { name: 'Message', exact: true }).scrollIntoViewIfNeeded();
  await evidence(page, 'image-composer-references-before-send.png');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(page.getByText('Checking the fixture pipeline', { exact: true })).toBeVisible();
  const submitted = (await calls(request)).find((call) => call.action === 'send');
  expect(submitted?.imageReferences).toEqual([edited.id]);
  expect(submitted?.attachmentIds).toHaveLength(1);
  expect(submitted?.attachmentIds).not.toContain(edited.id);
  await expect(reply.getByRole('img', { name: original.name, exact: true })).toBeVisible();
  await expect(reply.getByRole('img', { name: edited.name, exact: true })).toBeVisible();
  await expect(reply.getByRole('link', { name: new RegExp(original.name) })).toBeVisible();
});

test('generation capability never enables editing when edit profiles are unavailable', async ({
  page,
  request,
}) => {
  const original = makeArtifact('fixture/generated-original', 'original-generation.png');
  await request.post('/__fixture/images', {
    data: {
      sessionId,
      artifacts: [original],
      capabilities: {
        model: 'Qwen-Image-2.1',
        operations: {
          generation: { available: true, profiles: [{ referenceCount: 0, sizes: ['1920x1080'] }] },
          edit: { available: true, profiles: [] },
        },
      },
    },
  });
  await page.goto('/');
  const reuse = page
    .locator('.artifact-entry')
    .filter({ hasText: original.name })
    .getByRole('button', { name: 'Use for next edit', exact: true });
  await expect(reuse).toBeDisabled();
  await expect(reuse).toHaveAttribute('title', /unavailable|not qualified|no qualified/i);
  await expect(page.getByRole('list', { name: 'Image edit references', exact: true })).toHaveCount(
    0,
  );
  expect((await calls(request)).filter((call) => call.action === 'send')).toEqual([]);
  expect(
    (await calls(request)).filter((call) => call.action === 'image-capabilities').length,
  ).toBeGreaterThanOrEqual(1);
});
