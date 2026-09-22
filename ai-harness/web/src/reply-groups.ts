import type { ActivityItem, Artifact, Message, Thread } from './types';

export interface Reply {
  key: string;
  runId?: string;
  messages: Message[];
  activity: ActivityItem[];
  artifacts: Artifact[];
}
export type ConversationItem = { kind: 'user'; message: Message } | { kind: 'reply'; reply: Reply };
export interface Replies {
  items: ConversationItem[];
  unassociated: { activity: ActivityItem[]; artifacts: Artifact[] };
}

// Only server IDs associate records. Position, labels, filenames and prose never
// determine ownership, and conflicting/unknown metadata stays visible separately.
export function groupReplies(thread: Thread): Replies {
  const items: ConversationItem[] = [];
  const byRun = new Map<string, Reply>();
  const byMessage = new Map<string, Reply>();
  const unassociated: Replies['unassociated'] = { activity: [], artifacts: [] };
  const create = (key: string, runId?: string) => {
    const reply: Reply = { key, runId, messages: [], activity: [], artifacts: [] };
    items.push({ kind: 'reply', reply });
    if (runId) byRun.set(runId, reply);
    return reply;
  };
  for (const message of thread.messages) {
    if (message.role === 'user') {
      items.push({ kind: 'user', message });
      // Reserve the reply immediately after its own request, even if a queued
      // follow-up is persisted before the current response finishes streaming.
      if (message.runId && !byRun.has(message.runId)) create(`run:${message.runId}`, message.runId);
      continue;
    }
    const reply =
      (message.runId ? byRun.get(message.runId) : undefined) ??
      create(message.runId ? `run:${message.runId}` : `message:${message.id}`, message.runId);
    reply.messages.push(message);
    byMessage.set(message.id, reply);
  }
  const owner = (record: {
    runId?: string | null;
    messageId?: string | null;
  }): Reply | undefined => {
    if (record.messageId) {
      const reply = byMessage.get(record.messageId);
      return reply && (!record.runId || !reply.runId || record.runId === reply.runId)
        ? reply
        : undefined;
    }
    return record.runId ? byRun.get(record.runId) : undefined;
  };
  for (const activity of thread.activity)
    (owner(activity)?.activity ?? unassociated.activity).push(activity);
  for (const artifact of thread.artifacts)
    (owner(artifact)?.artifacts ?? unassociated.artifacts).push(artifact);
  return { items, unassociated };
}
