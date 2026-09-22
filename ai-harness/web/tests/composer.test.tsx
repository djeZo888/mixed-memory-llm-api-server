import { useSyncExternalStore } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { Composer } from '../src/Composer';
import { HarnessStore } from '../src/store';
import { MAX_UPLOAD_BYTES } from '../src/uploads';
import { deferred, fixtureTransport } from './fixtures';

async function setup(visionAvailable = false) {
  const fixture = fixtureTransport();
  fixture.transport.health.mockResolvedValue({ visionAvailable });
  const store = new HarnessStore(fixture.transport);
  await store.start();
  await waitFor(() => expect(store.getSnapshot().thread).not.toBeNull());
  function View() {
    const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
    return <Composer store={store} state={state} id="chat/a" />;
  }
  render(<View />);
  return { ...fixture, store };
}
function drop(files: File[]) {
  const target = screen.getByRole('form', { name: 'Message composer' });
  const event = new Event('drop', { bubbles: true, cancelable: true });
  Object.defineProperty(event, 'dataTransfer', { value: { types: ['Files'], files } });
  fireEvent(target, event);
  return event;
}
const result = (id: string, name: string) => ({
  attachment: { id, name, size: 4, mimeType: 'text/plain' },
});

describe('composer keyboard and file interactions', () => {
  it('keeps Enter as newline and submits with Ctrl+Enter and Cmd+Enter', async () => {
    const user = userEvent.setup();
    const { transport, store } = await setup();
    const input = screen.getByRole('textbox', { name: 'Message' });
    await user.type(input, 'First line{Enter}Second line');
    expect(input).toHaveValue('First line\nSecond line');
    expect(transport.send).not.toHaveBeenCalled();
    expect(screen.getByText('Enter for a new line · Ctrl / Cmd + Enter to send')).toBeVisible();
    await user.keyboard('{Control>}{Enter}{/Control}');
    expect(transport.send).toHaveBeenCalledWith('chat/a', 'First line\nSecond line', []);
    await waitFor(() => expect(input).toHaveValue(''));
    await user.type(input, 'Follow up');
    await user.keyboard('{Meta>}{Enter}{/Meta}');
    expect(transport.send).toHaveBeenLastCalledWith('chat/a', 'Follow up', []);
    store.dispose();
  });

  it('does not submit IME composition, native composing events or keyCode 229', async () => {
    const { transport, store } = await setup();
    const input = screen.getByRole('textbox', { name: 'Message' });
    fireEvent.change(input, { target: { value: '文章' } });
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: 'Enter', ctrlKey: true });
    fireEvent.compositionEnd(input);
    fireEvent.keyDown(input, { key: 'Enter', metaKey: true, isComposing: true });
    fireEvent.keyDown(input, { key: 'Enter', ctrlKey: true, keyCode: 229 });
    expect(transport.send).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: 'Enter', ctrlKey: true });
    await waitFor(() => expect(transport.send).toHaveBeenCalledOnce());
    store.dispose();
  });

  it('uploads multiple dropped files sequentially, prevents navigation, duplicates and send races', async () => {
    const { transport, store } = await setup();
    const first = deferred<Awaited<ReturnType<typeof transport.upload>>>();
    const second = deferred<Awaited<ReturnType<typeof transport.upload>>>();
    transport.upload.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const one = new File(['one'], 'one.txt', { type: 'text/plain' });
    const two = new File(['two'], 'two.txt', { type: 'text/plain' });
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Read both' } });
    expect(drop([one, one, two]).defaultPrevented).toBe(true);
    expect(transport.upload).toHaveBeenCalledTimes(1);
    const statuses = screen.getByRole('list', { name: 'File upload status' });
    expect(within(statuses).getByText('one.txt')).toBeVisible();
    expect(within(statuses).getByText('two.txt')).toBeVisible();
    expect(within(statuses).getByText('Queued')).toBeVisible();
    drop([one, two]);
    expect(screen.getByText(/Please wait for the current request/)).toBeVisible();
    fireEvent.submit(screen.getByRole('form', { name: 'Message composer' }));
    expect(transport.send).not.toHaveBeenCalled();
    await act(async () => {
      first.resolve(result('file/one', 'one.txt'));
    });
    await waitFor(() => expect(transport.upload).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
    await act(async () => {
      second.resolve(result('file/two', 'two.txt'));
    });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled());
    expect(screen.queryByRole('list', { name: 'File upload status' })).not.toBeInTheDocument();
    expect(
      within(screen.getByRole('list', { name: 'Attached files' })).getAllByText(/Ready/),
    ).toHaveLength(2);
    expect(screen.getByLabelText('Upload file')).toHaveAttribute('multiple');
    drop([one, two]);
    await waitFor(() =>
      expect(screen.queryByRole('list', { name: 'File upload status' })).not.toBeInTheDocument(),
    );
    expect(transport.upload).toHaveBeenCalledTimes(2);
    fireEvent.submit(screen.getByRole('form', { name: 'Message composer' }));
    await waitFor(() =>
      expect(transport.send).toHaveBeenCalledWith('chat/a', 'Read both', ['file/one', 'file/two']),
    );
    store.dispose();
  });

  it('shows per-file validation and server failures while continuing valid selections', async () => {
    const { transport, store } = await setup();
    transport.upload
      .mockRejectedValueOnce(new Error('Server refused this file.'))
      .mockResolvedValueOnce(result('valid', 'valid.txt'));
    const oversized = new File(['x'], 'oversized.txt', { type: 'text/plain' });
    Object.defineProperty(oversized, 'size', { value: MAX_UPLOAD_BYTES + 1 });
    const image = new File(['img'], 'photo.png', { type: 'image/png' });
    const refused = new File(['a'], 'refused.txt', { type: 'text/plain' });
    const valid = new File(['b'], 'valid.txt', { type: 'text/plain' });
    fireEvent.change(screen.getByLabelText('Upload file'), {
      target: { files: [image, oversized, refused, valid] },
    });
    await screen.findByText('Server refused this file.');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Attach files' })).toBeEnabled());
    expect(screen.getByText(/Image uploads are unavailable/)).toBeVisible();
    expect(screen.getByText('Upload exceeds 50 MiB per file.')).toBeVisible();
    expect(screen.getByText('valid.txt')).toBeVisible();
    expect(transport.upload).toHaveBeenCalledTimes(2);
    expect(transport.upload).toHaveBeenNthCalledWith(1, 'chat/a', refused);
    expect(transport.upload).toHaveBeenNthCalledWith(2, 'chat/a', valid);
    drop([image]);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Attach files' })).toBeEnabled());
    expect(transport.upload).toHaveBeenCalledTimes(2);
    store.dispose();
  });

  it('allows image drops only with the authoritative health capability', async () => {
    const { transport, store } = await setup(true);
    const file = new File(['img'], 'photo.png', { type: 'image/png' });
    transport.upload.mockResolvedValueOnce({
      attachment: { id: 'image', name: file.name, mimeType: file.type, size: file.size },
    });
    drop([file]);
    await waitFor(() => expect(screen.getByRole('list', { name: 'Attached files' })).toBeVisible());
    expect(transport.upload).toHaveBeenCalledWith('chat/a', file);
    expect(screen.getByLabelText('Upload file').getAttribute('accept')).toContain('image/*');
    store.dispose();
  });

  it('preserves failed-send drafts and labels queued followups without claiming in-run steering', async () => {
    const { transport, store, streams } = await setup();
    const { event } = await import('./fixtures');
    act(() => {
      streams[0].callbacks.event(event(1, 'state', { status: 'running' }));
    });
    expect(screen.getByRole('button', { name: 'Stop all' })).toHaveAttribute(
      'title',
      'Stop active and queued turns',
    );
    expect(
      screen.getByText(
        'New messages queue for the next turn. Stop cancels active and queued turns.',
      ),
    ).toBeVisible();
    const pending = deferred<{ runId: string }>();
    transport.send.mockReturnValueOnce(pending.promise);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Next turn' } });
    const button = screen.getByRole('button', { name: 'Queue message for next turn' });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(transport.send).toHaveBeenCalledOnce();
    await act(async () => {
      pending.reject(new Error('Queue full'));
    });
    expect(screen.getByRole('textbox')).toHaveValue('Next turn');
    expect(screen.getByRole('button', { name: 'Queue message for next turn' })).toBeEnabled();
    store.dispose();
  });
});
