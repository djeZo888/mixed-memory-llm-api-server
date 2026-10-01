import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it } from 'vitest';
import { App } from '../src/App';
import { HarnessStore } from '../src/store';
import { fixtureTransport } from './fixtures';

it('creates only the active chat engine even when the server reports an old default', async () => {
  const { transport } = fixtureTransport();
  transport.health.mockResolvedValue({ visionAvailable: false, engines: { default: 'minimax', codex: { available: true } } });
  const store = new HarnessStore(transport);
  render(<App store={store} />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'New chat' })).toBeEnabled());
  expect(screen.queryByRole('combobox', { name: /Harness/ })).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'New chat' }));
  await waitFor(() => expect(transport.create).toHaveBeenCalledWith('codex'));
  await store.create('minimax');
  expect(transport.create).toHaveBeenCalledTimes(1);
});

it('does not substitute an old engine when active chat availability is withdrawn', async () => {
  const { transport } = fixtureTransport();
  transport.health.mockResolvedValue({ visionAvailable: false, engines: { default: 'minimax', codex: { available: false, configured: true, protocolQualified: true } } });
  const store = new HarnessStore(transport);
  render(<App store={store} />);
  await screen.findByText('Chat is temporarily unavailable. Your history and files are saved.');
  expect(screen.getByRole('button', { name: 'New chat' })).toBeDisabled();
  await store.create();
  await store.create('minimax');
  expect(transport.create).not.toHaveBeenCalled();
  expect(screen.getByRole('textbox', { name: 'Message' })).toBeDisabled();
});
