import { afterEach, expect, it, vi } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { FrontierActivity } from '../src/FrontierActivity';
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it('shows separate exact frontier occupancy and queue without creating a main context meter', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        model: 'glm-5.3-flash',
        configured: true,
        state: 'active',
        contextWindow: 480000,
        queued: 2,
        requests: [{ state: 'active', promptTokens: 12345, reservedOutput: 65536 }],
      }),
    })),
  );
  render(<FrontierActivity sessionId="owned" />);
  const badge = await screen.findByLabelText('Frontier child activity');
  expect(badge.textContent).toContain('queue 2/8');
  expect(badge.textContent).toContain('rendered input 12,345');
  expect(badge.textContent).toContain('output reserve 65,536');
  expect(screen.queryByRole('progressbar')).toBeNull();
});
it('old chat response cannot overwrite selected child activity after reconnect/switch', async () => {
  let release: (v: unknown) => void = () => {};
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      url.includes('/first/')
        ? new Promise((r) => {
            release = r;
          })
        : Promise.resolve({
            ok: true,
            json: async () => ({
              model: 'glm-5.3-flash',
              configured: true,
              state: 'idle',
              contextWindow: 480000,
              queued: 0,
              requests: [],
            }),
          }),
    ),
  );
  const view = render(<FrontierActivity sessionId="first" />);
  view.rerender(<FrontierActivity sessionId="second" />);
  await screen.findByLabelText('Frontier child activity');
  release({
    ok: true,
    json: async () => ({
      model: 'wrong-old-chat',
      configured: true,
      state: 'active',
      contextWindow: 128000,
      queued: 8,
      requests: [],
    }),
  });
  await waitFor(() =>
    expect(screen.getByLabelText('Frontier child activity').textContent).toContain('glm-5.3-flash'),
  );
  expect(screen.queryByText(/wrong-old-chat/)).toBeNull();
});

it.each([
  ['idle', 'unavailable'],
  ['idle', 'available'],
  ['quarantined', 'available'],
  ['idle', undefined],
])('distinguishes lane %s from backend %s', async (lane, backend) => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    json: async () => ({model: 'glm-5.3-flash', configured: true, state: lane,
      availability: backend ? {state: backend} : undefined,
      contextWindow: 480000, queued: 0, requests: []}),
  })));
  render(<FrontierActivity sessionId="owned" />);
  const badge = await screen.findByLabelText('Frontier child activity');
  expect(badge.textContent).toContain(`backend ${backend ?? 'unknown'}`);
  expect(badge.textContent).toContain(`lane ${lane}`);
  expect(screen.queryByRole('progressbar')).toBeNull();
});

it('MiMo shows separate allocated and largest completed input plus historical actual model', async () => {
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({model:'mimo-v2.6-pro-rl',provider:'mimo',configured:true,state:'idle',contextWindow:131072,queued:0,capacity:{configured:131072,allocated:131072,occupiedTested:4096},requests:[{model:'glm-5.3-flash',state:'settled'}]})})));
  render(<FrontierActivity sessionId="owned" />);
  const badge=await screen.findByLabelText('Frontier child activity');
  expect(badge.textContent).toContain('allocated 131,072');expect(badge.textContent).toContain('largest completed input 4,096');expect(badge.textContent).toContain('glm-5.3-flash settled');expect(screen.queryByRole('progressbar')).toBeNull();
});
