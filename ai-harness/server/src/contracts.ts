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
export interface Message {
  id: string;
  role: "user" | "assistant";
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
export interface Event {
  id: number;
  type: string;
  sessionId: string;
  runId?: string;
  createdAt: string;
  data: Record<string, unknown>;
}
export type EngineUpdate =
  | { type: "text"; text: string }
  | {
      type: "progress";
      kind: string;
      label: string;
      detail?: string;
      taskId?: string;
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
