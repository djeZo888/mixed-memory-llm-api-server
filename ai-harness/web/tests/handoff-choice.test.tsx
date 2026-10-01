import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it } from 'vitest';
import { App } from '../src/App';
import { HarnessStore } from '../src/store';
import { saveSubmission } from '../src/submissions';
import { fixtureTransport, snapshot } from './fixtures';

it.each(['minimax', undefined] as const)('preserves an earlier %s chat and never executes it on send, retry or handoff', async engineKind => {
  const { transport } = fixtureTransport();
  transport.snapshot.mockImplementation(async id => ({
    ...snapshot(id), session: { ...snapshot(id).session, engineKind },
    messages: [{ id: 'old', role: 'user', content: 'Original history', createdAt: '' }],
    attachments: [{ id: 'old-file', name: 'original.txt', size: 3, mimeType: 'text/plain' }],
  }));
  saveSubmission({ version: 1, sessionId: 'chat/a', submissionId: 'saved-original', text: 'Pending old follow-up', attachmentIds: [], imageReferences: [] });
  const store = new HarnessStore(transport);
  render(<App store={store} />);
  await screen.findByText('Original history');
  expect(screen.getByRole('textbox', { name: 'Message' })).toBeDisabled();
  await store.send('chat/a', 'Follow up');
  await store.retrySubmission('chat/a');
  await store.handoff('chat/a', 'codex');
  await store.upload('chat/a', new File(['text'], 'new.txt', { type: 'text/plain' }));
  expect(transport.send).not.toHaveBeenCalled();
  expect(transport.handoff).not.toHaveBeenCalled();
  expect(transport.upload).not.toHaveBeenCalled();
  expect(store.getSnapshot().thread?.session.engineKind).toBe(engineKind);
  expect(store.getSnapshot().thread?.attachments[0].id).toBe('old-file');
  await userEvent.click(screen.getByRole('button', { name: 'Start a new chat' }));
  await waitFor(() => expect(transport.create).toHaveBeenCalledWith('codex'));
  expect(store.getSnapshot().sessions.some(session => session.id === 'chat/a')).toBe(true);
});
