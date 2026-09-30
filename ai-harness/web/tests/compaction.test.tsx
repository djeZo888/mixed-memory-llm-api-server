import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { api, ApiError } from '../src/api';
import { HarnessStore, pendingRunIds } from '../src/store';
import { createdAt, deferred, event, fixtureTransport, snapshot } from './fixtures';
import { replyRun } from './reply-fixtures';

function codexFixture() {
  const fixture = fixtureTransport();
  const snap = snapshot();
  snap.session.engineKind = 'codex';
  snap.messages = [
    {
      id: 'retained-message',
      role: 'user',
      content: 'Remember the original constraint',
      createdAt,
    },
  ];
  fixture.transport.snapshot.mockImplementation(async () => snap);
  fixture.transport.health.mockResolvedValue({
    visionAvailable: false,
    engines: { codex: { available: true } },
  });
  return { ...fixture, snap, store: new HarnessStore(fixture.transport) };
}

describe('owned manual compaction', () => {
  beforeEach(() => sessionStorage.clear());
  it('sends only the stable action ID to the session-owned endpoint', async () => {
    const fetcher = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ runId: 'compact-run' })));
    await expect(api.compact('chat/a', 'action-1')).resolves.toEqual({ runId: 'compact-run' });
    expect(fetcher).toHaveBeenCalledOnce();
    const [url, options] = fetcher.mock.calls[0];
    expect(url).toBe('/api/sessions/chat%2Fa/compact');
    expect(options?.method).toBe('POST');
    expect(options?.body).toBe('{"actionId":"action-1"}');
  });

  it('shows the action for Codex history, keeps it pending until completion, and preserves visible history', async () => {
    const { transport, store, streams, snap } = codexFixture();
    const ack = deferred<{ runId: string }>();
    transport.compact.mockReturnValueOnce(ack.promise);
    render(<App store={store} />);
    const button = await screen.findByRole('button', { name: 'Compact context' });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(transport.compact).toHaveBeenCalledOnce();
    expect(transport.compact.mock.calls[0]).toEqual([
      'chat/a',
      expect.stringMatching(/^[0-9a-f-]{36}$/),
    ]);
    expect(button).toBeDisabled();
    await userEvent.click(button);
    expect(transport.compact).toHaveBeenCalledOnce();
    await act(async () => {
      ack.resolve({ runId: 'compact/1' });
      await ack.promise;
    });
    expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual(['compact/1']);
    expect(screen.getByText('Remember the original constraint')).toBeInTheDocument();
    const retained = [...snap.messages];
    act(() => {
      streams[0].callbacks.event(event(1, 'state', { status: 'compacting' }));
      streams[0].callbacks.event(
        event(2, 'run', { run: replyRun('compact/1', { kind: 'compact', status: 'completed' }) }),
      );
      streams[0].callbacks.event(event(3, 'state', { status: 'idle' }));
      streams[0].callbacks.event(event(4, 'done', { runId: 'compact/1' }));
    });
    await waitFor(() => expect(button).toBeEnabled());
    expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual([]);
    expect(store.getSnapshot().thread?.messages).toEqual(retained);
    expect(transport.send).not.toHaveBeenCalled();
    expect(transport.create).not.toHaveBeenCalled();
  });

  it('does not resurrect pending compaction when completion precedes its HTTP acknowledgement', async () => {
    const { transport, store, streams } = codexFixture();
    await store.start();
    await waitFor(() => expect(streams).toHaveLength(1));
    const ack = deferred<{ runId: string }>();
    transport.compact.mockReturnValueOnce(ack.promise);
    const pending = store.compact('chat/a');
    streams[0].callbacks.event(
      event(1, 'run', { run: replyRun('compact/1', { kind: 'compact', status: 'completed' }) }),
    );
    ack.resolve({ runId: 'compact/1' });
    await pending;
    expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual([]);
    store.dispose();
  });

  it('surfaces request failure once and retains the prior messages', async () => {
    const { transport, store } = codexFixture();
    transport.compact.mockRejectedValue(
      new ApiError(409, 'compaction_empty', 'Context compaction unavailable'),
    );
    render(<App store={store} />);
    const button = await screen.findByRole('button', { name: 'Compact context' });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await screen.findByText('Context compaction unavailable')).toBeInTheDocument();
    expect(screen.getByText('Remember the original constraint')).toBeInTheDocument();
    expect(transport.compact).toHaveBeenCalledOnce();
    expect(transport.send).not.toHaveBeenCalled();
    expect(sessionStorage.getItem('ai-harness:compaction:chat/a')).toBeNull();
  });

  it('reuses a lost-ack action across refresh, then allows a distinct action after confirmed completion', async () => {
    const first = codexFixture();
    await first.store.start();
    await waitFor(() => expect(first.streams).toHaveLength(1));
    first.transport.compact.mockRejectedValueOnce(new TypeError('Network connection lost'));
    await first.store.compact('chat/a');
    const actionId = first.transport.compact.mock.calls[0][1];
    expect(first.store.getSnapshot().error).toContain('outcome is unconfirmed');
    expect(JSON.parse(sessionStorage.getItem('ai-harness:compaction:chat/a')!).actionId).toBe(actionId);
    first.store.dispose();

    const refreshed = codexFixture();
    refreshed.snap.runs = [replyRun('accepted-before-disconnect', { kind: 'compact', status: 'completed' })];
    refreshed.transport.compact.mockResolvedValueOnce({ runId: 'accepted-before-disconnect' });
    await refreshed.store.start();
    await waitFor(() => expect(refreshed.streams).toHaveLength(1));
    await refreshed.store.compact('chat/a');
    expect(refreshed.transport.compact).toHaveBeenNthCalledWith(1, 'chat/a', actionId);
    expect(sessionStorage.getItem('ai-harness:compaction:chat/a')).toBeNull();
    expect(pendingRunIds(refreshed.store.getSnapshot(), 'chat/a')).toEqual([]);
    await refreshed.store.compact('chat/a');
    expect(refreshed.transport.compact.mock.calls[1][1]).not.toBe(actionId);
    refreshed.store.dispose();
  });

  it.each([408, 503])('retains the same unresolved action after HTTP %s', async (status) => {
    const { transport, store, streams } = codexFixture();
    await store.start();
    await waitFor(() => expect(streams).toHaveLength(1));
    transport.compact.mockRejectedValueOnce(new ApiError(status, 'timeout', 'Uncertain request'));
    await store.compact('chat/a');
    const actionId = transport.compact.mock.calls[0][1];
    await store.compact('chat/a');
    expect(transport.compact).toHaveBeenNthCalledWith(2, 'chat/a', actionId);
    store.dispose();
  });

  it.each([401, 409, 429])('retains a lost-ack action when its retry receives HTTP %s', async (status) => {
    const { transport, store, streams } = codexFixture();
    await store.start();
    await waitFor(() => expect(streams).toHaveLength(1));
    transport.compact
      .mockRejectedValueOnce(new TypeError('Acknowledgement lost'))
      .mockRejectedValueOnce(new ApiError(status, 'retry_rejected', 'Retry rejected'))
      .mockResolvedValueOnce({ runId: 'original-action-run' });
    await store.compact('chat/a');
    const actionId = transport.compact.mock.calls[0][1];
    await store.compact('chat/a');
    expect(store.getSnapshot().error).toBe('Retry rejected');
    expect(JSON.parse(sessionStorage.getItem('ai-harness:compaction:chat/a')!).actionId).toBe(actionId);
    await store.compact('chat/a');
    expect(transport.compact.mock.calls).toEqual([
      ['chat/a', actionId],
      ['chat/a', actionId],
      ['chat/a', actionId],
    ]);
    expect(pendingRunIds(store.getSnapshot(), 'chat/a')).toEqual(['original-action-run']);
    store.dispose();
  });

  it('does not offer native compaction on MiniMax or enable it on an empty Codex chat', async () => {
    const mini = fixtureTransport();
    const first = render(<App store={new HarnessStore(mini.transport)} />);
    await screen.findByRole('button', { name: /Continue in new chat/ });
    expect(screen.queryByRole('button', { name: 'Compact context' })).not.toBeInTheDocument();
    first.unmount();
    const { store, snap } = codexFixture();
    snap.messages = [];
    render(<App store={store} />);
    expect(await screen.findByRole('button', { name: 'Compact context' })).toBeDisabled();
  });
});
