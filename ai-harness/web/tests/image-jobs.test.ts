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
const capabilities = {
  operations: {
    generation: { available: true, profiles: [{ referenceCount: 0, sizes: ['1920x1080'] }] },
    edit: { available: true, profiles: [{ referenceCount: 1, sizes: ['1024x1024'] }] },
  },
};

describe('image lifecycle and reference boundaries', () => {
  it('discovers exact reference-count edit profiles and fails closed for absent, disabled and malformed records', () => {
    expect(editAvailable(imageCapabilities(capabilities), 1)).toBe(true);
    expect(editAvailable(imageCapabilities(capabilities), 2)).toBe(false);
    expect(
      editAvailable(
        imageCapabilities({ operations: { generation: capabilities.operations.generation } }),
      ),
    ).toBe(false);
    expect(
      editAvailable(
        imageCapabilities({
          operations: { edit: { ...capabilities.operations.edit, available: false } },
        }),
      ),
    ).toBe(false);
    expect(
      editAvailable(
        imageCapabilities({
          operations: {
            edit: { available: true, profiles: [{ referenceCount: 1, sizes: [null, 'unknown'] }] },
          },
        }),
      ),
    ).toBe(false);
  });

  it('retains cancellation intent and terminal state across stale GETs, rejects foreign jobs and reports real elapsed time', () => {
    const cancelled = job({
      state: 'cancelled',
      cancelRequested: true,
      finishedAt: '2026-09-22T12:01:00.000Z',
    });
    expect(
      mergeImageJobs(
        [cancelled],
        [job({ state: 'queued' }), job({ id: 'foreign', sessionId: 'other' })],
        'chat/a',
      ),
    ).toEqual([cancelled]);
    const stale = job({
      state: 'failed',
      finishedAt: '2026-09-22T12:00:59.000Z',
      artifactId: 'late-output',
    });
    expect(mergeImageJobs([cancelled], [stale], 'chat/a')[0]).toMatchObject({
      state: 'cancelled',
      artifactId: 'late-output',
      cancelRequested: true,
    });
    expect(
      mergeImageJobs(
        [{ ...cancelled, artifactId: 'late-output', actualSize: '1024x1024' }],
        [cancelled],
        'chat/a',
      )[0],
    ).toMatchObject({ artifactId: 'late-output', actualSize: '1024x1024', state: 'cancelled' });
    expect(
      imageElapsed(job({ state: 'running', elapsedMs: 1 }), Date.parse(createdAt) + 65000),
    ).toBe('1m 5s');
    expect(imageElapsed(cancelled, Date.parse(createdAt) + 9999999)).toBe('1m 0s');
  });

  it('honors ordered SSE requeue after known non-admission while rejecting stale GET state regressions', () => {
    const running = job({ state: 'running' });
    const thread = reconcileSnapshot({ ...snapshot(), imageJobs: [running] });
    const requeued = job({ state: 'queued', queuePosition: 2 });
    const update = event(1, 'image_job', { job: requeued });
    expect(applyEvent(thread, update).imageJobs?.[0]).toMatchObject({
      state: 'queued',
      queuePosition: 2,
    });
    expect(
      reconcileSnapshot({
        ...snapshot(),
        events: [event(1, 'image_job', { job: running }), event(2, 'image_job', { job: requeued })],
      }).imageJobs?.[0].state,
    ).toBe('queued');
    expect(mergeImageJobs([running], [requeued], 'chat/a')[0].state).toBe('running');
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
    fixture.streams[0].callbacks.event(event(1, 'image_job', { job: job({ state: 'running' }) }));
    read.resolve({ jobs: [job({ state: 'queued' })] });
    await waitFor(() => expect(fixture.transport.imageJobs).toHaveBeenCalledTimes(2));
    await Promise.resolve();
    expect(store.getSnapshot().thread?.imageJobs?.[0].state).toBe('running');
    store.dispose();
    expect(fixture.transport.cancelImage).not.toHaveBeenCalled();
    expect(fixture.transport.cancel).not.toHaveBeenCalled();
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
    fixture.streams[0].callbacks.event(event(1, 'image_job', { job: job({ state: 'running' }) }));
    fixture.transport.snapshot.mockResolvedValueOnce({
      ...snapshot(),
      messages: [{ id: 'text', role: 'assistant', content: 'Existing conversation', createdAt }],
      events: [event(2, 'image_job', { job: job({ state: 'queued', queuePosition: 1 }) })],
    });
    fixture.transport.imageJobs.mockRejectedValueOnce(new Error('Still offline'));
    fixture.transport.imageCapabilities.mockResolvedValue({ operations: {} });
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
    const onlyTwo = {
      operations: {
        edit: { available: true, profiles: [{ referenceCount: 2, sizes: ['1024x1024'] }] },
      },
    };
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

  it('sends browser approval decisions without dimensions, references or a model approval flag', async () => {
    const fetcher = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(
        async () => new Response(JSON.stringify({ job: job({ state: 'queued' }) })),
      );
    await api.approveImage('chat/a', 'image/one', 'approve');
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify(job({ state: 'cancelled' }))));
    await expect(api.approveImage('chat/a', 'image/one', 'reject')).resolves.toEqual({
      job: job({ state: 'cancelled' }),
    });
    expect(
      fetcher.mock.calls.map(([path, options]) => [
        path,
        options?.method,
        JSON.parse(options?.body as string),
      ]),
    ).toEqual([
      ['/api/sessions/chat%2Fa/image-jobs/image%2Fone/approval', 'POST', { decision: 'approve' }],
      ['/api/sessions/chat%2Fa/image-jobs/image%2Fone/approval', 'POST', { decision: 'reject' }],
    ]);
  });
});
