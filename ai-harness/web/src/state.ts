import type { Activity, Message, ServerEvent, Snapshot, Thread } from './types';

export const DETAIL_LIMIT = 6000;
export const ACTIVITY_LIMIT = 100;
const upsert = <T extends { id: string }>(items: T[], item: T): T[] => {
  const index = items.findIndex((entry) => entry.id === item.id);
  return index < 0 ? [...items, item] : items.map((entry, i) => (i === index ? item : entry));
};
const activityFrom = (event: ServerEvent): Activity | null => {
  if (event.type === 'progress')
    return {
      id: event.id,
      createdAt: event.createdAt,
      kind: event.data.kind.slice(0, 80),
      label: event.data.label.slice(0, 300),
      detail: event.data.detail?.slice(0, DETAIL_LIMIT),
    };
  if (event.type === 'error')
    return {
      id: event.id,
      createdAt: event.createdAt,
      kind: 'error',
      label: event.data.message.slice(0, 300),
    };
  return null;
};
export function applyEvent(thread: Thread, event: ServerEvent): Thread {
  if (event.sessionId !== thread.session.id || event.id <= thread.lastEventId) return thread;
  let next: Thread = { ...thread, lastEventId: event.id };
  switch (event.type) {
    case 'message':
      next.messages = upsert(next.messages, event.data.message);
      break;
    case 'assistant_delta': {
      const existing = next.messages.find((m) => m.id === event.data.messageId);
      const message: Message = existing ?? {
        id: event.data.messageId,
        role: 'assistant',
        content: '',
        createdAt: event.createdAt,
        runId: event.runId,
      };
      next.messages = upsert(next.messages, {
        ...message,
        content: message.content + event.data.text,
      });
      break;
    }
    case 'context':
      next.session = { ...next.session, context: event.data.context };
      break;
    case 'state':
      next.session = { ...next.session, status: event.data.status };
      break;
    case 'artifact':
      next.artifacts = upsert(next.artifacts, event.data.artifact);
      break;
    case 'error':
      next.error = event.data.message;
      break;
  }
  const activity = activityFrom(event);
  if (activity) next = { ...next, activity: [...next.activity, activity].slice(-ACTIVITY_LIMIT) };
  return next;
}

// GET messages are canonical at the highest returned event ID. Never append
// snapshot deltas to those messages: only replay events beyond that watermark.
export function reconcileSnapshot(snapshot: Snapshot, inFlight: ServerEvent[] = []): Thread {
  const events = snapshot.events
    .filter((e) => e.sessionId === snapshot.session.id)
    .sort((a, b) => a.id - b.id);
  const lastEventId = events.reduce((max, event) => Math.max(max, event.id), 0);
  let thread: Thread = {
    session: snapshot.session,
    messages: snapshot.messages,
    artifacts: snapshot.artifacts,
    activity: events
      .map(activityFrom)
      .filter((entry): entry is Activity => entry !== null)
      .slice(-ACTIVITY_LIMIT),
    lastEventId,
    error: events.filter((event) => event.type === 'error').at(-1)?.data.message ?? null,
  };
  for (const event of [...inFlight].sort((a, b) => a.id - b.id)) thread = applyEvent(thread, event);
  return thread;
}
