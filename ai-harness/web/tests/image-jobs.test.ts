import { describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/react';
import { api } from '../src/api';
import { HarnessStore } from '../src/store';
import { imageCapabilities, editAvailable } from '../src/image-capabilities';
import { imageElapsed, mergeImageJobs } from '../src/image-jobs';
import { groupReplies } from '../src/reply-groups';
import { applyEvent, reconcileSnapshot } from '../src/state';
import type { ImageJob } from '../src/types';
import { createdAt, deferred, event, fixtureTransport, snapshot } from './fixtures';

const job = (patch: Partial<ImageJob> = {}): ImageJob => ({
  id: 'image/one',
  revision: 1,
  sessionId: 'chat/a',
  runId: 'run/image',
  requestId: 'request/one',
  operation: 'edit',
  state: 'awaiting_approval',
  model: 'Qwen-Image-2.1',
  prompt: 'Recolour the teapot',
  seed: 42,
  requestedSize: '1024x1024',
  references: [],
  createdAt,
  cancelRequested: false,
  ...patch,
});
const profile = (operation = 'edit', references = 1, size = '1024x1024') => ({
  operation,
  references,
  size,
  transparent: false,
  evidence_sha256: 'a'.repeat(64),
  native_size: size,
  crop_bottom: 0,
});
const capabilities = {
  ready: true,
  admitting: true,
  busy: false,
  state: 'ready',
  model: 'Qwen-Image-2.1',
  profiles: [profile('generation', 0, '1920x1080'), profile()],
  defaults: { size: '1024x1024' },
  output_format: 'png',
};

describe('image lifecycle and reference boundaries', () => {
  it('discovers exact upstream operation/reference profiles and fails closed for absent, transparent and malformed records', () => {
    expect(editAvailable(imageCapabilities(capabilities), 1)).toBe(true);
    expect(editAvailable(imageCapabilities(capabilities), 2)).toBe(false);
    expect(
      editAvailable(imageCapabilities({ ...capabilities, profiles: [profile('generation', 0)] })),
    ).toBe(false);
    expect(
      editAvailable(
        imageCapabilities({ ...capabilities, profiles: [{ ...profile(), transparent: true }] }),
      ),
    ).toBe(false);
    expect(
      editAvailable(
        imageCapabilities({
          ...capabilities,
          profiles: [
            { ...profile(), size: 'unknown' },
            { ...profile(), references: 1.5 },
          ],
        }),
      ),
    ).toBe(false);
    expect(
      editAvailable(
        imageCapabilities({
          operations: {
            edit: { available: true, profiles: [{ referenceCount: 1, sizes: ['1024x1024'] }] },
          },
        }),
      ),
    ).toBe(false);
  });

  it('uses revisions to preserve terminal state and late artifacts across stale GETs, rejects foreign/malformed jobs, and reports real elapsed time', () => {
    const cancelled = job({
      revision: 5,
      state: 'cancelled',
      cancelRequested: true,
      finishedAt: '2026-09-22T12:01:00.000Z',
    });
    expect(
      mergeImageJobs(
        [cancelled],
        [job({ revision: 4, state: 'queued' }), job({ id: 'foreign', sessionId: 'other' })],
        'chat/a',
      ),
    ).toEqual([cancelled]);
    const stale = job({ revision: 4, state: 'failed', artifactId: 'untrusted-stale-output' });
    expect(mergeImageJobs([cancelled], [stale], 'chat/a')).toEqual([cancelled]);
    const late = { ...cancelled, revision: 6, artifactId: 'late-output', actualSize: '1024x1024' };
    expect(mergeImageJobs([cancelled], [late], 'chat/a')).toEqual([late]);
    expect(mergeImageJobs([late], [cancelled], 'chat/a')).toEqual([late]);
    expect(mergeImageJobs([], [job({ revision: 0 }), job({ revision: 1.5 })], 'chat/a')).toEqual(
      [],
    );
    expect(
      imageElapsed(job({ state: 'running', elapsedMs: 1 }), Date.parse(createdAt) + 65000),
    ).toBe('1m 5s');
    expect(imageElapsed(cancelled, Date.parse(createdAt) + 9999999)).toBe('1m 0s');
  });

  it('accepts newer running-to-queued revisions from GET/SSE and ignores older revisions even in later SSE envelopes', () => {
    const running = job({ revision: 2, state: 'running' });
    const thread = reconcileSnapshot({ ...snapshot(), imageJobs: [running] });
    const requeued = job({ revision: 3, state: 'queued', queuePosition: 2 });
    const afterQueue = applyEvent(thread, event(1, 'image_job', { job: requeued }));
    expect(afterQueue.imageJobs?.[0]).toEqual(requeued);
    expect(applyEvent(afterQueue, event(2, 'image_job', { job: running })).imageJobs?.[0]).toEqual(
      requeued,
    );
    expect(
      reconcileSnapshot({
        ...snapshot(),
        events: [event(1, 'image_job', { job: requeued }), event(2, 'image_job', { job: running })],
        imageJobs: [running],
      }).imageJobs?.[0],
    ).toEqual(requeued);
    expect(mergeImageJobs([running], [requeued], 'chat/a')[0]).toEqual(requeued);
    expect(mergeImageJobs([requeued], [{ ...requeued, state: 'running' }], 'chat/a')[0]).toEqual(
      requeued,
    );
  });

  it('rejects SSE image records whose run conflicts with the event envelope', () => {
    const thread = reconcileSnapshot(snapshot());
    const malformed = { ...event(1, 'image_job', { job: job() }), runId: 'other-run' };
    expect(applyEvent(thread, malformed)).toBe(thread);
    expect(reconcileSnapshot({ ...snapshot(), events: [malformed] }).imageJobs).toEqual([]);
  });

  it('places a post-turn job under its stored run even before assistant text or run projection arrives', () => {
    const thread = reconcileSnapshot({ ...snapshot(), imageJobs: [job()] });
    const reply = groupReplies(thread).items[0];
    expect(reply.kind).toBe('reply');
    if (reply.kind === 'reply')
      expect(reply.reply).toMatchObject({ runId: 'run/image', imageJobs: [job()] });
  });

  it('loads persisted jobs after reconnect, buffers SSE and never cancels on disposal', async () => {
    const fixture = fixtureTransport();
    fixture.transport.imageJobs.mockResolvedValue({ jobs: [job()] });
    const store = new HarnessStore(fixture.transport);
    await store.start();
    await waitFor(() => expect(fixture.streams).toHaveLength(1));
    expect(store.getSnapshot().thread?.imageJobs?.[0].state).toBe('awaiting_approval');
    expect(fixture.transport.approveImage).not.toHaveBeenCalled();
    const read = deferred<{ jobs: ImageJob[] }>();
    fixture.transport.imageJobs.mockReturnValueOnce(read.promise);
    fixture.streams[0].callbacks.disconnected();
    fixture.streams[0].callbacks.open();
    fixture.streams[0].callbacks.event(
      event(1, 'image_job', { job: job({ revision: 3, state: 'running' }) }),
    );
    read.resolve({ jobs: [job({ revision: 2, state: 'queued' })] });
    await waitFor(() => expect(fixture.transport.imageJobs).toHaveBeenCalledTimes(2));
    await Promise.resolve();
    expect(store.getSnapshot().thread?.imageJobs?.[0].state).toBe('running');
    store.dispose();
    expect(fixture.transport.cancelImage).not.toHaveBeenCalled();
    expect(fixture.transport.cancel).not.toHaveBeenCalled();
  });

  it('keeps a newer card revision when a successful reconnect GET returns an older job projection', async () => {
    const fixture = fixtureTransport();
    const newer = job({ revision: 4, state: 'queued', queuePosition: 2 });
    fixture.transport.imageJobs.mockResolvedValueOnce({ jobs: [newer] });
    const store = new HarnessStore(fixture.transport);
    await store.start();
    await waitFor(() => expect(fixture.streams).toHaveLength(1));
    fixture.transport.imageJobs.mockResolvedValueOnce({
      jobs: [job({ revision: 3, state: 'running' })],
    });
    await store.resync();
    expect(store.getSnapshot().thread?.imageJobs?.[0]).toEqual(newer);
    store.dispose();
  });

  it('preserves ordinary chat and last known jobs when the image route fails, and refreshes disabled capabilities on reconnect', async () => {
    const fixture = fixtureTransport();
    fixture.transport.imageCapabilities.mockResolvedValue(capabilities);
    fixture.transport.imageJobs.mockRejectedValueOnce(new Error('Temporarily offline'));
    fixture.transport.snapshot.mockResolvedValue({
      ...snapshot(),
      messages: [{ id: 'text', role: 'assistant', content: 'Existing conversation', createdAt }],
    });
    const store = new HarnessStore(fixture.transport);
    await store.start();
    await waitFor(() => expect(fixture.streams).toHaveLength(1));
    expect(store.getSnapshot().thread?.messages[0].content).toBe('Existing conversation');
    expect(store.getSnapshot().imageJobsError).toContain('Image status unavailable');
    fixture.streams[0].callbacks.event(
      event(1, 'image_job', { job: job({ revision: 2, state: 'running' }) }),
    );
    fixture.transport.snapshot.mockResolvedValueOnce({
      ...snapshot(),
      messages: [{ id: 'text', role: 'assistant', content: 'Existing conversation', createdAt }],
      events: [
        event(2, 'image_job', { job: job({ revision: 3, state: 'queued', queuePosition: 1 }) }),
      ],
    });
    fixture.transport.imageJobs.mockRejectedValueOnce(new Error('Still offline'));
    fixture.transport.imageCapabilities.mockResolvedValue({ ...capabilities, profiles: [] });
    fixture.streams[0].callbacks.open();
    await waitFor(() => expect(editAvailable(store.getSnapshot().imageCapabilities)).toBe(false));
    await waitFor(() => expect(store.getSnapshot().thread?.imageJobs?.[0].state).toBe('queued'));
    expect(store.getSnapshot().thread?.messages[0].content).toBe('Existing conversation');
    await store.send('chat/a', 'Ordinary message still works');
    expect(fixture.transport.send).toHaveBeenCalledWith(
      'chat/a',
      'Ordinary message still works',
      [],
    );
    store.dispose();
  });

  it('keeps current-session artifact references separate from uploads and enforces the discovered count', async () => {
    const fixture = fixtureTransport();
    fixture.transport.imageCapabilities.mockResolvedValue(capabilities);
    const artifact = {
      id: 'generated',
      name: 'generated.png',
      mimeType: 'image/png',
      size: 10,
      downloadUrl: '/api/artifacts/generated/download',
    };
    fixture.transport.snapshot.mockResolvedValue({
      ...snapshot(),
      artifacts: [artifact, { ...artifact, id: 'second' }],
    });
    const store = new HarnessStore(fixture.transport);
    await store.start();
    await waitFor(() => expect(fixture.streams).toHaveLength(1));
    store.addImageReference('chat/a', 'foreign');
    store.addImageReference('chat/b', artifact.id);
    expect(store.getSnapshot().imageReferences).toEqual({});
    store.addImageReference('chat/a', artifact.id);
    store.addImageReference('chat/a', artifact.id);
    store.addImageReference('chat/a', 'second');
    expect(store.getSnapshot().imageReferences['chat/a'].map((item) => item.id)).toEqual([
      'generated',
    ]);
    await store.upload('chat/a', new File(['text'], 'notes.txt', { type: 'text/plain' }));
    await store.send('chat/a', 'Edit this image');
    expect(fixture.transport.send).toHaveBeenCalledWith(
      'chat/a',
      'Edit this image',
      ['file/1'],
      ['generated'],
    );
    expect(store.getSnapshot().imageReferences['chat/a']).toEqual([]);
    expect(store.getSnapshot().thread?.artifacts).toHaveLength(2);
    store.dispose();
  });

  it('stages references toward a qualified two-reference edit without inventing single-reference support', async () => {
    const fixture = fixtureTransport();
    const onlyTwo = { ...capabilities, profiles: [profile('edit', 2)] };
    fixture.transport.imageCapabilities.mockResolvedValue(onlyTwo);
    fixture.transport.snapshot.mockResolvedValue({
      ...snapshot(),
      artifacts: ['first', 'second', 'third'].map((id) => ({
        id,
        name: `${id}.png`,
        mimeType: 'image/png',
        size: 10,
        downloadUrl: `/api/artifacts/${id}/download`,
      })),
    });
    const store = new HarnessStore(fixture.transport);
    await store.start();
    await waitFor(() => expect(fixture.streams).toHaveLength(1));
    expect(editAvailable(store.getSnapshot().imageCapabilities, 1)).toBe(false);
    expect(editAvailable(store.getSnapshot().imageCapabilities, 2)).toBe(true);
    store.addImageReference('chat/a', 'first');
    expect(store.getSnapshot().imageReferences['chat/a'].map((item) => item.id)).toEqual(['first']);
    store.addImageReference('chat/a', 'second');
    store.addImageReference('chat/a', 'third');
    expect(store.getSnapshot().imageReferences['chat/a'].map((item) => item.id)).toEqual([
      'first',
      'second',
    ]);
    await store.send('chat/a', 'Use these sources');
    expect(fixture.transport.send).toHaveBeenCalledWith(
      'chat/a',
      'Use these sources',
      [],
      ['first', 'second'],
    );
    store.dispose();
  });

  it('fetches ephemeral approval authorization per user decision and sends only the exact token-bound body', async () => {
    const fetcher = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ approvalToken: 'fixture-token-one' })))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job: job({ revision: 2, state: 'queued' }) })),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ approvalToken: 'fixture-token-two' })))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job: job({ revision: 2, state: 'cancelled' }) })),
      );
    await api.approveImage('chat/a', 'image/one', 'approve');
    await api.approveImage('chat/a', 'image/one', 'reject');
    const base = '/api/sessions/chat%2Fa/image-jobs/image%2Fone';
    expect(
      fetcher.mock.calls.map(([path, options]) => [
        path,
        options?.method ?? 'GET',
        options?.body ? JSON.parse(options.body as string) : null,
      ]),
    ).toEqual([
      [`${base}/approval-token`, 'GET', null],
      [`${base}/approval`, 'POST', { decision: 'approve', approvalToken: 'fixture-token-one' }],
      [`${base}/approval-token`, 'GET', null],
      [`${base}/approval`, 'POST', { decision: 'reject', approvalToken: 'fixture-token-two' }],
    ]);
  });

  it('never replays a denied decision and obtains a fresh token only on an explicit retry', async () => {
    const fetcher = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ approvalToken: 'fixture-expired' })))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            error: { code: 'approval_expired', message: 'Approval expired. Try again.' },
          }),
          { status: 403 },
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ approvalToken: 'fixture-fresh' })))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job: job({ revision: 2, state: 'queued' }) })),
      );
    await expect(api.approveImage('chat/a', 'image/one', 'approve')).rejects.toThrow(
      'Approval expired',
    );
    expect(fetcher).toHaveBeenCalledTimes(2);
    await api.approveImage('chat/a', 'image/one', 'approve');
    expect(fetcher).toHaveBeenCalledTimes(4);
    expect(JSON.parse(fetcher.mock.calls[3][1]?.body as string)).toEqual({
      decision: 'approve',
      approvalToken: 'fixture-fresh',
    });
  });

  it('rejects missing authorization tokens and noncontract raw job responses', async () => {
    const fetcher = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ approvalToken: '' })));
    await expect(api.approveImage('chat/a', 'image/one', 'approve')).rejects.toThrow(
      'Approval authorization was unavailable',
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify(job())));
    await expect(api.cancelImage('chat/a', 'image/one')).rejects.toThrow('unreadable image job');
  });
});
