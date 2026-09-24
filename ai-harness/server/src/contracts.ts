export const CONTEXT_LIMIT = 480000 as const;
export const MAX_OUTPUT = 65536 as const;
export const MODEL = "qwen3.8-27b";
export type Status =
  | "idle"
  | "queued"
  | "running"
  | "compacting"
  | "cancelling"
  | "interrupted"
  | "failed"
  | "deleting";
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
export type MessageChannel = "thought" | "commentary" | "final" | "unknown";
export interface MessagePhase {
  phase: "intermediate" | "thinking" | "final" | "unclassified";
  nativeMessageId?: string;
  nativeTurnId?: string;
  streamState?: "streaming" | "completed";
}
export interface Message extends Partial<MessagePhase> {
  attachments?: Attachment[];
  zipUrl?: string;
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  runId?: string;
  attachmentIds?: string[];
  imageReferences?: string[];
}
export interface Attachment {
  downloadUrl?: string;
  previewUrl?: string;
  id: string;
  name: string;
  mimeType: string;
  size: number;
}
export interface Artifact extends Attachment {
  /** Exact server-attested references; resolved to the immutable artifact, never read as paths. */
  referencePaths?: string[];
  image?: import("./image-contracts.js").ImageMetadata;
  runId: string | null;
  messageId: string | null;
  previewUrl?: string;
  downloadUrl: string;
}
export interface Event {
  id: number;
  type: string;
  sessionId: string;
  runId?: string;
  createdAt: string;
  data: Record<string, unknown>;
}
export interface SubagentSummary {
  known: boolean;
  active: number | null;
  completed: number | null;
  failed: number | null;
  cancelled: number | null;
  updatedAt?: string;
}
export const unknownSubagents = (): SubagentSummary => ({
  known: false,
  active: null,
  completed: null,
  failed: null,
  cancelled: null,
});
export interface Activity {
  id: string;
  runId: string;
  kind: "tool" | "subagent";
  name: string;
  status:
    | "pending"
    | "in_progress"
    | "completed"
    | "failed"
    | "cancelled"
    | "unknown";
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
export interface RunSnapshot {
  id: string;
  kind: "message" | "handoff";
  status:
    | "queued"
    | "running"
    | "cancelling"
    | "completed"
    | "cancelled"
    | "interrupted"
    | "failed";
  createdAt: string;
  updatedAt: string;
  finalMessageId?: string | null;
  artifactIds: string[];
  attachmentIds?: string[];
  filesZipUrl?: string;
  zipUrl?: string;
  subagents: SubagentSummary;
}
export interface Environment {
  timeZone: "Europe/Ljubljana";
  location: { city: "Ljubljana"; country: "Slovenia" };
  now: string;
}
export type EngineUpdate =
  | {
      type: "text";
      text: string;
      nativeMessageId?: string;
      channel?: MessageChannel;
      phaseSource?: string;
    }
  | {
      type: "phase";
      nativeMessageId: string;
      channel: "commentary" | "final" | "unknown";
      phaseSource: string;
      nativeTurnId?: string;
      streamState?: "streaming" | "completed";
    }
  | {
      type: "progress";
      kind: string;
      label: string;
      detail?: string;
      taskId?: string;
      toolActivityId?: string;
      toolCallId?: string;
      name?: string;
      command?: string;
      url?: string;
      status?: string;
      startedAt?: string;
      updatedAt?: string;
      completedAt?: string;
      subagentId?: string;
      parentSessionId?: string;
      backgroundTaskId?: string;
      subagents?: SubagentSummary;
    }
  | {
      type: "compaction";
      compactionId: string;
      status: "start" | "completed" | "failed";
      tokensBefore?: number;
      tokensAfter?: number;
    }
  | { type: "context"; used: number | null; estimated: boolean; source: string }
  | { type: "artifact"; path: string; name?: string; mimeType?: string };
export interface EngineOptions {
  sessionId: string;
  profileDir: string;
  workspace: string;
  nativeSessionId?: string;
  launcher: string;
  gatewayUrl: string;
  gatewayToken: string;
  stderrPath: string;
  shutdownTimeouts?: { acpMs?: number; launcherMs?: number; killMs?: number };
  onExit?: () => void;
  onNativeSessionId: (id: string) => void;
  onUpdate: (update: EngineUpdate) => void;
}
export interface Engine {
  start(): Promise<void>;
  prompt(
    text: string,
    attachments?: { path: string; mimeType: string; name: string }[],
  ): Promise<void | "completed" | "cancelled">;
  cancel(): Promise<void>;
  close(): Promise<void>;
}
export type EngineFactory = (options: EngineOptions) => Engine;
export interface GatewayUsage {
  sessionId: string;
  promptTokens: number;
  completionTokens?: number;
  source: string;
}

export type {
  ImageJob,
  ImageState,
  ImageReference,
  ImageAdjustment,
  ImageMetadata,
} from "./image-contracts.js";
