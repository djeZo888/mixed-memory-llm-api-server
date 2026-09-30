import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { HarnessStore } from '../src/store';
import type { RunSnapshot, Status } from '../src/types';
import { event, fixtureTransport, session, snapshot } from './fixtures';
import { replyRun, replyThread } from './reply-fixtures';

const stripLabel = (status: Status) =>
  status === 'idle'
    ? 'Ready'
    : status === 'running'
      ? 'Running · working'
      : ['queued', 'compacting', 'cancelling'].includes(status)
        ? status[0].toUpperCase() + status.slice(1)
        : status;

function expectStatus(status: Status) {
  expect(document.querySelector('.topbar .badge')).toHaveTextContent(new RegExp(`^${status}$`));
  expect(
    screen.getByRole('button', { name: new RegExp(`^Chat chat/a\\s*${status}$`) }),
  ).toHaveAttribute('aria-current', 'page');
  expect(
    screen.getByRole('status', { name: 'Run status' }).querySelector('strong'),
  ).toHaveTextContent(new RegExp(`^${stripLabel(status)}$`));
}

async function setup(status: Status, runs: RunSnapshot[]) {
  const fixture = fixtureTransport();
  fixture.transport.snapshot.mockImplementation(async (id) => ({
    ...snapshot(id),
    session: { ...session(id), status: id === 'chat/a' ? status : 'idle' },
    runs: id === 'chat/a' ? runs : [],
  }));
  const store = new HarnessStore(fixture.transport);
  render(<App store={store} />);
  await waitFor(() => expect(store.getSnapshot().thread?.session.id).toBe('chat/a'));
  await screen.findByRole('textbox', { name: 'Message' });
  return { ...fixture, store };
}

describe('consistent observed run status across the app', () => {
  it.each(['queued', 'running', 'cancelling'] as const)(
    'shows %s in header, selected sidebar and working strip when aggregate is idle',
    async (status) => {
      const { store } = await setup('idle', [replyRun('pending', { status })]);
      expectStatus(status);
      expect(screen.getByRole('status', { name: 'Run status' })).toHaveClass('is-working');
      // Rendering must not rewrite the server's aggregate evidence.
      expect(store.getSnapshot().thread?.session.status).toBe('idle');
    },
  );

  it.each([
    { statuses: ['running', 'queued'], expected: 'running' },
    { statuses: ['cancelling', 'running', 'queued'], expected: 'cancelling' },
    { statuses: ['queued', 'cancelling', 'running'], expected: 'cancelling' },
  ] as const)('uses pending priority for $statuses', async ({ statuses, expected }) => {
    await setup(
      'idle',
      statuses.map((status, index) => replyRun(`run/${index}`, { status })),
    );
    expectStatus(expected);
  });

  it.each(['failed', 'interrupted', 'compacting'] as const)(
    'preserves emitted %s despite pending run snapshots',
    async (status) => {
      await setup(status, [replyRun('pending', { status: 'running' })]);
      expectStatus(status);
    },
  );

  it('preserves deleting in all rendered status surfaces before the store removes the chat', () => {
    // The normal store immediately removes deleting chats. This snapshot tests
    // presentation of that transient state without bypassing it in production.
    const thread = replyThread({
      session: { ...session(), status: 'deleting' },
      runs: [replyRun('pending', { status: 'running' })],
    });
    const { transport } = fixtureTransport();
    const store = new HarnessStore(transport);
    const state = {
      ...store.getSnapshot(),
      sessions: [thread.session],
      selectedId: thread.session.id,
      thread,
      loading: false,
      listLoading: false,
      healthLoaded: true,
    };
    vi.spyOn(store, 'getSnapshot').mockReturnValue(state);
    vi.spyOn(store, 'start').mockResolvedValue();
    render(<App store={store} />);
    expectStatus('deleting');
  });

  it('keeps idle with no pending runs and after the last pending run settles', async () => {
    const completed = replyRun('finished', { status: 'completed' });
    const { streams } = await setup('idle', [completed]);
    expectStatus('idle');
    expect(
      screen.getByRole('status', { name: 'Run status' }).querySelector('.working-spinner'),
    ).toBeNull();
    act(() => {
      streams[0].callbacks.event(
        event(1, 'run', {
          run: replyRun('next', { status: 'queued' }),
        }),
      );
    });
    expectStatus('queued');
    act(() => {
      streams[0].callbacks.event(
        event(2, 'run', {
          run: replyRun('next', { status: 'completed' }),
        }),
      );
    });
    expectStatus('idle');
  });

  it('uses list aggregates after switching away without retaining stale pending runs', async () => {
    const user = userEvent.setup();
    const fixture = fixtureTransport();
    fixture.transport.list.mockResolvedValue({
      sessions: [session(), session('chat/b'), { ...session('chat/c'), status: 'compacting' }],
    });
    fixture.transport.snapshot.mockImplementation(async (id) => ({
      ...snapshot(id),
      runs: id === 'chat/a' ? [replyRun('queued', { status: 'queued' })] : [],
    }));
    const store = new HarnessStore(fixture.transport);
    render(<App store={store} />);
    await screen.findByRole('textbox', { name: 'Message' });
    expectStatus('queued');
    await user.click(screen.getByRole('button', { name: /^Chat chat\/b\s*idle$/ }));
    await waitFor(() => expect(store.getSnapshot().thread?.session.id).toBe('chat/b'));
    expect(screen.getByRole('button', { name: /^Chat chat\/a\s*idle$/ })).not.toHaveAttribute(
      'aria-current',
    );
    expect(screen.getByRole('button', { name: /^Chat chat\/c\s*compacting$/ })).toBeInTheDocument();
    expect(fixture.transport.snapshot.mock.calls.some(([id]) => id === 'chat/c')).toBe(false);
    // A fresh idle list must not inherit stale typed runs from the closed stream.
    await act(async () => {
      await store.refreshList(false);
    });
    expect(screen.getByRole('button', { name: /^Chat chat\/a\s*idle$/ })).toBeInTheDocument();
    // Non-idle list aggregates also remain authoritative.
    fixture.transport.list.mockResolvedValue({
      sessions: [
        { ...session(), status: 'failed' },
        session('chat/b'),
        { ...session('chat/c'), status: 'compacting' },
      ],
    });
    await act(async () => {
      await store.refreshList(false);
    });
    expect(screen.getByRole('button', { name: /^Chat chat\/a\s*failed$/ })).toBeInTheDocument();
  });
});
