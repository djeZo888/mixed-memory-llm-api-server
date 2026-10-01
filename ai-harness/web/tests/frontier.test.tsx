import { afterEach, expect, it, vi } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { FrontierActivity } from '../src/FrontierActivity';
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('shows useful research progress only for actual work, without exposing model/runtime identifiers', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ model: 'mimo-private-id', configured: true, state: 'active', queued: 2, requests: [{ state: 'active', promptTokens: 12345, reservedOutput: 65536 }] }) })));
  render(<FrontierActivity sessionId="owned" />);
  const activity = await screen.findByLabelText('Research activity');
  expect(activity).toHaveTextContent('Research in progress · 2 waiting');
  expect(activity).not.toHaveTextContent('mimo-private-id');
  expect(screen.queryByRole('meter')).toBeNull();
});
it('does not show idle inventory or revive an old chat response after selection changes', async () => {
  let release: (value: unknown) => void = () => {};
  vi.stubGlobal('fetch', vi.fn((url: string) => url.includes('/first/') ? new Promise(resolve => { release = resolve; }) : Promise.resolve({ ok: true, json: async () => ({ configured: true, state: 'idle', queued: 0, requests: [] }) })));
  const view = render(<FrontierActivity sessionId="first" />);
  view.rerender(<FrontierActivity sessionId="second" />);
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  release({ ok: true, json: async () => ({ configured: true, state: 'active', queued: 8, requests: [{ state: 'active' }] }) });
  await waitFor(() => expect(screen.queryByLabelText('Research activity')).toBeNull());
});
