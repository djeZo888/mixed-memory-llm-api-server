/** Only the structured successful native MCP completion may attest consumption. */
export interface ImageStatusConsumption { toolCallId: string; jobId: string; artifactId: string }
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const id = (value: unknown): value is string => typeof value === "string" && /^[A-Za-z0-9_-]{1,80}$/.test(value);
export function completedImageStatus(value: Record<string, unknown>): ImageStatusConsumption | undefined {
  if (value.type !== "mcpToolCall" || value.server !== "image" || value.tool !== "image_status" ||
      value.status !== "completed" || value.error != null || !id(value.id) || !record(value.arguments) ||
      Object.keys(value.arguments).length !== 1 || !id(value.arguments.jobId) || !record(value.result) ||
      (value.result.isError !== undefined && value.result.isError !== false) || !Array.isArray(value.result.content) || value.result.content.length !== 1)
    return;
  const content = value.result.content[0];
  if (!record(content) || content.type !== "text" || typeof content.text !== "string" || content.text.length > 256 * 1024) return;
  let output: unknown;
  try { output = JSON.parse(content.text); } catch { return; }
  if (!record(output) || output.error != null || !record(output.job)) return;
  const job = output.job;
  if (job.id !== value.arguments.jobId || job.state !== "completed" || job.cancelRequested !== false || job.error != null || !id(job.artifactId)) return;
  return { toolCallId: value.id, jobId: value.arguments.jobId, artifactId: job.artifactId };
}
