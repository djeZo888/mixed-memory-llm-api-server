import { beforeEach, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { useSyncExternalStore } from 'react';
import userEvent from '@testing-library/user-event';
import { HarnessStore } from '../src/store';
import { Composer } from '../src/Composer';
import { api, ApiError } from '../src/api';
import { readSubmission } from '../src/submissions';
import { deferred, fixtureTransport } from './fixtures';
const id = 'chat/a';
beforeEach(() => sessionStorage.clear());
async function ready(fixture = fixtureTransport()) {
  const store = new HarnessStore(fixture.transport);
  await store.start(id);
  await waitFor(() => expect(store.getSnapshot().thread?.session.id).toBe(id));
  return { store, ...fixture };
}
function Live({ store }: { store: HarnessStore }) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  return <Composer store={store} state={state} id={id} />;
}
it('lost ACK keeps exact payload/ID through reconnect and reload; explicit retry alone resends and a new prompt gets a new ID', async () => {
  const f = await ready();
  await f.store.upload(id, new File(['notes'], 'notes.txt', { type: 'text/plain' }));
  f.transport.send.mockRejectedValueOnce(new TypeError('network lost after acceptance'));
  expect(await f.store.send(id, 'Original submitted bytes\n')).toBe(false);
  const saved = readSubmission(id)!;
  expect(saved.text).toBe('Original submitted bytes\n');
  expect(saved.attachmentIds).toEqual(['file/1']);
  expect(f.transport.send).toHaveBeenCalledWith(id, saved.text, ['file/1'], [], saved.submissionId);
  f.streams[0].callbacks.disconnected(); f.streams[0].callbacks.open();
  await f.store.resync();
  expect(f.transport.send).toHaveBeenCalledTimes(1);
  expect(await f.store.send(id, 'Edited current draft')).toBe(false);
  expect(readSubmission(id)).toEqual(saved);
  f.store.dispose();
  const next = await ready();
  expect(next.transport.send).not.toHaveBeenCalled();
  expect(next.store.getSnapshot().pendingSubmissions[id]).toEqual(saved);
  expect(await next.store.retrySubmission(id)).toBe(true);
  expect(next.transport.send).toHaveBeenCalledWith(id, saved.text, ['file/1'], [], saved.submissionId);
  expect(readSubmission(id)).toBeUndefined();
  expect(await next.store.send(id, saved.text)).toBe(true);
  const second = next.transport.send.mock.calls[1] as unknown as unknown[];
  expect(second[4]).not.toBe(saved.submissionId);
  expect(second[1]).toBe(saved.text);
  next.store.dispose();
});
it('composer offers an explicit retry even when Codex becomes unavailable, preserving a changed draft', async () => {
  const f = await ready(), user = userEvent.setup();
  render(<Live store={f.store} />);
  const textbox = screen.getByRole('textbox');
  await user.type(textbox, 'Original');
  f.transport.send.mockRejectedValueOnce(new TypeError('ACK lost'));
  await user.click(screen.getByRole('button', { name: 'Send message' }));
  expect(await screen.findByRole('button', { name: 'Retry saved submission' })).toBeEnabled();
  const saved = readSubmission(id)!;
  // A snapshot health change must not gate retrieval of a committed run.
  f.transport.snapshot.mockImplementation(async () => ({ session: { id, title: 'Codex', status: 'idle' as const, engineKind: 'codex' as const, createdAt: '', updatedAt: '' }, messages: [], artifacts: [], events: [] }));
  await act(async () => { await f.store.resync(); });
  expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
  await user.click(screen.getByRole('button', { name: 'Retry saved submission' }));
  expect(f.transport.send).toHaveBeenLastCalledWith(id, 'Original', [], [], saved.submissionId);
  expect(readSubmission(id)).toBeUndefined();
  f.store.dispose();
});
it('storage failure blocks HTTP; corrupt or wrong-chat saved payload cannot be silently replaced', async () => {
  const f = await ready();
  const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw Error('storage full'); });
  expect(await f.store.send(id, 'Never sent')).toBe(false);
  expect(f.transport.send).not.toHaveBeenCalled(); write.mockRestore();
  sessionStorage.setItem(`ai-harness:submission:${id}`, JSON.stringify({ version: 1, sessionId: 'chat/b', submissionId: 'other', text: 'private', attachmentIds: [], imageReferences: [] }));
  expect(await f.store.retrySubmission(id)).toBe(false);
  expect(await f.store.send(id, 'Do not overwrite')).toBe(false);
  expect(f.transport.send).not.toHaveBeenCalled();
  expect(sessionStorage.getItem(`ai-harness:submission:${id}`)).toContain('private');
  f.store.dispose();
});
it('unreadable ACK and conflicts retain pending payload; deletion removes it and forbids late retry', async () => {
  const f = await ready();
  f.transport.send.mockResolvedValueOnce({} as { runId: string });
  expect(await f.store.send(id, 'Pending')).toBe(false);
  const saved = readSubmission(id);
  f.transport.send.mockRejectedValueOnce(new ApiError(409, 'submission_conflict', 'Conflict'));
  expect(await f.store.retrySubmission(id)).toBe(false);
  expect(readSubmission(id)).toEqual(saved);
  await f.store.remove(id);
  expect(readSubmission(id)).toBeUndefined();
  expect(await f.store.retrySubmission(id)).toBe(false);
  expect(f.transport.send).toHaveBeenCalledTimes(2);
  f.store.dispose();
});
it('double clicks submit once and late known ACK clears recovery after dispose', async () => {
  const f = await ready(), ack = deferred<{ runId: string }>();
  f.transport.send.mockReturnValueOnce(ack.promise);
  const sending = f.store.send(id, 'one');
  expect(await f.store.send(id, 'one')).toBe(false);
  expect(f.transport.send).toHaveBeenCalledTimes(1);
  expect(readSubmission(id)).toBeDefined();
  f.store.dispose(); ack.resolve({ runId: 'retained' }); await sending;
  expect(readSubmission(id)).toBeUndefined();
});
it('real HTTP transport includes supplied stable ID and complete attachment/reference payload', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ runId: 'saved-run' }), { status: 202 }));
  await api.send('owned', 'exact\ntext', ['attachment-a'], ['image-b'], 'submission-c');
  expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toEqual({ submissionId: 'submission-c', text: 'exact\ntext', attachmentIds: ['attachment-a'], imageReferences: ['image-b'] });
});

it('definite validation rejection unlocks correction; unknown/proxy errors do not discard uncertain IDs', async () => {
  const f = await ready();
  f.transport.send.mockRejectedValueOnce(new ApiError(400, 'unsupported_slash_command', 'Use a normal prompt'));
  expect(await f.store.send(id, '/compact')).toBe(false);
  const rejectedCall = f.transport.send.mock.calls[0] as unknown as unknown[];
  expect(readSubmission(id)).toBeUndefined();
  expect(f.store.getSnapshot().pendingSubmissions[id]).toBeUndefined();
  expect(await f.store.send(id, 'Corrected request')).toBe(true);
  const correctedCall = f.transport.send.mock.calls[1] as unknown as unknown[];
  expect(correctedCall[4]).not.toBe(rejectedCall[4]);
  f.transport.send.mockRejectedValueOnce(new ApiError(400, 'proxy_error', 'Unknown boundary'));
  expect(await f.store.send(id, 'Uncertain')).toBe(false);
  expect(readSubmission(id)?.text).toBe('Uncertain');
  f.store.dispose();
});
