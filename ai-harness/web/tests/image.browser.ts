import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

// Browser contract fixtures only. No inference, native image call or deployed evidence.
const sessionId = 'fixture/chat-a';
const initialRun = 'fixture/initial-run';
const secondRun = 'fixture/image-turn-2';
const at = '2026-09-23T10:00:00.000Z';
const source = {
  referenceId: 'fixture/reference-original',
  fileId: 'fixture/source-image',
  name: 'original-photo.png',
  sha256: 'a'.repeat(64),
  width: 2560,
  height: 1600,
};
const makeJob = (id: string, changes: Record<string, unknown> = {}) => ({
  id,
  revision: 1,
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
    sources: [
      {
        ...source,
        workingWidth: 1728,
        workingHeight: 1080,
        padding: { top: 0, right: 96, bottom: 0, left: 96 },
      },
    ],
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

test('detached image approval and rejection require real browser clicks while text is idle', async ({
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
  await expect(card(page, approve.id)).toContainText('1600');
  await expect(card(page, approve.id)).toContainText('1920');
  await expect(card(page, approve.id)).toContainText('1080');
  await expect(card(page, approve.id)).toContainText(source.name);
  await expect(card(page, approve.id)).toContainText('1728');
  await expect(card(page, approve.id)).toContainText('96');
  await expect(page.locator('.badge')).toHaveText('idle');
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
  expect((await calls(request)).filter((call) => call.action === 'image-approval-token')).toEqual(
    [],
  );
  await card(page, approve.id).scrollIntoViewIfNeeded();
  await evidence(page, 'image-approval-required.png');

  await card(page, approve.id).getByRole('button', { name: 'Approve resize', exact: true }).click();
  await expect(card(page, approve.id)).toContainText(/queued/i);
  await expect(page.locator('.badge')).toHaveText('idle');
  await expect(page.getByRole('button', { name: 'Stop all', exact: true })).toBeEnabled();
  await expect(
    card(page, approve.id).getByRole('button', { name: 'Approve resize', exact: true }),
  ).toHaveCount(0);
  await card(page, reject.id).getByRole('button', { name: 'Reject change', exact: true }).click();
  await expect(card(page, reject.id)).toContainText(/cancelled/i);
  expect((await calls(request)).filter((call) => call.action === 'image-approval')).toEqual([
    {
      action: 'image-approval',
      id: sessionId,
      jobId: approve.id,
      body: { decision: 'approve', approvalToken: 'fixture-approval-token-1' },
    },
    {
      action: 'image-approval',
      id: sessionId,
      jobId: reject.id,
      body: { decision: 'reject', approvalToken: 'fixture-approval-token-2' },
    },
  ]);
  expect((await calls(request)).filter((call) => call.action === 'send')).toEqual([]);
  const persisted = await (
    await request.get(`/api/sessions/${encodeURIComponent(sessionId)}/image-jobs`)
  ).json();
  expect(persisted.jobs.find((job: { id: string }) => job.id === approve.id).adjustment).toEqual(
    approve.adjustment,
  );
  expect(persisted.jobs.find((job: { id: string }) => job.id === approve.id).runId).toBe(
    initialRun,
  );
  expect(persisted.jobs.every((job: { revision: number }) => job.revision === 2)).toBe(true);
  expect(JSON.stringify(persisted)).not.toContain('approvalToken');
  await page.reload();
  await expect(card(page, approve.id)).toContainText(/queued/i);
  await expect(card(page, reject.id)).toContainText(/cancelled/i);
  await card(page, reject.id).scrollIntoViewIfNeeded();
  await evidence(page, 'image-rejection-persisted.png');
});

test('revision-ordered SSE and reconnect ignore stale jobs, allow requeue, and drain cancellation while text is idle', async ({
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
    revision: 2,
    state: 'running',
    queuePosition: undefined,
    startedAt: at,
    elapsedMs: 1500,
  });
  const started = await event(request, 'image_job', { job: active });
  await expect(card(page, active.id)).toContainText(/running/i);
  await request.post('/__fixture/replay', { data: { sessionId, id: started.id } });
  await expect(card(page, active.id)).toHaveCount(1);
  const staleRunning = active;
  active = makeJob(active.id, { ...active, revision: 3, state: 'queued', queuePosition: 4 });
  await event(request, 'image_job', { job: active });
  await expect(card(page, active.id).getByRole('status')).toHaveText('Queued');
  await event(request, 'image_job', { job: staleRunning });
  // A later visible frame confirms the preceding stale frame reached the UI.
  await event(request, 'context', {
    context: {
      used: 98765,
      limit: 480000,
      estimated: true,
      stale: false,
      updatedAt: at,
      source: 'fixture estimator',
    },
  });
  await expect(page.getByText(/98,765 \/ 480,000 tokens/)).toBeVisible();
  await expect(card(page, active.id).getByRole('status')).toHaveText('Queued');

  // No event carries this failure: the next connection must re-fetch persisted jobs.
  const failed = {
    ...later,
    revision: 2,
    state: 'failed',
    finishedAt: at,
    error: {
      code: 'unsupported_size',
      message: 'Editing at 1920x1080 is not qualified for two references.',
    },
  };
  await seed(request, [active, failed]);
  await request.post('/__fixture/images', {
    data: { sessionId, getJobs: [staleRunning, failed], omitImageEvents: true },
  });
  await request.post('/__fixture/disconnect', { data: { sessionId } });
  await expect(card(page, failed.id)).toContainText(failed.error.message);
  await expect(card(page, failed.id)).toContainText(/failed/i);
  await expect(page.locator('.connection')).toContainText('Connected');
  await expect(card(page, active.id).getByRole('status')).toHaveText('Queued');
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
  active = makeJob(active.id, {
    ...active,
    revision: 4,
    state: 'running',
    queuePosition: undefined,
  });
  await event(request, 'image_job', { job: active });
  await expect(card(page, active.id).getByRole('status')).toHaveText('Running');
  await expect(page.locator('.badge')).toHaveText('idle');

  await card(page, active.id)
    .getByRole('button', { name: 'Cancel image job', exact: true })
    .click();
  await expect(card(page, active.id)).toContainText(/drain/i);
  const running = (
    await (await request.get(`/api/sessions/${encodeURIComponent(sessionId)}/image-jobs`)).json()
  ).jobs.find((job: { id: string }) => job.id === active.id);
  expect(running.state).toBe('running');
  expect(running.cancelRequested).toBe(true);
  await event(request, 'image_job', {
    job: { ...running, revision: running.revision + 1, state: 'saving', elapsedMs: 2500 },
  });
  await expect(card(page, active.id)).toContainText(/saving/i);
  await event(request, 'image_job', {
    job: {
      ...running,
      revision: running.revision + 2,
      state: 'cancelled',
      finishedAt: at,
      elapsedMs: 3000,
    },
  });
  await expect(card(page, active.id)).toContainText(/cancelled/i);
  await page.reload();
  await expect(card(page, active.id)).toContainText(/cancelled/i);
  await expect(card(page, failed.id)).toContainText(failed.error.message);
  expect((await calls(request)).filter((call) => call.action === 'image-cancel')).toHaveLength(1);
  expect(errors).toEqual([]);
});

test('image reuse sends explicit artifact references and a later text reply preserves the original artifact association', async ({
  page,
  request,
}) => {
  const original = makeArtifact('fixture/generated-original', 'original-generation.png');
  const edited = makeArtifact('fixture/generated-edit', 'edited-version.png');
  const completed = makeJob('fixture/completed', {
    revision: 4,
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
  const snapshot = await (
    await request.get(`/api/sessions/${encodeURIComponent(sessionId)}`)
  ).json();
  const followup = snapshot.runs.find((run: { id: string }) => run.id !== initialRun);
  await event(
    request,
    'message',
    {
      message: {
        id: 'assistant/followup-final',
        runId: followup.id,
        role: 'assistant',
        phase: 'final',
        streamState: 'completed',
        content: 'Follow-up complete. The earlier versions are preserved.',
        createdAt: at,
      },
    },
    followup.id,
  );
  await event(
    request,
    'run',
    {
      run: {
        ...followup,
        status: 'completed',
        finalMessageId: 'assistant/followup-final',
        artifactIds: [],
      },
    },
    followup.id,
  );
  await event(request, 'state', { status: 'idle' }, followup.id);
  await expect(
    page.getByText('Follow-up complete. The earlier versions are preserved.', { exact: true }),
  ).toBeVisible();
  for (const artifact of [original, edited]) {
    await expect(page.getByRole('img', { name: artifact.name, exact: true })).toHaveCount(1);
    await expect(reply.getByRole('img', { name: artifact.name, exact: true })).toHaveCount(1);
    await expect(
      page
        .locator(`[data-run-id="${followup.id}"]`)
        .getByRole('img', { name: artifact.name, exact: true }),
    ).toHaveCount(0);
  }
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
        ready: true,
        admitting: true,
        busy: false,
        state: 'ready',
        model: 'Qwen-Image-2.1',
        profiles: [
          {
            operation: 'generation',
            size: '1920x1080',
            references: 0,
            transparent: false,
            evidence_sha256: 'a'.repeat(64),
            native_size: '1920x1088',
            crop_bottom: 8,
          },
        ],
        defaults: { size: '1024x1024' },
        limits: { n: 1 },
        masks: false,
        response_format: 'b64_json',
        output_format: 'png',
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

for (const failure of ['denied', 'expired'] as const) {
  test(`approval ${failure} remains pending and a new user click obtains a fresh token`, async ({
    page,
    request,
  }) => {
    const job = makeJob(`fixture/token-${failure}`);
    await seed(request, [job]);
    await request.post('/__fixture/images', {
      data: { sessionId, approvalFailures: { [job.id]: failure } },
    });
    await page.goto('/');
    const approve = card(page, job.id).getByRole('button', { name: 'Approve resize', exact: true });
    await expect(approve).toBeEnabled();
    expect(
      (await calls(request)).filter((call) => call.action === 'image-approval-token'),
    ).toHaveLength(0);
    await approve.click();
    await expect(page.getByRole('alert')).toContainText(
      failure === 'expired' ? 'token expired' : 'unavailable from this browser origin',
    );
    await expect(card(page, job.id).getByRole('status')).toHaveText('Awaiting your approval');
    await expect(approve).toBeEnabled();
    const failedCalls = await calls(request);
    expect(failedCalls.filter((call) => call.action === 'image-approval-token')).toHaveLength(1);
    expect(failedCalls.filter((call) => call.action === 'image-approval')).toHaveLength(
      failure === 'expired' ? 1 : 0,
    );
    await approve.click();
    await expect(card(page, job.id).getByRole('status')).toHaveText('Queued');
    const requests = await calls(request);
    expect(requests.filter((call) => call.action === 'image-approval-token')).toHaveLength(2);
    const decisions = requests.filter((call) => call.action === 'image-approval');
    expect(decisions).toHaveLength(failure === 'expired' ? 2 : 1);
    if (failure === 'expired')
      expect((decisions[0].body as { approvalToken: string }).approvalToken).not.toBe(
        (decisions[1].body as { approvalToken: string }).approvalToken,
      );
    await expect(page.locator('body')).not.toContainText('fixture-approval-token-');
    const persisted = await (
      await request.get(`/api/sessions/${encodeURIComponent(sessionId)}/image-jobs`)
    ).json();
    expect(persisted.jobs[0].revision).toBe(2);
    expect(JSON.stringify(persisted)).not.toContain('approvalToken');
  });
}
