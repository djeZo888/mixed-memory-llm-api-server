import type {
  Activity,
  Artifact,
  Message,
  RunSnapshot,
  ServerEvent,
  Snapshot,
  Thread,
} from '../src/types';
import { reconcileSnapshot } from '../src/state';
import { createdAt, event, snapshot } from './fixtures';

export function replyMessage(
  id: string,
  role: Message['role'],
  content: string,
  additions: Partial<Message> = {},
): Message {
  return { id, role, content, createdAt, ...additions };
}

export function replyThread(additions: Partial<Snapshot> = {}): Thread {
  return reconcileSnapshot({ ...snapshot(), ...additions });
}

export function runEvent(
  id: number,
  type: ServerEvent['type'],
  data: unknown,
  runId: string,
): ServerEvent {
  return { ...event(id, type, data), runId };
}

export function replyRun(id: string, additions: Partial<RunSnapshot> = {}): RunSnapshot {
  return {
    id,
    kind: 'message',
    status: 'running',
    createdAt,
    updatedAt: createdAt,
    artifactIds: [],
    subagents: { known: false, active: null, completed: null, failed: null, cancelled: null },
    ...additions,
  };
}

export function replyArtifact(
  id: string,
  name: string,
  additions: Partial<Artifact> = {},
): Artifact {
  return {
    id,
    name,
    mimeType: 'text/plain',
    size: 128,
    downloadUrl: `/api/artifacts/${encodeURIComponent(id)}/download`,
    ...additions,
  };
}

export function replyActivity(id: string, additions: Partial<Activity> = {}): Activity {
  return {
    id,
    runId: 'run/one',
    kind: 'tool',
    name: 'exec_command',
    status: 'in_progress',
    updatedAt: createdAt,
    ...additions,
  };
}
