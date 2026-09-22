import type { Context, Thread } from './types';
// Only the server can establish untouched native history. An empty-source zero
// remains valid until a turn exists; it must not masquerade as current occupancy
// while that turn is waiting for its first estimate.
export function contextForThread(thread: Thread | null | undefined): Context | undefined {
  const context = thread?.session.context;
  if (
    context?.source === 'empty' &&
    thread &&
    (thread.messages.length > 0 ||
      thread.runs.length > 0 ||
      thread.activity.length > 0 ||
      thread.artifacts.length > 0 ||
      thread.session.status !== 'idle')
  )
    return { ...context, used: null, stale: true, source: 'awaiting_first_context' };
  return context;
}
