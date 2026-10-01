import { render, screen, waitFor, within } from '@testing-library/react';
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
  expect(within(selector).getByRole('option', { name: /Codex/ })).toBeDisabled();
  await store.create('codex');
  expect(transport.create).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'New chat' }));
  await waitFor(() => expect(transport.create).toHaveBeenCalledWith("minimax"));
});
it('qualified deployment enables new-chat choice and sends immutable engine choice only on creation', async () => {
  const { transport } = fixtureTransport();
  transport.health.mockResolvedValue({
    visionAvailable: false,
    engines: { default: "codex", codex: { available: true } },
  });
  const store = new HarnessStore(transport);
  render(<App store={store} />);
  const selector = screen.getByRole('combobox', { name: 'Harness for new chat' });
  await waitFor(() => expect(within(selector).getByRole('option', { name: /Codex/ })).toBeEnabled());
  expect(selector).toHaveValue('codex');
  await userEvent.selectOptions(selector, 'codex');
  await userEvent.click(screen.getByRole('button', { name: 'New chat' }));
  await waitFor(() => expect(transport.create).toHaveBeenCalledWith('codex'));
  expect(transport.send).not.toHaveBeenCalled();
});
it('keeps an unavailable Codex default selected and permits only an explicit MiniMax alternative', async () => {
  const { transport } = fixtureTransport();
  transport.health.mockResolvedValue({ visionAvailable: false, engines: { default: 'codex', codex: { available: false } } });
  const store = new HarnessStore(transport);
  render(<App store={store} />);
  const selector = screen.getByRole('combobox', { name: 'Harness for new chat' });
  await waitFor(() => expect(selector).toHaveValue('codex'));
  expect(screen.getByRole('button', { name: 'New chat' })).toBeDisabled();
  await store.create(); expect(transport.create).not.toHaveBeenCalled();
  await userEvent.selectOptions(selector, 'minimax');
  await userEvent.click(screen.getByRole('button', { name: 'New chat' }));
  await waitFor(() => expect(transport.create).toHaveBeenCalledWith('minimax'));
});
it('shows qualification separately from configuration without enabling preview', async () => {
  const { transport } = fixtureTransport();
  transport.health.mockResolvedValue({
    visionAvailable: false,
    engines: {
      codex: {
        available: false,
        configured: true,
        version: '0.158.0',
        readiness: 'disabled',
        protocolQualified: true,
        capabilityDetails: {
          nativeDelegation: {
            supported: false,
            qualification: 'native_fixture',
            reason: 'Gateway qualification pending',
          },
          nativeMedia: {
            supported: false,
            qualification: 'not_tested',
            reason: 'Native media unavailable',
          },
        },
      },
    },
  });
  const store = new HarnessStore(transport);
  render(<App store={store} />);
  await screen.findByText(/Configured · 0.158.0 · disabled/);
  expect(within(screen.getByRole('combobox', { name: 'Harness for new chat' })).getByRole('option', { name: /Codex/ })).toBeDisabled();
  expect(screen.getByText(/Gateway qualification pending/)).toBeInTheDocument();
  expect(screen.getByText(/Live acceptance is separate/)).toBeInTheDocument();
});
