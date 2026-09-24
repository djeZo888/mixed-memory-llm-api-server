import type { ActivityItem, Artifact, ImageJob, Message, Thread } from './types';

export interface Reply {
  key: string;
  runId?: string;
  messages: Message[];
  activity: ActivityItem[];
  artifacts: Artifact[];
  imageJobs: ImageJob[];
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
  const runTimes = new Map(thread.runs.map((run) => [run.id, Date.parse(run.createdAt)]));
  const replyTimes = new Map<Reply, number>();
  const unassociated: Replies['unassociated'] = { activity: [], artifacts: [] };
  const create = (
    key: string,
    runId: string | undefined,
    createdAt: string,
    index = items.length,
  ) => {
    const reply: Reply = { key, runId, messages: [], activity: [], artifacts: [], imageJobs: [] };
    items.splice(index, 0, { kind: 'reply', reply });
    replyTimes.set(reply, (runId ? runTimes.get(runId) : undefined) ?? Date.parse(createdAt));
    if (runId) byRun.set(runId, reply);
    return reply;
  };
  for (const message of thread.messages) {
    if (message.role === 'user') {
      items.push({ kind: 'user', message });
      // Reserve the reply immediately after its own request, even if a queued
      // follow-up is persisted before the current response finishes streaming.
      if (message.runId && !byRun.has(message.runId))
        create(`run:${message.runId}`, message.runId, message.createdAt);
      continue;
    }
    const reply =
      (message.runId ? byRun.get(message.runId) : undefined) ??
      create(
        message.runId ? `run:${message.runId}` : `message:${message.id}`,
        message.runId,
        message.createdAt,
      );
    reply.messages.push(message);
    byMessage.set(message.id, reply);
  }
  // Insert runs with no message at their creation time, without reordering the
  // existing user/reply pairs by a late assistant's streaming timestamp.
  const itemTime = (item: ConversationItem) =>
    item.kind === 'user'
      ? ((item.message.runId ? runTimes.get(item.message.runId) : undefined) ??
        Date.parse(item.message.createdAt))
      : replyTimes.get(item.reply)!;
  const orphanRuns = thread.runs
    .filter((run) => !byRun.has(run.id))
    .sort((a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt));
  for (const run of orphanRuns) {
    if (byRun.has(run.id)) continue;
    const at = Date.parse(run.createdAt);
    const before = items.findIndex((item) => itemTime(item) > at);
    create(`run:${run.id}`, run.id, run.createdAt, before < 0 ? items.length : before);
  }
  for (const job of thread.imageJobs ?? []) {
    if (job.sessionId !== thread.session.id) continue;
    let reply = byRun.get(job.runId);
    if (!reply) {
      const before = items.findIndex((item) => itemTime(item) > Date.parse(job.createdAt));
      reply = create(
        `run:${job.runId}`,
        job.runId,
        job.createdAt,
        before < 0 ? items.length : before,
      );
    }
    reply.imageJobs.push(job);
  }
  const memberships = new Map<string, Set<Reply>>();
  for (const run of thread.runs) {
    const reply = byRun.get(run.id)!;
    for (const id of run.artifactIds) {
      const owners = memberships.get(id) ?? new Set<Reply>();
      owners.add(reply);
      memberships.set(id, owners);
    }
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
  const addArtifact = (artifacts: Artifact[], artifact: Artifact) => {
    if (!artifacts.some((existing) => existing.id === artifact.id)) artifacts.push(artifact);
  };
  for (const artifact of thread.artifacts) {
    const proven = memberships.get(artifact.id);
    if (proven?.size) {
      for (const reply of proven) addArtifact(reply.artifacts, artifact);
      // Membership is authoritative, but do not silently discard contradictory
      // or unresolved scalar claims. Preserve those in the existing unknown-
      // association section, without assigning the file to an unproven reply.
      const runClaim = artifact.runId ? byRun.get(artifact.runId) : undefined;
      const messageClaim = artifact.messageId ? byMessage.get(artifact.messageId) : undefined;
      if (
        (artifact.runId && (!runClaim || !proven.has(runClaim))) ||
        (artifact.messageId && (!messageClaim || !proven.has(messageClaim)))
      )
        addArtifact(unassociated.artifacts, artifact);
    } else {
      addArtifact(owner(artifact)?.artifacts ?? unassociated.artifacts, artifact);
    }
  }
  return { items, unassociated };
}
