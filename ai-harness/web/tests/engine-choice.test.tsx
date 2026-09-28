import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it } from 'vitest';
import { App } from '../src/App';
import { HarnessStore } from '../src/store';
import { fixtureTransport } from './fixtures';
it('defaults new chat to MiniMax and disables unqualified Codex preview', async () => {
  const { transport } = fixtureTransport();
  const store = new HarnessStore(transport);
  render(<App store={store} />);
  const selector = await screen.findByRole('combobox', { name: 'Harness for new chat' });
  expect(selector).toHaveValue('minimax');
  expect(screen.getByRole('option', { name: /Codex/ })).toBeDisabled();
  await store.create('codex');
  expect(transport.create).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'New chat' }));
  await waitFor(() => expect(transport.create).toHaveBeenCalledWith(undefined));
});
it('qualified deployment enables new-chat choice and sends immutable engine choice only on creation', async () => {
  const { transport } = fixtureTransport();
  transport.health.mockResolvedValue({
    visionAvailable: false,
    engines: { codex: { available: true } },
  });
  const store = new HarnessStore(transport);
  render(<App store={store} />);
  await waitFor(() => expect(screen.getByRole('option', { name: /Codex/ })).toBeEnabled());
  await userEvent.selectOptions(screen.getByRole('combobox'), 'codex');
  await userEvent.click(screen.getByRole('button', { name: 'New chat' }));
  await waitFor(() => expect(transport.create).toHaveBeenCalledWith('codex'));
  expect(transport.send).not.toHaveBeenCalled();
});
