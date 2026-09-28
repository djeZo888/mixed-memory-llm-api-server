import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { HarnessStore } from '../src/store';
import { fixtureTransport, snapshot } from './fixtures';
it('reuses selected Codex artifact as attachment and never claims native image recognition', async () => {
  const { transport } = fixtureTransport();
  const file = {
    id: 'artifact-a',
    name: 'notes.txt',
    mimeType: 'text/plain',
    size: 3,
    downloadUrl: '/api/artifacts/artifact-a/download',
  };
  transport.snapshot.mockImplementation(async (id) => ({
    ...snapshot(id),
    session: { ...snapshot(id).session, engineKind: 'codex' },
    artifacts: [file],
  }));
  const reference = vi.fn(async () => ({ attachment: { ...file, id: 'copy-a' } }));
  const store = new HarnessStore({ ...transport, reference });
  render(<App store={store} />);
  const select = await screen.findByRole('combobox', { name: 'Reuse workspace file' });
  await userEvent.selectOptions(select, 'artifact-a');
  await waitFor(() => expect(reference).toHaveBeenCalledWith('chat/a', 'artifact-a'));
  expect(await screen.findByRole('button', { name: 'Remove attachment notes.txt' })).toBeEnabled();
  expect(
    screen.getByText(/Native image, audio and video recognition is unavailable/),
  ).toBeInTheDocument();
});
