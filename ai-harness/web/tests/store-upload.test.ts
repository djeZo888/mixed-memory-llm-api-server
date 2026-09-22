import { waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HarnessStore, busyKey } from '../src/store';
import { deferred, fixtureTransport } from './fixtures';

async function ready() {
  const fixture = fixtureTransport();
  const store = new HarnessStore(fixture.transport);
  await store.start();
  await waitFor(() => expect(store.getSnapshot().thread).not.toBeNull());
  return { ...fixture, store };
}
const file = (name: string) => new File([name], name, { type: 'text/plain', lastModified: 1 });
const result = (id: string) => ({
  attachment: { id, name: `${id}.txt`, size: 5, mimeType: 'text/plain' },
});

describe('upload batch lifecycle', () => {
  it('holds the upload lock across requests and sends only the completed selection', async () => {
    const { store, transport } = await ready();
    const first = deferred<Awaited<ReturnType<typeof transport.upload>>>();
    const second = deferred<Awaited<ReturnType<typeof transport.upload>>>();
    transport.upload.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const files = [file('one.txt'), file('two.txt')];
    const update = vi.fn();
    const uploading = store.uploadBatch('chat/a', files, update);
    expect(store.getSnapshot().busy[busyKey('upload', 'chat/a')]).toBe(true);
    expect(await store.send('chat/a', 'Read both')).toBe(false);
    expect(await store.uploadBatch('chat/a', files)).toBe(false);
    first.resolve(result('one'));
    await waitFor(() => expect(transport.upload).toHaveBeenCalledTimes(2));
    expect(store.getSnapshot().busy[busyKey('upload', 'chat/a')]).toBe(true);
    expect(await store.send('chat/a', 'Read both')).toBe(false);
    second.resolve(result('two'));
    expect(await uploading).toBe(true);
    expect(store.getSnapshot().busy[busyKey('upload', 'chat/a')]).toBe(false);
    expect(store.getSnapshot().thread?.attachments.map((a) => a.id)).toEqual(['one', 'two']);
    expect(update.mock.calls.map(([u]) => u.status)).toEqual([
      'uploading',
      'ready',
      'uploading',
      'ready',
    ]);
    await store.send('chat/a', 'Read both');
    expect(transport.send).toHaveBeenCalledWith('chat/a', 'Read both', ['one', 'two']);
    store.dispose();
  });

  it('de-duplicates selected files while attached and permits reattachment after removal', async () => {
    const { store, transport } = await ready();
    const one = file('one.txt');
    transport.upload.mockResolvedValue(result('one'));
    await store.uploadBatch('chat/a', [one, one, file('one.txt')]);
    await store.uploadBatch('chat/a', [file('one.txt')]);
    expect(transport.upload).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot().attachments['chat/a']).toHaveLength(1);
    store.removeAttachment('chat/a', 'one');
    await store.upload('chat/a', one);
    expect(transport.upload).toHaveBeenCalledTimes(2);
    expect(store.getSnapshot().attachments['chat/a']).toHaveLength(1);
    store.dispose();
  });

  it('keeps successful files and reports failed files without aborting the batch', async () => {
    const { store, transport } = await ready();
    const update = vi.fn();
    transport.upload
      .mockRejectedValueOnce(new Error('Upload unavailable'))
      .mockResolvedValueOnce(result('two'));
    const success = await store.uploadBatch('chat/a', [file('one.txt'), file('two.txt')], update);
    expect(success).toBe(false);
    expect(store.getSnapshot().attachments['chat/a'].map((a) => a.id)).toEqual(['two']);
    expect(update.mock.calls.map(([u]) => [u.file.name, u.status])).toEqual([
      ['one.txt', 'uploading'],
      ['one.txt', 'error'],
      ['two.txt', 'uploading'],
      ['two.txt', 'ready'],
    ]);
    expect(store.getSnapshot().error).toBe('Upload unavailable');
    transport.upload.mockResolvedValueOnce(result('one'));
    expect(await store.upload('chat/a', file('one.txt'))).toBe(true);
    expect(store.getSnapshot().attachments['chat/a'].map((a) => a.id)).toEqual(['two', 'one']);
    store.dispose();
  });

  it('does not lose or reassign uploads when switching chats during a batch', async () => {
    const { store, transport } = await ready();
    const first = deferred<Awaited<ReturnType<typeof transport.upload>>>();
    transport.upload.mockReturnValueOnce(first.promise).mockResolvedValueOnce(result('two'));
    const uploading = store.uploadBatch('chat/a', [file('one.txt'), file('two.txt')]);
    store.select('chat/b');
    first.resolve(result('one'));
    await uploading;
    expect(store.getSnapshot().selectedId).toBe('chat/b');
    expect(store.getSnapshot().attachments['chat/b']).toBeUndefined();
    expect(store.getSnapshot().attachments['chat/a'].map((a) => a.id)).toEqual(['one', 'two']);
    expect(transport.upload).toHaveBeenNthCalledWith(2, 'chat/a', expect.any(File));
    store.dispose();
  });

  it('rejects batch requests while a send is pending and leaves attachments stable', async () => {
    const { store, transport } = await ready();
    const response = deferred<{ runId: string }>();
    transport.send.mockReturnValueOnce(response.promise);
    const sending = store.send('chat/a', 'Sending');
    expect(await store.uploadBatch('chat/a', [file('one.txt')])).toBe(false);
    expect(transport.upload).not.toHaveBeenCalled();
    response.resolve({ runId: 'run/1' });
    await sending;
    store.dispose();
  });
});
