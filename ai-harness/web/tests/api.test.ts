import { describe, expect, it, vi } from 'vitest';
import { api, ApiError, artifactPath, sessionPath, subscribe } from '../src/api';
import { event } from './fixtures';
describe('contract transport', () => {
  it('accepts named frames and ordinary envelopes, rejects malformed/wrong-session events, and closes only the subscription', () => {
    class Source extends EventTarget {
      static current: Source;
      onopen?: () => void;
      onerror?: (event: Event) => void;
      close = vi.fn();
      constructor(public url: string) {
        super();
        Source.current = this;
      }
    }
    vi.stubGlobal('EventSource', Source);
    const callbacks = { event: vi.fn(), open: vi.fn(), disconnected: vi.fn() };
    const close = subscribe('chat/a', 42, callbacks);
    const source = Source.current;
    expect(source.url).toBe('/api/sessions/chat%2Fa/events?after=42');
    source.dispatchEvent(
      new MessageEvent('assistant_delta', {
        data: JSON.stringify(event(43, 'assistant_delta', { messageId: 'm', text: 'a' })),
      }),
    );
    source.dispatchEvent(
      new MessageEvent('message', {
        data: JSON.stringify(event(44, 'assistant_delta', { messageId: 'm', text: 'b' })),
      }),
    );
    source.dispatchEvent(new MessageEvent('message', { data: 'invalid' }));
    source.dispatchEvent(
      new MessageEvent('message', {
        data: JSON.stringify(event(45, 'done', { runId: 'r' }, 'wrong')),
      }),
    );
    source.dispatchEvent(
      new MessageEvent('error', {
        data: JSON.stringify(event(46, 'error', { code: 'failed', message: 'Failed' })),
      }),
    );
    source.onerror?.(new MessageEvent('error', { data: '{}' }));
    expect(callbacks.disconnected).not.toHaveBeenCalled();
    source.onerror?.(new Event('error'));
    expect(callbacks.disconnected).toHaveBeenCalledOnce();
    source.onopen?.();
    expect(callbacks.open).toHaveBeenCalledOnce();
    expect(callbacks.event).toHaveBeenCalledTimes(3);
    close();
    expect(source.close).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });
  it('omits Content-Type for bodyless DELETE and retains it for JSON POST', async () => {
    const fetcher = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: 'deleting' }), { status: 202 }),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'cancelling' })));

    await expect(api.remove('owned-chat')).resolves.toEqual({ status: 'deleting' });
    const [deletePath, deleteOptions] = fetcher.mock.calls[0];
    expect(deletePath).toBe('/api/sessions/owned-chat');
    expect(deleteOptions?.method).toBe('DELETE');
    expect(deleteOptions?.body).toBeUndefined();
    expect(new Headers(deleteOptions?.headers).has('Content-Type')).toBe(false);

    await expect(api.cancel('owned-chat')).resolves.toEqual({ status: 'cancelling' });
    const [cancelPath, cancelOptions] = fetcher.mock.calls[1];
    expect(cancelPath).toBe('/api/sessions/owned-chat/cancel');
    expect(cancelOptions?.method).toBe('POST');
    expect(cancelOptions?.body).toBe('{}');
    expect(new Headers(cancelOptions?.headers).get('Content-Type')).toBe('application/json');
  });
  it('encodes opaque paths, sends one multipart file field and surfaces structured API errors', async () => {
    expect(sessionPath('opaque/space ?#')).toBe('/api/sessions/opaque%2Fspace%20%3F%23');
    expect(artifactPath('//external/?')).toBe('/api/artifacts/%2F%2Fexternal%2F%3F/download');
    const fetcher = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ attachment: { id: 'f' } }), { status: 201 }),
      );
    const file = new File(['content'], 'notes.txt', { type: 'text/plain' });
    await api.upload('a/b', file);
    const [path, options] = fetcher.mock.calls[0];
    expect(path).toBe('/api/sessions/a%2Fb/uploads');
    expect(new Headers(options?.headers).has('Content-Type')).toBe(false);
    const form = options?.body as FormData;
    expect([...form.keys()]).toEqual(['file']);
    expect((form.get('file') as File).name).toBe('notes.txt');
    fetcher.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ error: { code: 'busy', message: 'Please wait for cancellation.' } }),
        { status: 409 },
      ),
    );
    await expect(api.send('a/b', 'Hello', [])).rejects.toEqual(
      new ApiError(409, 'busy', 'Please wait for cancellation.'),
    );
  });
});
