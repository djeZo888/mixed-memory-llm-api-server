import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { ApiError } from '../src/api';
import { HarnessStore } from '../src/store';
import { createdAt, fixtureTransport, snapshot } from './fixtures';

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ configured: false, requests: [], queued: 0 })),
  );
});

// Consumer contract fixture for the older normal service. This does not
// qualify deployed chat, compaction, image analysis, or browser operation.
function normalService(imageJobsCode = 'image_unavailable') {
  const fixture = fixtureTransport();
  fixture.transport.health.mockResolvedValue({
    // The legacy broad flag must not advertise qualified image analysis.
    visionAvailable: true,
    engines: { default: 'codex', codex: { available: true, imageToolEnabled: false } },
    availability: { qwenGpu0: 'available', qwenGpu1: 'available', image: 'unavailable' },
  });
  fixture.transport.imageCapabilities.mockRejectedValue(
    new ApiError(503, 'image_service_unavailable', 'Image service is unavailable'),
  );
  fixture.transport.imageJobs.mockRejectedValue(
    new ApiError(503, imageJobsCode, 'Image broker is not configured'),
  );
  fixture.transport.snapshot.mockImplementation(async id => ({
    ...snapshot(id),
    messages: [{ id: 'retained', role: 'user', content: 'Remember the blue notebook.', createdAt }],
  }));
  return { ...fixture, store: new HarnessStore(fixture.transport) };
}

it.each(['image_unavailable', 'image_service_unavailable'])(
  'keeps the same chat usable when optional image jobs return %s',
  async code => {
    const { store, transport } = normalService(code);
    const view = render(<App store={store} />);
    const user = userEvent.setup();
    await screen.findByText('Remember the blue notebook.');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Compact context' })).toBeEnabled());
    expect(screen.getByRole('button', { name: 'New chat' })).toBeEnabled();
    expect(screen.queryByRole('combobox', { name: /model|harness/i })).toBeNull();
    expect(view.container).not.toHaveTextContent(/Codex|MiniMax|Qwen|harness|Image broker/i);
    await user.click(screen.getByText('Attachment help'));
    expect(screen.getByText('Image analysis is unavailable.')).toBeVisible();
    expect(screen.getByLabelText('Upload file')).not.toHaveAttribute('accept', expect.stringContaining('image/'));
    await user.type(screen.getByRole('textbox', { name: 'Message' }), 'What colour was the notebook?');
    const send = screen.getByRole('button', { name: 'Send message' });
    expect(send).toBeEnabled();
    await user.click(send);
    await waitFor(() => expect(transport.send).toHaveBeenCalledWith(
      'chat/a', 'What colour was the notebook?', [], [], expect.any(String),
    ));
    expect(transport.send).toHaveBeenCalledOnce();
    expect(transport.create).not.toHaveBeenCalled();
    expect(store.getSnapshot().selectedId).toBe('chat/a');
    expect(screen.getByText('Remember the blue notebook.')).toBeInTheDocument();
    view.unmount();
  },
);

it('does not send image uploads when the older health contract has no technical analysis capability', async () => {
  const { store, transport } = normalService();
  const view = render(<App store={store} />);
  await screen.findByText('Remember the blue notebook.');
  await act(async () => {
    expect(await store.upload('chat/a', new File(['fixture'], 'drawing.png', { type: 'image/png' }))).toBe(false);
  });
  expect(transport.upload).not.toHaveBeenCalled();
  expect(transport.send).not.toHaveBeenCalled();
  expect(screen.getByRole('textbox', { name: 'Message' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Compact context' })).toBeEnabled();
  view.unmount();
});
