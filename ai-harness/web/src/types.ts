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
export type MessagePhase = 'intermediate' | 'thinking' | 'final' | 'unclassified';
export type StreamState = 'streaming' | 'completed';
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  runId?: string;
  attachmentIds?: string[];
  imageReferences?: string[];
  phase?: MessagePhase;
  nativeMessageId?: string;
  nativeTurnId?: string;
  streamState?: StreamState;
}
export interface Attachment {
  id: string;
  name: string;
  mimeType: string;
  size: number;
  downloadUrl?: string;
  previewUrl?: string;
}
export interface Artifact extends Attachment {
  downloadUrl: string;
  runId?: string | null;
  messageId?: string | null;
  image?: {
    jobId?: string;
    operation?: ImageOperation;
    width?: number;
    height?: number;
    seed?: number;
    model?: string;
  };
}
export type ImageOperation = 'generation' | 'edit';
export type ImageJobState =
  | 'awaiting_approval'
  | 'queued'
  | 'running'
  | 'saving'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'interrupted';
export interface ImageReference {
  referenceId: string;
  fileId?: string;
  name: string;
  sha256: string;
  width: number;
  height: number;
}
export interface ImageAdjustmentSource extends ImageReference {
  workingWidth: number;
  workingHeight: number;
  padding: { top: number; right: number; bottom: number; left: number };
}
export interface ImageJob {
  id: string;
  revision: number;
  sessionId: string;
  runId: string;
  requestId: string;
  operation: ImageOperation;
  state: ImageJobState;
  model: string;
  prompt: string;
  seed: number;
  requestedSize: string;
  actualSize?: string;
  references: ImageReference[];
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
  elapsedMs?: number;
  queuePosition?: number;
  artifactId?: string;
  error?: { code: string; message: string };
  adjustment?: { sources: ImageAdjustmentSource[]; targetSize: string; reason: string };
  cancelRequested: boolean;
}
export interface Summary {
  known: boolean;
  active: number | null;
  completed: number | null;
  failed: number | null;
  cancelled: number | null;
  updatedAt?: string;
}
export type RunStatus =
  'queued' | 'running' | 'cancelling' | 'completed' | 'cancelled' | 'interrupted' | 'failed';
export interface RunSnapshot {
  id: string;
  kind: 'message' | 'handoff';
  status: RunStatus;
  createdAt: string;
  updatedAt: string;
  finalMessageId?: string | null;
  artifactIds: string[];
  zipUrl?: string;
  subagents: Summary;
}
export type ActivityStatus =
  'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled' | 'unknown';
export interface Activity {
  id: string;
  runId: string;
  kind: 'tool' | 'subagent';
  name: string;
  status: ActivityStatus;
  summary?: string;
  command?: string;
  url?: string;
  detail?: string;
  startedAt?: string;
  updatedAt: string;
  finishedAt?: string;
  toolCallId?: string;
  childSessionId?: string;
  parentSessionId?: string;
  backgroundTaskId?: string;
}
// Internal presentation record. Old progress/errors retain their event identity
// and unknown lifecycle fields; they never become invented tool or agent runs.
export interface ActivityItem extends Omit<Activity, 'kind' | 'runId' | 'status'> {
  kind: string;
  runId?: string;
  status?: ActivityStatus;
  label: string;
  createdAt: string;
  legacy: boolean;
  taskId?: string;
}
export interface Environment {
  timeZone: 'Europe/Ljubljana';
  location: { city: 'Ljubljana'; country: 'Slovenia' };
  now: string;
}
type EventData = {
  message: { message: Message };
  assistant_delta: {
    messageId: string;
    text: string;
    phase?: MessagePhase;
    nativeMessageId?: string;
    nativeTurnId?: string;
  };
  progress: { kind: string; label: string; detail?: string; taskId?: string };
  context: { context: Context };
  state: { status: Status };
  artifact: { artifact: Artifact };
  image_job: { job: ImageJob };
  run: { run: RunSnapshot };
  activity: { activity: Activity };
  subagents: { runId: string; summary: Summary };
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
  'image_job',
  'run',
  'activity',
  'subagents',
  'error',
  'done',
  'handoff',
];
export interface Snapshot {
  session: Session;
  messages: Message[];
  events: ServerEvent[];
  artifacts: Artifact[];
  imageJobs?: ImageJob[];
  runs?: RunSnapshot[];
  activities?: Activity[];
  attachments?: Attachment[];
  environment?: Environment;
}
export interface Thread {
  session: Session;
  messages: Message[];
  artifacts: Artifact[];
  imageJobs?: ImageJob[];
  activity: ActivityItem[];
  runs: RunSnapshot[];
  attachments: Attachment[];
  subagentsByRun: Record<string, Summary>;
  environment?: Environment;
  lastEventId: number;
  error: string | null;
}
export const isActive = (status?: Status) =>
  !!status && ['queued', 'running', 'compacting', 'cancelling'].includes(status);
