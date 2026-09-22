import { describe, expect, it } from 'vitest';
import { waitFor } from '@testing-library/react';
import { HarnessStore } from '../src/store';
import { ApiError } from '../src/api';
import { deferred, event, fixtureTransport, snapshot } from './fixtures';
import type { Snapshot } from '../src/types';
async function ready() {
  const fixture = fixtureTransport();
  const store = new HarnessStore(fixture.transport);
  await store.start();
  await waitFor(() => expect(fixture.streams.length).toBe(1));
  return { ...fixture, store };
}
describe('real store callback flows', () => {
  it('resyncs on reconnect and done while buffering newer deltas', async () => {
    const { store, transport, streams } = await ready();
    const stream = streams[0].callbacks;
    stream.event(event(1, 'assistant_delta', { messageId: 'm', text: 'Hello' }));
    const read = deferred<Snapshot>();
    transport.snapshot.mockReturnValueOnce(read.promise);
    stream.disconnected();
    expect(store.getSnapshot().connection).toBe('reconnecting');
    stream.open();
    stream.event(event(2, 'assistant_delta', { messageId: 'm', text: ' world' }));
    const snap = snapshot();
    snap.messages = [
      { id: 'm', role: 'assistant', content: 'Hello', createdAt: snap.session.createdAt },
    ];
    snap.events = [event(1, 'assistant_delta', { messageId: 'm', text: 'Hello' })];
    read.resolve(snap);
    await waitFor(() =>
      expect(store.getSnapshot().thread?.messages[0].content).toBe('Hello world'),
    );
    stream.event(event(2, 'assistant_delta', { messageId: 'm', text: ' world' }));
    expect(store.getSnapshot().thread?.messages[0].content).toBe('Hello world');
    const before = transport.snapshot.mock.calls.length;
    stream.event(event(3, 'done', { runId: 'run/1' }));
    await waitFor(() => expect(transport.snapshot.mock.calls.length).toBeGreaterThan(before));
    store.dispose();
    expect(transport.cancel).not.toHaveBeenCalled();
  });
  it('ignores late GETs, events, upload results and handoffs for a different selected chat', async () => {
    const { store, transport, streams } = await ready();
    const slow = deferred<Snapshot>();
    transport.snapshot.mockReturnValueOnce(slow.promise);
    streams[0].callbacks.open();
    const upload = deferred<Awaited<ReturnType<typeof transport.upload>>>();
    transport.upload.mockReturnValueOnce(upload.promise);
    const uploading = store.upload(
      'chat/a',
      new File(['text'], 'notes.txt', { type: 'text/plain' }),
    );
    store.select('chat/b');
    await waitFor(() => expect(store.getSnapshot().thread?.session.id).toBe('chat/b'));
    streams[0].callbacks.event(event(1, 'handoff', { newSessionId: 'wrong' }));
    slow.resolve(snapshot());
    upload.resolve({ attachment: { id: 'a', name: 'notes.txt', size: 4, mimeType: 'text/plain' } });
    await uploading;
    expect(store.getSnapshot().selectedId).toBe('chat/b');
    expect(store.getSnapshot().thread?.session.id).toBe('chat/b');
    expect(store.getSnapshot().attachments['chat/b']).toBeUndefined();
    expect(streams[0].close).toHaveBeenCalled();
    expect(transport.cancel).not.toHaveBeenCalled();
    store.dispose();
  });
  it('removes HTTP 202 deleting sessions and excludes them from stale list results', async () => {
    const { store, transport } = await ready();
    await store.remove('chat/a');
    await store.refreshList();
    expect(store.getSnapshot().sessions.map((s) => s.id)).toEqual(['chat/b']);
    expect(store.getSnapshot().selectedId).toBe('chat/b');
    expect(transport.remove).toHaveBeenCalledWith('chat/a');
    store.dispose();
  });
  it('handles a selected session disappearing with 404', async () => {
    const { store, transport } = await ready();
    transport.snapshot.mockRejectedValueOnce(new ApiError(404, 'not_found', 'Gone'));
    await store.resync();
    expect(store.getSnapshot().selectedId).toBe('chat/b');
    store.dispose();
  });
  it('guards duplicate create/send/upload/delete and carries attachment IDs', async () => {
    const { store, transport } = await ready();
    const upload = deferred<Awaited<ReturnType<typeof transport.upload>>>();
    transport.upload.mockReturnValueOnce(upload.promise);
    const file = new File(['text'], 'notes.txt', { type: 'text/plain' });
    const uploading = store.upload('chat/a', file);
    await store.upload('chat/a', file);
    expect(transport.upload).toHaveBeenCalledTimes(1);
    upload.resolve({
      attachment: { id: 'file/1', name: 'notes.txt', mimeType: 'text/plain', size: 4 },
    });
    await uploading;
    const sent = deferred<{ runId: string }>();
    transport.send.mockReturnValueOnce(sent.promise);
    const sending = store.send('chat/a', 'Read');
    await store.send('chat/a', 'Read');
    expect(transport.send).toHaveBeenCalledTimes(1);
    expect(transport.send).toHaveBeenCalledWith('chat/a', 'Read', ['file/1']);
    sent.resolve({ runId: 'run/1' });
    await sending;
    const created = deferred<Awaited<ReturnType<typeof transport.create>>>();
    transport.create.mockReturnValueOnce(created.promise);
    const creating = store.create();
    await store.create();
    expect(transport.create).toHaveBeenCalledTimes(1);
    created.resolve({ session: snapshot('new').session });
    await creating;
    const removed = deferred<{ status: 'deleting' }>();
    transport.remove.mockReturnValueOnce(removed.promise);
    const removing = store.remove('new');
    await store.remove('new');
    expect(transport.remove).toHaveBeenCalledTimes(1);
    removed.resolve({ status: 'deleting' });
    await removing;
    store.dispose();
  });
  it('does not stick submitted state when done/handoff beats its 202 response', async () => {
    const { store, transport, streams } = await ready();
    const sent = deferred<{ runId: string }>();
    transport.send.mockReturnValueOnce(sent.promise);
    const sending = store.send('chat/a', 'Read');
    streams[0].callbacks.event(event(1, 'done', { runId: 'run/1' }));
    sent.resolve({ runId: 'run/1' });
    await sending;
    expect(store.getSnapshot().submitted['chat/a']).toBeUndefined();
    const handed = deferred<{ runId: string }>();
    transport.handoff.mockReturnValueOnce(handed.promise);
    const handing = store.handoff('chat/a');
    streams[0].callbacks.event(event(2, 'handoff', { newSessionId: 'new' }));
    handed.resolve({ runId: 'handoff/1' });
    await handing;
    expect(store.getSnapshot().selectedId).toBe('new');
    expect(store.getSnapshot().submitted['chat/a']).toBeUndefined();
    expect(store.getSnapshot().sessions.some((s) => s.id === 'chat/a')).toBe(true);
    store.dispose();
  });
  it('restores a subscription after dispose/start with the same store', async () => {
    const { store, streams, transport } = await ready();
    store.dispose();
    await store.start();
    await waitFor(() => expect(streams.length).toBe(2));
    streams[1].callbacks.event(event(1, 'state', { status: 'running' }));
    expect(store.getSnapshot().thread?.session.status).toBe('running');
    expect(transport.cancel).not.toHaveBeenCalled();
    store.dispose();
  });
  it('rejects unsupported images without uploading; enables them only from health', async () => {
    const { store, transport } = await ready();
    await store.upload('chat/a', new File(['image'], 'photo.png', { type: 'image/png' }));
    expect(transport.upload).not.toHaveBeenCalled();
    expect(store.getSnapshot().error).toMatch(/Image uploads are unavailable/);
    store.dispose();
    transport.health.mockResolvedValue({ visionAvailable: true });
    const enabled = new HarnessStore(transport);
    await enabled.start();
    await enabled.upload('chat/a', new File(['image'], 'photo.png', { type: 'image/png' }));
    expect(transport.upload).toHaveBeenCalledOnce();
    enabled.dispose();
  });
});

it('does not revert completed cancellation when its HTTP acknowledgement arrives late', async () => {
  const { store, transport, streams } = await ready();
  streams[0].callbacks.event(event(1, 'state', { status: 'running' }));
  const ack = deferred<{ status: 'cancelling' }>();
  transport.cancel.mockReturnValueOnce(ack.promise);
  const cancelling = store.cancel('chat/a');
  streams[0].callbacks.event(event(2, 'state', { status: 'interrupted' }));
  streams[0].callbacks.event(event(3, 'done', { runId: 'run/1' }));
  ack.resolve({ status: 'cancelling' });
  await cancelling;
  expect(store.getSnapshot().thread?.session.status).toBe('interrupted');
  store.dispose();
});

it('honors a previously unseen handoff when reconnect GET wins the SSE replay race', async () => {
  const { store, transport, streams } = await ready();
  const snap = snapshot();
  snap.events = [event(1, 'handoff', { newSessionId: 'continued' })];
  transport.snapshot.mockResolvedValueOnce(snap);
  streams[0].callbacks.disconnected();
  streams[0].callbacks.open();
  await waitFor(() => expect(store.getSnapshot().selectedId).toBe('continued'));
  streams[0].callbacks.event(snap.events[0]); // late replay from the old chat
  expect(store.getSnapshot().selectedId).toBe('continued');
  expect(store.getSnapshot().sessions.some((s) => s.id === 'chat/a')).toBe(true);
  store.dispose();
});

it('ignores an old initial snapshot after switching chats and an older reconnect snapshot', async () => {
  const fixture = fixtureTransport();
  const delayed = deferred<Snapshot>();
  fixture.transport.snapshot.mockReturnValueOnce(delayed.promise);
  const store = new HarnessStore(fixture.transport);
  await store.start();
  store.select('chat/b');
  await waitFor(() => expect(store.getSnapshot().thread?.session.id).toBe('chat/b'));
  delayed.resolve(snapshot());
  await Promise.resolve();
  expect(store.getSnapshot().thread?.session.id).toBe('chat/b');
  fixture.streams[0].callbacks.event(
    event(5, 'assistant_delta', { messageId: 'm', text: 'Current answer' }, 'chat/b'),
  );
  await store.resync();
  expect(store.getSnapshot().thread?.messages[0].content).toBe('Current answer');
  expect(store.getSnapshot().thread?.lastEventId).toBe(5);
  store.dispose();
});
