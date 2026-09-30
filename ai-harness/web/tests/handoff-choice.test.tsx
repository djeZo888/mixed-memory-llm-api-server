import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { api } from '../src/api';
import { HarnessStore } from '../src/store';
import type { EngineKind } from '../src/types';
import { deferred, event, fixtureTransport, snapshot } from './fixtures';

function handoffFixture(engineKind: EngineKind, available = true) {
  const fixture = fixtureTransport();
  fixture.transport.health.mockResolvedValue({
    visionAvailable: false, engines: { default: "minimax", codex: { available } },
  });
  fixture.transport.snapshot.mockImplementation(async id => ({
    ...snapshot(id), session: { ...snapshot(id).session, engineKind: id === 'chat/a' ? engineKind : 'minimax' },
  }));
  return { ...fixture, store: new HarnessStore(fixture.transport) };
}

it.each([
  ['minimax', 'codex'], ['codex', 'minimax'],
] as const)('continues %s in an explicitly chosen %s chat without changing the source', async (source, target) => {
  const { store, transport } = handoffFixture(source);
  render(<App store={store} />);
  const selector = await screen.findByRole('combobox', { name: 'Harness for continued chat' });
  expect(selector).toHaveValue(source);
  expect(screen.getByRole('combobox', { name: 'Harness for new chat' })).toHaveValue('minimax');
  await userEvent.selectOptions(selector, target);
  await userEvent.click(screen.getByRole('button', { name: 'Continue in new chat' }));
  await waitFor(() => expect(transport.handoff).toHaveBeenCalledWith('chat/a', target));
  expect(transport.handoff).toHaveBeenCalledTimes(1);
  expect(store.getSnapshot().thread?.session.engineKind).toBe(source);
  expect(store.getSnapshot().selectedId).toBe('chat/a');
  expect(transport.create).not.toHaveBeenCalled();
  expect(transport.send).not.toHaveBeenCalled();
});

it('defaults to each source engine and keeps unavailable Codex explicit', async () => {
  const { store, transport } = handoffFixture('codex', false);
  render(<App store={store} />);
  const selector = await screen.findByRole('combobox', { name: 'Harness for continued chat' });
  expect(selector).toHaveValue('codex');
  expect(within(selector).getByRole('option', { name: /Codex/ })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Continue in new chat' })).toBeDisabled();
  await store.handoff('chat/a', 'codex');
  await store.handoff('chat/a');
  expect(transport.handoff).not.toHaveBeenCalled();
  await userEvent.selectOptions(selector, 'minimax');
  expect(selector).toHaveValue('minimax');
  expect(screen.getByRole('button', { name: 'Continue in new chat' })).toBeEnabled();
  await userEvent.click(screen.getByRole('button', { name: /^Chat chat\/b/ }));
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Harness for continued chat' })).toHaveValue('minimax'));
  expect(screen.getByRole('button', { name: 'Continue in new chat' })).toBeEnabled();
});

it('disables a selected target when refreshed health withdraws it without silently switching engines', async () => {
  vi.useFakeTimers();
  const { store, transport } = handoffFixture('minimax');
  try {
    await act(async () => { render(<App store={store} />); });
    const selector = screen.getByRole('combobox', { name: 'Harness for continued chat' });
    fireEvent.change(selector, { target: { value: 'codex' } });
    transport.health.mockResolvedValue({ visionAvailable: false, engines: { default: "minimax", codex: { available: false } } });
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    expect(selector).toHaveValue('codex');
    expect(screen.getByRole('button', { name: 'Continue in new chat' })).toBeDisabled();
    await act(async () => { await store.handoff('chat/a', 'codex'); });
    expect(transport.handoff).not.toHaveBeenCalled();
    fireEvent.change(selector, { target: { value: 'minimax' } });
    expect(screen.getByRole('button', { name: 'Continue in new chat' })).toBeEnabled();
  } finally {
    store.dispose();
    vi.useRealTimers();
  }
});

it('holds a chosen target through late acknowledgement and never dispatches a competing handoff', async () => {
  const { store, transport, streams } = handoffFixture('minimax');
  await store.start();
  await waitFor(() => expect(store.getSnapshot().thread?.session.id).toBe('chat/a'));
  const ack = deferred<{ runId: string }>();
  transport.handoff.mockReturnValueOnce(ack.promise);
  const pending = store.handoff('chat/a', 'codex');
  await store.handoff('chat/a', 'minimax');
  expect(transport.handoff).toHaveBeenCalledTimes(1);
  expect(transport.handoff).toHaveBeenCalledWith('chat/a', 'codex');
  streams[0].callbacks.event(event(1, 'handoff', { newSessionId: 'continued' }));
  ack.resolve({ runId: 'handoff/target' });
  await pending;
  expect(store.getSnapshot().selectedId).toBe('continued');
  expect(store.getSnapshot().submitted['chat/a']).toBeUndefined();
  expect(store.getSnapshot().sessions.some(session => session.id === 'chat/a')).toBe(true);
  store.dispose();
});

it('sends only an explicit target engine and preserves the omitted request contract', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () => new Response(JSON.stringify({ runId: 'handoff/wire' })),
  );
  await api.handoff('source/chat');
  await api.handoff('source/chat', 'codex');
  await api.handoff('source/chat', 'minimax');
  expect(fetcher.mock.calls.map(([path, init]) => ({ path, method: init?.method, body: init?.body }))).toEqual([
    { path: '/api/sessions/source%2Fchat/handoff', method: 'POST', body: '{}' },
    { path: '/api/sessions/source%2Fchat/handoff', method: 'POST', body: '{"engineKind":"codex"}' },
    { path: '/api/sessions/source%2Fchat/handoff', method: 'POST', body: '{"engineKind":"minimax"}' },
  ]);
});
