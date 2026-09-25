import { vi } from 'vitest';
import type { StreamCallbacks, Transport } from '../src/api';
import type { ServerEvent, Session, Snapshot } from '../src/types';
export const createdAt = '2026-09-22T12:00:00.000Z';
export const session = (id = 'chat/a'): Session => ({
  id,
  title: `Chat ${id}`,
  status: 'idle',
  createdAt,
  updatedAt: createdAt,
});
export const snapshot = (id = 'chat/a'): Snapshot => ({
  session: session(id),
  messages: [],
  events: [],
  artifacts: [],
});
export function event(
  id: number,
  type: ServerEvent['type'],
  data: unknown,
  sessionId = 'chat/a',
): ServerEvent {
  return { id, type, data, sessionId, createdAt } as ServerEvent;
}
export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
export function fixtureTransport() {
  const streams: {
    id: string;
    after: number;
    callbacks: StreamCallbacks;
    close: ReturnType<typeof vi.fn>;
  }[] = [];
  const transport = {
    imageCapabilities: vi.fn(async (): Promise<unknown> => ({ profiles: [] })),
    health: vi.fn<Transport['health']>(async () => ({ visionAvailable: false })),
    list: vi.fn(async () => ({ sessions: [session(), session('chat/b')] })),
    snapshot: vi.fn(async (id: string) => snapshot(id)),
    imageJobs: vi.fn(async () => ({ jobs: [] as import('../src/types').ImageJob[] })),
    approveImage: vi.fn<Transport['approveImage']>(),
    cancelImage: vi.fn<Transport['cancelImage']>(),
    create: vi.fn(async () => ({ session: session('new') })),
    remove: vi.fn(async () => ({ status: 'deleting' as const })),
    send: vi.fn(async () => ({ runId: 'run/1' })),
    cancel: vi.fn(async () => ({ status: 'cancelling' as const })),
    handoff: vi.fn(async () => ({ runId: 'handoff/1' })),
    upload: vi.fn(async () => ({
      attachment: { id: 'file/1', name: 'notes.txt', size: 10, mimeType: 'text/plain' },
    })),
    stream: vi.fn((id: string, after: number, callbacks: StreamCallbacks) => {
      const close = vi.fn();
      streams.push({ id, after, callbacks, close });
      return close;
    }),
  } satisfies Transport;
  return { transport, streams };
}
