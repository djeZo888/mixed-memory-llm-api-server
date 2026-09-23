import { mergeImageJobs } from './image-jobs';
import type {
  Activity,
  ActivityItem,
  Artifact,
  ImageJob,
  Message,
  RunSnapshot,
  ServerEvent,
  Snapshot,
  Summary,
  Thread,
} from './types';

export const DETAIL_LIMIT = 6000;
// Presentation page size only. Never discard old reply activity from the store.
export const ACTIVITY_LIMIT = 100;
const defined = <T extends object>(value: T): T =>
  Object.fromEntries(Object.entries(value).filter(([, entry]) => entry !== undefined)) as T;
const upsert = <T extends { id: string }>(items: T[], item: T): T[] => {
  const index = items.findIndex((entry) => entry.id === item.id);
  return index < 0
    ? [...items, item]
    : items.map((entry, i) => (i === index ? { ...entry, ...defined(item) } : entry));
};
const normalizeActivity = (activity: Activity): ActivityItem =>
  defined({
    ...activity,
    label: activity.summary ?? activity.name,
    createdAt: activity.startedAt ?? activity.updatedAt,
    detail: activity.detail?.slice(0, DETAIL_LIMIT),
    legacy: false,
  });
const mergeActivity = (current: ActivityItem, incoming: ActivityItem): ActivityItem => {
  // Both collections carry emitted timestamps. A stale snapshot projection must
  // not roll a newer lifecycle status backwards; equal/invalid times retain
  // normal event order and canonical snapshot precedence.
  const older = Date.parse(incoming.updatedAt) < Date.parse(current.updatedAt);
  const merged = older
    ? { ...defined(incoming), ...current }
    : { ...current, ...defined(incoming) };
  return {
    ...merged,
    label: merged.summary ?? merged.name,
    createdAt: merged.startedAt ?? current.createdAt,
  };
};
const upsertActivity = (items: ActivityItem[], item: ActivityItem): ActivityItem[] => {
  const index = items.findIndex(
    (entry) => entry.id === item.id && entry.runId === item.runId && entry.legacy === item.legacy,
  );
  if (index < 0) return [...items, item];
  return items.map((entry, i) => (i === index ? mergeActivity(entry, item) : entry));
};
const activityFrom = (event: ServerEvent): ActivityItem | null => {
  if (event.type === 'activity') return normalizeActivity(event.data.activity);
  if (event.type === 'progress')
    return defined({
      id: `event:${event.id}`,
      createdAt: event.createdAt,
      updatedAt: event.createdAt,
      runId: event.runId,
      kind: event.data.kind.slice(0, 80),
      name: event.data.label.slice(0, 300),
      label: event.data.label.slice(0, 300),
      detail: event.data.detail?.slice(0, DETAIL_LIMIT),
      taskId: event.data.taskId,
      legacy: true,
    });
  if (event.type === 'error')
    return defined({
      id: `event:${event.id}`,
      createdAt: event.createdAt,
      updatedAt: event.createdAt,
      runId: event.runId,
      kind: 'error',
      name: event.data.message.slice(0, 300),
      label: event.data.message.slice(0, 300),
      legacy: true,
    });
  return null;
};
const messageFrom = (event: Extract<ServerEvent, { type: 'message' }>): Message => ({
  ...event.data.message,
  ...(event.data.message.runId === undefined && event.runId ? { runId: event.runId } : {}),
});
const artifactFrom = (event: Extract<ServerEvent, { type: 'artifact' }>): Artifact => ({
  ...event.data.artifact,
  ...(event.data.artifact.runId == null && event.runId ? { runId: event.runId } : {}),
});
const deltaMetadata = (
  event: Extract<ServerEvent, { type: 'assistant_delta' }>,
): Partial<Message> =>
  defined({
    runId: event.runId,
    phase: event.data.phase,
    nativeMessageId: event.data.nativeMessageId,
    nativeTurnId: event.data.nativeTurnId,
  });

export function applyEvent(thread: Thread, event: ServerEvent): Thread {
  if (event.sessionId !== thread.session.id || event.id <= thread.lastEventId) return thread;
  if (
    event.type === 'image_job' &&
    (event.data.job.sessionId !== thread.session.id ||
      (event.runId !== undefined && event.runId !== event.data.job.runId))
  )
    return thread;
  let next: Thread = { ...thread, lastEventId: event.id };
  switch (event.type) {
    case 'message':
      next.messages = upsert(next.messages, messageFrom(event));
      break;
    case 'assistant_delta': {
      const existing = next.messages.find((message) => message.id === event.data.messageId);
      const message: Message = existing ?? {
        id: event.data.messageId,
        role: 'assistant',
        content: '',
        createdAt: event.createdAt,
        streamState: 'streaming',
      };
      next.messages = upsert(next.messages, {
        ...message,
        ...deltaMetadata(event),
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
      next.artifacts = upsert(next.artifacts, artifactFrom(event));
      break;
    case 'image_job':
      next.imageJobs = mergeImageJobs(
        next.imageJobs ?? [],
        [event.data.job],
        thread.session.id,
        true,
      );
      break;
    case 'run': {
      const run = event.data.run;
      next.runs = upsert(next.runs, run);
      next.subagentsByRun = Object.assign(Object.create(null), next.subagentsByRun, {
        [run.id]: run.subagents,
      });
      break;
    }
    case 'subagents':
      next.subagentsByRun = Object.assign(Object.create(null), next.subagentsByRun, {
        [event.data.runId]: event.data.summary,
      });
      next.runs = next.runs.map((run) =>
        run.id === event.data.runId ? { ...run, subagents: event.data.summary } : run,
      );
      break;
    case 'error':
      next.error = event.data.message;
      break;
  }
  const activity = activityFrom(event);
  if (activity) next = { ...next, activity: upsertActivity(next.activity, activity) };
  return next;
}

// GET messages are canonical at the highest returned event ID. Never append
// snapshot deltas to those messages: only replay events beyond that watermark.
export function reconcileSnapshot(snapshot: Snapshot, inFlight: ServerEvent[] = []): Thread {
  const events = snapshot.events
    .filter((event) => event.sessionId === snapshot.session.id)
    .sort((a, b) => a.id - b.id)
    .filter((event, index, sorted) => index === 0 || event.id !== sorted[index - 1].id);
  const messageMetadata = new Map<string, Partial<Message>>();
  const artifactMetadata = new Map<string, Artifact>();
  let runs: RunSnapshot[] = [];
  let imageJobs: ImageJob[] = [];
  let activity: ActivityItem[] = [];
  const subagentsByRun: Record<string, Summary> = Object.create(null);
  for (const event of events) {
    if (event.type === 'message') {
      const message = messageFrom(event);
      messageMetadata.set(message.id, { ...messageMetadata.get(message.id), ...message });
    } else if (event.type === 'assistant_delta') {
      messageMetadata.set(event.data.messageId, {
        ...messageMetadata.get(event.data.messageId),
        ...deltaMetadata(event),
      });
    } else if (event.type === 'artifact') {
      const artifact = artifactFrom(event);
      artifactMetadata.set(artifact.id, { ...artifactMetadata.get(artifact.id), ...artifact });
    } else if (
      event.type === 'image_job' &&
      (event.runId === undefined || event.runId === event.data.job.runId)
    ) {
      imageJobs = mergeImageJobs(imageJobs, [event.data.job], snapshot.session.id, true);
    } else if (event.type === 'run') {
      runs = upsert(runs, event.data.run);
      subagentsByRun[event.data.run.id] = event.data.run.subagents;
    } else if (event.type === 'subagents') {
      subagentsByRun[event.data.runId] = event.data.summary;
    }
    const item = activityFrom(event);
    if (item) activity = upsertActivity(activity, item);
  }
  // Canonical snapshot collections win over historical events at equal emitted
  // times. Legacy omitted collections recover exact identities from their log.
  for (const run of snapshot.runs ?? []) {
    runs = upsert(runs, run);
    subagentsByRun[run.id] = run.subagents;
  }
  runs = runs.map((run) => ({ ...run, subagents: subagentsByRun[run.id] ?? run.subagents }));
  for (const item of snapshot.activities ?? [])
    activity = upsertActivity(activity, normalizeActivity(item));
  const lastEventId = events.reduce((max, event) => Math.max(max, event.id), 0);
  let thread: Thread = {
    session: snapshot.session,
    // Only enrich exact canonical IDs. An old unassociated row stays unassociated.
    messages: snapshot.messages.map((message) => ({
      ...messageMetadata.get(message.id),
      ...defined(message),
    })),
    artifacts: snapshot.artifacts.map((artifact) => {
      const metadata = artifactMetadata.get(artifact.id);
      return {
        ...metadata,
        ...artifact,
        ...(artifact.runId == null && metadata?.runId ? { runId: metadata.runId } : {}),
        ...(artifact.messageId == null && metadata?.messageId
          ? { messageId: metadata.messageId }
          : {}),
      };
    }),
    runs,
    imageJobs: mergeImageJobs(imageJobs, snapshot.imageJobs ?? [], snapshot.session.id),
    attachments: snapshot.attachments ?? [],
    subagentsByRun,
    environment: snapshot.environment,
    activity,
    lastEventId,
    error: events.filter((event) => event.type === 'error').at(-1)?.data.message ?? null,
  };
  for (const event of [...inFlight].sort((a, b) => a.id - b.id)) thread = applyEvent(thread, event);
  return thread;
}
