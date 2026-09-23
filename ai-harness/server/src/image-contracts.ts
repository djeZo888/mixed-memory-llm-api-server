/** Public image records: never include encoded pixels, credentials or host paths. */
export type ImageState =
  | "awaiting_approval"
  | "queued"
  | "running"
  | "saving"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";
export interface ImageReference {
  referenceId: string;
  fileId?: string;
  name: string;
  sha256: string;
  width: number;
  height: number;
}
export interface FrozenImageReference extends ImageReference {
  normalizedSha256: string;
  originalWidth: number;
  originalHeight: number;
  orientation: number;
  colour: string;
}
export interface ImageAdjustment {
  sources: (ImageReference & {
    workingWidth: number;
    workingHeight: number;
    padding: { left: number; top: number; right: number; bottom: number };
  })[];
  targetSize: string;
  reason: string;
}
export interface ImageJob {
  revision: number;
  id: string;
  sessionId: string;
  runId: string;
  requestId: string;
  operation: "generation" | "edit";
  state: ImageState;
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
  outputPath?: string;
  error?: { code: string; message: string };
  adjustment?: ImageAdjustment;
  cancelRequested: boolean;
}
export interface ImageMetadata {
  /** Present on new records; older actualSize-only records are hydrated on read. */
  width?: number;
  height?: number;
  jobId: string;
  actualSize: string;
  model: string;
  seed: number;
  sha256: string;
}
export interface ImageSubmission {
  requestId: string;
  operation: "generation" | "edit";
  prompt: string;
  size?: string;
  seed?: number;
  references?: ({ fileId: string } | { workspacePath: string })[];
}
/** Host-only adapter boundary. Profiles must come from reviewed upstream records. */
export interface ImageProfile {
  operation: ImageSubmission["operation"];
  referenceCount: number;
  size: string;
  model: string;
}
export interface ImageBackend {
  capabilities(signal: AbortSignal): Promise<unknown>;
  profiles(capabilities: unknown): ImageProfile[];
  readiness(signal: AbortSignal): Promise<{ ready: boolean; idle: boolean }>;
  execute(
    input: {
      operation: ImageSubmission["operation"];
      prompt: string;
      seed: number;
      size: string;
      model: string;
      references: Buffer[];
    },
    signal: AbortSignal,
  ): Promise<
    | { kind: "output"; png: Buffer; model: string; seed: number }
    | { kind: "not_admitted"; retryAfterMs: number }
  >;
}
