import { afterEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useSyncExternalStore } from 'react';
import { HarnessStore } from '../src/store';
import { Composer } from '../src/Composer';
import type { Transport } from '../src/api';
import { deferred, fixtureTransport } from './fixtures';

afterEach(() => vi.useRealTimers());

it('refreshes service availability every five seconds without blocking chat on observer failure', async () => {
  vi.useFakeTimers();
  const { transport } = fixtureTransport();
  transport.health
    .mockResolvedValueOnce({
      visionAvailable: true,
      availability: {
        qwenGpu0: 'available',
        qwenGpu1: 'available',
        image: 'available',
      },
    })
    .mockResolvedValueOnce({
      visionAvailable: true,
      availability: {
        qwenGpu0: 'unavailable',
        qwenGpu1: 'available',
        image: 'unavailable',
      },
    })
    .mockRejectedValueOnce(new Error('private observer detail'));
  const store = new HarnessStore(transport);
  try {
    await store.start();
    await vi.advanceTimersByTimeAsync(0);
    expect(store.getSnapshot().serviceAvailability?.qwenGpu0).toBe('available');
    await vi.advanceTimersByTimeAsync(5000);
    expect(store.getSnapshot().serviceAvailability?.qwenGpu0).toBe('unavailable');
    await vi.advanceTimersByTimeAsync(5000);
    expect(store.getSnapshot().serviceAvailability?.qwenGpu0).toBe('unknown');
    expect(store.getSnapshot().visionAvailable).toBe(true);
    await store.send('chat/a', 'synthetic request');
    expect(transport.send).toHaveBeenCalledOnce();
    expect(store.getSnapshot().error).toBeNull();
  } finally {
    store.dispose();
  }
  await vi.advanceTimersByTimeAsync(10000);
  expect(transport.health).toHaveBeenCalledTimes(3);
});

it('caps hung health work and discards late success after the two second deadline', async () => {
  vi.useFakeTimers();
  const { transport } = fixtureTransport();
  const hung = deferred<Awaited<ReturnType<Transport['health']>>>();
  transport.health.mockReturnValueOnce(hung.promise);
  const store = new HarnessStore(transport);
  try {
    await store.start();
    await vi.advanceTimersByTimeAsync(30000);
    expect(transport.health).toHaveBeenCalledOnce();
    expect(transport.health.mock.calls[0][0]?.aborted).toBe(true);
    expect(store.getSnapshot().serviceAvailability?.image).toBe('unknown');
    hung.resolve({
      visionAvailable: true,
      availability: { qwenGpu0: 'available', qwenGpu1: 'available', image: 'available' },
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(store.getSnapshot().serviceAvailability?.image).toBe('unknown');
    await vi.advanceTimersByTimeAsync(5000);
    expect(transport.health).toHaveBeenCalledTimes(2);
  } finally {
    store.dispose();
  }
});

it('shows partial Qwen and image degradation with a status link while permitting ordinary chat', async () => {
  const { transport } = fixtureTransport();
  transport.health.mockResolvedValue({
    visionAvailable: false,
    availability: {
      qwenGpu0: 'unavailable',
      qwenGpu1: 'available',
      image: 'unavailable',
    },
  });
  const store = new HarnessStore(transport);
  try {
    await store.start();
    await waitFor(() => expect(store.getSnapshot().thread).not.toBeNull());
    function View() {
      const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
      return <Composer store={store} state={state} id="chat/a" />;
    }
    render(<View />);
    expect(screen.getByRole('status')).toHaveTextContent(
      'Text service degraded: one Qwen lane unavailable. Image service unavailable.',
    );
    expect(screen.getByRole('link', { name: 'View status' })).toHaveAttribute('href', '/status');
    fireEvent.change(screen.getByRole('textbox', { name: 'Message' }), {
      target: { value: 'synthetic prompt' },
    });
    expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled();
    fireEvent.submit(screen.getByRole('form', { name: 'Message composer' }));
    await waitFor(() => expect(transport.send).toHaveBeenCalledOnce());
  } finally {
    store.dispose();
  }
});
