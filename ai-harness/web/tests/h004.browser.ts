import { test, expect } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const evidence = resolve(process.env.H004_WEB_EVIDENCE ?? '../../../evidence');
const sessionId = 'fixture/chat-a';
const zipEntries = (buffer: Buffer) => {
  const files = new Map<string, Buffer>();
  let offset = 0;
  while (buffer.readUInt32LE(offset) === 0x04034b50) {
    const length = buffer.readUInt32LE(offset + 18),
      nameLength = buffer.readUInt16LE(offset + 26),
      extraLength = buffer.readUInt16LE(offset + 28);
    const name = buffer.subarray(offset + 30, offset + 30 + nameLength).toString();
    const start = offset + 30 + nameLength + extraLength;
    files.set(name, buffer.subarray(start, start + length));
    offset = start + length;
  }
  return files;
};
test.beforeEach(async ({ request }) => {
  await request.post('/__fixture/reset');
  await request.post('/__fixture/h004');
});
test('H004 stored reply: narrative images, discoverable ZIP downloads and scoped contents', async ({
  page,
  request,
}) => {
  const errors: string[] = [],
    remote: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    if (!request.url().startsWith('http://127.0.0.1:4193/')) remote.push(request.url());
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/');
  await page.evaluate(() => {
    const label = document.createElement('div');
    label.textContent = 'H004 FIXTURE · NO MODEL CALLS';
    label.style.cssText =
      'position:fixed;top:0;right:0;padding:4px 8px;background:#29483b;color:white;font:10px monospace;z-index:100';
    document.body.append(label);
  });
  const reply = page.locator('[data-run-id="fixture/initial-run"]'),
    final = reply.getByLabel('Final answer'),
    additional = reply.locator('.additional-image-previews');
  await expect(final.locator('img')).toHaveCount(10);
  await expect(page.locator('.connection')).toContainText('Connected');
  await expect(additional).not.toHaveAttribute('open', '');
  await expect(additional.locator('summary')).toContainText('Additional image previews');
  await expect(additional.locator('img')).toHaveCount(9);
  await expect(additional.locator('img').first()).not.toBeVisible();
  const fileEntries = reply.locator('.artifact-entry');
  await expect(fileEntries).toHaveCount(20);
  await expect(fileEntries.locator('a[download]')).toHaveCount(20);
  await expect(fileEntries.getByRole('button', { name: 'Use for next edit' })).toHaveCount(19);
  expect(
    await fileEntries.evaluateAll((nodes) => nodes.every((node) => !node.closest('details'))),
  ).toBe(true);
  for (const index of [0, 10, 18]) {
    const entry = fileEntries.nth(index);
    await expect(entry.getByRole('link')).toContainText(`illustration-${index}.png`);
    await expect(entry.getByRole('link')).toContainText('Download');
    await expect(entry.getByRole('link')).toHaveAttribute(
      'href',
      `/api/artifacts/h004-file-${index}/download`,
    );
    await expect(entry.getByRole('button', { name: 'Use for next edit' })).toBeEnabled();
  }
  await expect(
    reply.getByRole('link', { name: 'Download all ZIP from this reply', exact: true }),
  ).toBeInViewport();
  await final.getByRole('img', { name: 'First illustration' }).scrollIntoViewIfNeeded();
  await expect(final.getByRole('img', { name: 'First illustration' })).toHaveJSProperty(
    'naturalWidth',
    1920,
  );
  await expect(final.getByRole('img', { name: 'Second illustration' })).toHaveAttribute(
    'src',
    '/api/files/h004-file-1/preview',
  );
  await expect(final).not.toContainText('placement in the original answer');
  expect(
    await reply
      .locator('.reply-gallery img')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('src'))),
  ).toEqual(Array.from({ length: 9 }, (_, index) => `/api/files/h004-file-${index + 10}/preview`));
  const positions = await final.evaluate((node) =>
    Array.from(node.querySelectorAll('.markdown > p')).map((p) => ({
      text: p.textContent,
      image: !!p.querySelector('img'),
    })),
  );
  expect(positions.slice(0, 4).map((p) => p.image)).toEqual([false, true, false, true]);
  await expect(final.getByRole('link', { name: 'Download first original' })).toHaveAttribute(
    'download',
    '',
  );
  const topZip = reply.getByRole('link', { name: 'Download all ZIP', exact: true });
  await topZip.scrollIntoViewIfNeeded();
  await expect(topZip).toBeInViewport();
  await mkdir(evidence, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 1600 });
  await topZip.evaluate((node) => node.scrollIntoView({ block: 'start' }));
  await expect(final.getByRole('img', { name: 'Second illustration' })).toHaveJSProperty(
    'naturalWidth',
    1920,
  );
  await page.screenshot({ path: resolve(evidence, 'h004-final-inline-desktop.png') });
  await page.setViewportSize({ width: 1440, height: 1000 });
  const firstColumn = await final.locator('th').first().boundingBox();
  expect(firstColumn!.width).toBeGreaterThanOrEqual(175);
  await final.getByRole('region', { name: 'Scrollable table' }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(evidence, 'h004-table-desktop.png') });
  const bottomZip = reply.getByRole('link', {
    name: 'Download all ZIP from this reply',
    exact: true,
  });
  await bottomZip.scrollIntoViewIfNeeded();
  await expect(bottomZip).toBeInViewport();
  await page.screenshot({ path: resolve(evidence, 'h004-files-footer-desktop.png') });
  await additional.evaluate((node) => node.scrollIntoView({ block: 'start' }));
  await page.screenshot({
    path: resolve(evidence, 'h004-additional-previews-collapsed-desktop.png'),
  });
  await additional.locator('summary').click();
  await expect(additional).toHaveAttribute('open', '');
  await expect(additional.locator('img').first()).toBeVisible();
  await expect(additional.locator('img').first()).toHaveJSProperty('naturalWidth', 1920);
  await additional.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: resolve(evidence, 'h004-additional-previews-expanded-desktop.png'),
  });
  await additional.locator('summary').click();
  await expect(additional.locator('img').first()).not.toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await bottomZip.click();
  const download = await downloadPromise;
  const files = zipEntries(await readFile((await download.path())!));
  expect(files.size).toBe(22);
  expect(files.get('upload-one.txt')?.toString()).toBe('FIXTURE upload-one.txt');
  expect(files.get('report.txt')?.toString()).toBe('FIXTURE report.txt');
  expect(files.get('illustration-0.png')?.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
  expect([...files.keys()].some((name) => name.includes('/') || name.includes('..'))).toBe(false);
  const userZip = page
    .getByRole('article', { name: 'You message' })
    .getByRole('link', { name: 'Download all ZIP', exact: true });
  const userDownloadPromise = page.waitForEvent('download');
  await userZip.click();
  const userDownload = await userDownloadPromise;
  const uploads = zipEntries(await readFile((await userDownload.path())!));
  expect([...uploads.keys()]).toEqual(['upload-one.txt', 'upload-two.txt']);
  expect(
    (
      await request.get('/api/sessions/fixture%2Fchat-b/runs/fixture%2Finitial-run/files.zip')
    ).status(),
  ).toBe(404);
  expect(
    (
      await request.get(
        '/api/sessions/fixture%2Fchat-a/runs/fixture%2Finitial-run/files.zip?file=outside',
      )
    ).status(),
  ).toBe(400);
  await fileEntries.nth(10).getByRole('button', { name: 'Use for next edit' }).click();
  await expect(page.getByRole('list', { name: 'Image edit references' })).toContainText(
    'illustration-10.png',
  );
  await expect(additional).not.toHaveAttribute('open', '');
  await page.getByRole('button', { name: 'Remove image reference illustration-10.png' }).click();
  await additional.locator('summary').click();
  await expect(additional).toHaveAttribute('open', '');
  await page.reload();
  await expect(final.locator('img')).toHaveCount(10);
  await expect(additional).not.toHaveAttribute('open', '');
  await expect(additional.locator('img')).toHaveCount(9);
  expect(errors).toEqual([]);
  expect(remote).toEqual([]);
  await writeFile(
    resolve(evidence, 'h004-browser-summary.json'),
    JSON.stringify(
      {
        fixture: true,
        liveInference: false,
        inlineImages: 10,
        additionalImages: 9,
        additionalPreviewsCollapsedByDefault: true,
        downloadableOutputFiles: 20,
        editControlsOutsideDisclosure: 19,
        combinedZipEntries: [...files.keys()],
        uploadZipEntries: [...uploads.keys()],
        firstColumnWidth: firstColumn!.width,
        errors,
        remoteRequests: remote,
      },
      null,
      2,
    ),
  );
});
test('H004 preview disclosure and ownership survive artifact refresh and streamed placements', async ({
  page,
  request,
}) => {
  await page.goto('/');
  await expect(page.locator('.connection')).toContainText('Connected');
  const reply = page.locator('[data-run-id="fixture/initial-run"]'),
    final = reply.getByLabel('Final answer'),
    additional = reply.locator('.additional-image-previews');
  const history = await (
    await request.get(`/api/sessions/${encodeURIComponent(sessionId)}`)
  ).json();
  const message = history.messages.find((item: { id: string }) => item.id === 'h004-final');
  const artifact = history.artifacts.find((item: { id: string }) => item.id === 'h004-file-10');
  await additional.locator('summary').click();
  await expect(additional).toHaveAttribute('open', '');
  await request.post('/__fixture/event', {
    data: {
      sessionId,
      type: 'artifact',
      runId: 'fixture/initial-run',
      data: { artifact: { ...artifact, size: artifact.size + 1 } },
    },
  });
  await expect(final.locator('img')).toHaveCount(10);
  await expect(additional.locator('img')).toHaveCount(9);
  await expect(additional).toHaveAttribute('open', '');
  await request.post('/__fixture/event', {
    data: {
      sessionId,
      type: 'assistant_delta',
      runId: 'fixture/initial-run',
      data: {
        messageId: message.id,
        phase: 'final',
        text: '\n\n![Streamed selection](/api/files/h004-file-10/pre',
      },
    },
  });
  await expect(final).toContainText('Streamed selection');
  await expect(final.locator('img')).toHaveCount(10);
  await expect(additional.locator('img')).toHaveCount(9);
  await request.post('/__fixture/event', {
    data: {
      sessionId,
      type: 'assistant_delta',
      runId: 'fixture/initial-run',
      data: { messageId: message.id, phase: 'final', text: 'view)' },
    },
  });
  await expect(final.getByRole('img', { name: 'Streamed selection' })).toHaveAttribute(
    'src',
    '/api/files/h004-file-10/preview',
  );
  await expect(final.locator('img')).toHaveCount(11);
  await expect(additional.locator('img')).toHaveCount(8);
  await expect(additional.locator('img[src="/api/files/h004-file-10/preview"]')).toHaveCount(0);
  await expect(additional).toHaveAttribute('open', '');
  await additional.locator('summary').click();
  await request.post('/__fixture/event', {
    data: {
      sessionId,
      type: 'message',
      runId: 'fixture/initial-run',
      data: { message },
    },
  });
  await expect(final.locator('img')).toHaveCount(10);
  await expect(additional.locator('img')).toHaveCount(9);
  await expect(additional).not.toHaveAttribute('open', '');
  await expect(reply.locator('.artifact-entry')).toHaveCount(20);
  await expect(
    reply.getByRole('link', { name: 'Download all ZIP from this reply', exact: true }),
  ).toBeVisible();
  const calls = (await (await request.get('/__fixture/calls')).json()).calls;
  expect(
    calls.some((call: { action: string }) => ['send', 'image-decision'].includes(call.action)),
  ).toBe(false);
});
test('H004 narrow table and historical fallback remain usable without model calls', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.evaluate(() => {
    const label = document.createElement('div');
    label.textContent = 'H004 FIXTURE · NO MODEL CALLS';
    label.style.cssText =
      'position:fixed;top:0;right:0;padding:4px 8px;background:#29483b;color:white;font:10px monospace;z-index:100';
    document.body.append(label);
  });
  const final = page.getByLabel('Final answer'),
    table = final.getByRole('region', { name: 'Scrollable table' });
  await expect(page.locator('.connection')).toContainText('Connected');
  await expect(table).toBeVisible();
  await table.scrollIntoViewIfNeeded();
  expect(await table.evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);
  expect((await final.locator('th').first().boundingBox())!.width).toBeGreaterThanOrEqual(150);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await table.evaluate((node) => {
    node.scrollLeft = 170;
  });
  expect(await table.evaluate((node) => node.scrollLeft)).toBeGreaterThan(0);
  await table.evaluate((node) => {
    node.scrollLeft = 0;
  });
  await mkdir(evidence, { recursive: true });
  await page.screenshot({ path: resolve(evidence, 'h004-table-narrow.png') });
  await request.post('/__fixture/event', {
    data: {
      sessionId,
      type: 'message',
      runId: 'fixture/initial-run',
      data: {
        message: {
          id: 'h004-final',
          role: 'assistant',
          phase: 'final',
          streamState: 'completed',
          createdAt: '2026-09-22T10:24:00.000Z',
          runId: 'fixture/initial-run',
          content: 'Historical fixture answer omitted image references.',
        },
      },
    },
  });
  await expect(final).toContainText('Their placement in the original answer was not specified.');
  await expect(final.locator('img')).toHaveCount(19);
  const reply = page.locator('[data-run-id="fixture/initial-run"]');
  await expect(reply.locator('.reply-gallery img')).toHaveCount(0);
  await expect(reply.locator('.additional-image-previews')).toHaveCount(0);
  await expect(reply.locator('.artifact-entry a[download]')).toHaveCount(20);
  await expect(reply.getByRole('button', { name: 'Use for next edit' })).toHaveCount(19);
  await expect(reply.getByRole('link', { name: 'Download all ZIP', exact: true })).toBeVisible();
  await expect(
    reply.getByRole('link', { name: 'Download all ZIP from this reply', exact: true }),
  ).toBeVisible();
  await final.locator('img').first().scrollIntoViewIfNeeded();
  await expect(final.locator('img').first()).toHaveJSProperty('naturalWidth', 1920);
  await page.screenshot({ path: resolve(evidence, 'h004-historical-fallback-narrow.png') });
  const calls = (await (await request.get('/__fixture/calls')).json()).calls;
  expect(
    calls.some((call: { action: string }) => ['send', 'image-decision'].includes(call.action)),
  ).toBe(false);
});
