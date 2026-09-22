import { waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { HarnessStore, pendingRunIds } from '../src/store';
import type { RunSnapshot } from '../src/types';
import { createdAt, deferred, event, fixtureTransport, snapshot } from './fixtures';
const run = (id: string, status: RunSnapshot['status']): RunSnapshot => ({
  id,
  status,
  kind: 'message',
  createdAt,
  updatedAt: createdAt,
  artifactIds: [],
  subagents: { known: false, active: null, completed: null, failed: null, cancelled: null },
});
async function ready(runs: RunSnapshot[] = []) {
  const fixture = fixtureTransport();
  const snap = { ...snapshot(), runs };
  fixture.transport.snapshot.mockImplementation(async () => snap);
  const store = new HarnessStore(fixture.transport);
  await store.start();
  await waitFor(() => expect(fixture.streams).toHaveLength(1));
  return { ...fixture, store, snap };
}
describe('queued followups', () => {
  it('tracks multiple accepted turns; completing current run does not clear queued runs', async () => {
    const { store, transport, streams } = await ready([run('first', 'running')]);
    transport.send
      .mockResolvedValueOnce({ runId: 'second' })
      .mockResolvedValueOnce({ runId: 'third' });
    await store.send('chat/a', 'Next task');
    await store.send('chat/a', 'Then this task');
    expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual(['second', 'third', 'first']);
    const stream = streams[0].callbacks;
    stream.event(event(1, 'run', { run: run('second', 'queued') }));
    stream.event(event(2, 'run', { run: run('third', 'queued') }));
    stream.event(event(3, 'run', { run: run('first', 'completed') }));
    stream.event(event(4, 'done', { runId: 'first' }));
    expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual(['second', 'third']);
    store.dispose();
  });
  it('restores queued/running state from snapshot and clears all only through terminal run updates', async () => {
    const { store, streams } = await ready([run('first', 'running'), run('second', 'queued')]);
    expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual(['first', 'second']);
    streams[0].callbacks.event(event(1, 'state', { status: 'cancelling' }));
    streams[0].callbacks.event(event(2, 'run', { run: run('second', 'cancelled') }));
    expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual(['first']);
    streams[0].callbacks.event(event(3, 'run', { run: run('first', 'cancelled') }));
    streams[0].callbacks.event(event(4, 'state', { status: 'interrupted' }));
    expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual([]);
    store.dispose();
  });
  it('does not resurrect an accepted turn when terminal run SSE beats HTTP acknowledgement', async () => {
    const { store, transport, streams } = await ready();
    const ack = deferred<{ runId: string }>();
    transport.send.mockReturnValueOnce(ack.promise);
    const sending = store.send('chat/a', 'Fast task');
    streams[0].callbacks.event(event(1, 'run', { run: run('fast', 'completed') }));
    ack.resolve({ runId: 'fast' });
    await sending;
    expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual([]);
    store.dispose();
  });
  it('late response for another session stays associated with that session', async () => {
    const { store, transport } = await ready();
    const ack = deferred<{ runId: string }>();
    transport.send.mockReturnValueOnce(ack.promise);
    const sending = store.send('chat/a', 'Task');
    store.select('chat/b');
    ack.resolve({ runId: 'first' });
    await sending;
    expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual(['first']);
    expect(pendingRunIds(store.getSnapshot(), 'chat/b')).toEqual([]);
    store.dispose();
  });
});

it('hydrates completed IDs from an old snapshot after navigating away during completion', async () => {
  const { store, transport, snap } = await ready();
  transport.send.mockResolvedValueOnce({ runId: 'legacy-run' });
  await store.send('chat/a', 'Old server task');
  expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual(['legacy-run']);
  transport.snapshot.mockImplementation(async (id) => (id === 'chat/a' ? snap : snapshot(id)));
  store.select('chat/b');
  await waitFor(() => expect(store.getSnapshot().thread?.session.id).toBe('chat/b'));
  snap.events = [event(1, 'done', { runId: 'legacy-run' })];
  store.select('chat/a');
  await waitFor(() => expect(store.getSnapshot().thread?.session.id).toBe('chat/a'));
  expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual([]);
  store.dispose();
});
