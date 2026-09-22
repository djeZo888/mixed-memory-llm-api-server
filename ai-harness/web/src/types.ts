export const CONTEXT_LIMIT = 480_000;
export const statuses = [
  'idle',
  'queued',
  'running',
  'compacting',
  'cancelling',
  'interrupted',
  'failed',
  'deleting',
] as const;
export type Status = (typeof statuses)[number];
export interface Context {
  used: number | null;
  limit: 480000;
  estimated: boolean;
  stale: boolean;
  updatedAt: string;
  source?: string;
}
export interface Session {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  status: Status;
  context?: Context;
}
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  runId?: string;
  attachmentIds?: string[];
}
export interface Attachment {
  id: string;
  name: string;
  mimeType: string;
  size: number;
}
export interface Artifact extends Attachment {
  downloadUrl: string;
}
type EventData = {
  message: { message: Message };
  assistant_delta: { messageId: string; text: string };
  progress: { kind: string; label: string; detail?: string; taskId?: string };
  context: { context: Context };
  state: { status: Status };
  artifact: { artifact: Artifact };
  error: { code: string; message: string };
  done: { runId: string };
  handoff: { newSessionId: string };
};
export type EventType = keyof EventData;
export type ServerEvent = {
  [K in EventType]: {
    id: number;
    type: K;
    sessionId: string;
    runId?: string;
    createdAt: string;
    data: EventData[K];
  };
}[EventType];
export const eventTypes: EventType[] = [
  'message',
  'assistant_delta',
  'progress',
  'context',
  'state',
  'artifact',
  'error',
  'done',
  'handoff',
];
export interface Snapshot {
  session: Session;
  messages: Message[];
  events: ServerEvent[];
  artifacts: Artifact[];
}
export interface Activity {
  id: number;
  createdAt: string;
  kind: string;
  label: string;
  detail?: string;
}
export interface Thread {
  session: Session;
  messages: Message[];
  artifacts: Artifact[];
  activity: Activity[];
  lastEventId: number;
  error: string | null;
}
export const isActive = (status?: Status) =>
  !!status && ['queued', 'running', 'compacting', 'cancelling'].includes(status);
