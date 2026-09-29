import { ApiError } from './api';
/** Pending bodies stay in this tab across reloads, never in global localStorage.
 * No network retry is triggered by reading this record or reconnecting SSE.
 */
export interface PendingSubmission {
  version: 1;
  sessionId: string;
  submissionId: string;
  text: string;
  attachmentIds: string[];
  imageReferences: string[];
}
const key = (id: string) => `ai-harness:submission:${id}`;
export function readSubmission(id: string): PendingSubmission | undefined {
  const raw = sessionStorage.getItem(key(id));
  if (raw === null) return;
  const bad = () => new Error('Saved submission is unreadable. Restore its saved browser data before sending again.');
  let value: PendingSubmission;
  try { value = JSON.parse(raw); } catch { throw bad(); }
  const ids = (a: unknown): a is string[] => Array.isArray(a) && a.length <= 10 &&
    a.every((v) => typeof v === 'string' && v.length > 0) && new Set(a).size === a.length;
  if (!value || value.version !== 1 || value.sessionId !== id ||
    typeof value.submissionId !== 'string' || !/^[a-zA-Z0-9_-]{1,80}$/.test(value.submissionId) ||
    typeof value.text !== 'string' || value.text.length > 250000 ||
    !ids(value.attachmentIds) || !ids(value.imageReferences) ||
    Object.keys(value).some((k) => !['version','sessionId','submissionId','text','attachmentIds','imageReferences'].includes(k))) throw bad();
  return value;
}
export function saveSubmission(value: PendingSubmission) {
  // Fail before HTTP if persistence is unavailable/quota-limited.
  sessionStorage.setItem(key(value.sessionId), JSON.stringify(value));
}
export function acknowledgeSubmission(value: PendingSubmission) {
  if (readSubmission(value.sessionId)?.submissionId === value.submissionId)
    sessionStorage.removeItem(key(value.sessionId));
}
export function forgetSubmission(id: string) {
  // Explicit chat deletion must not leave a recoverable payload for a deleted chat.
  sessionStorage.removeItem(key(id));
}

/** Authoritative API rejection before creating any run. Proxy/auth/transport
 * failures, 5xx, unknown codes and ID conflicts are deliberately not included.
 */
export function submissionRejected(error: unknown): boolean {
  return error instanceof ApiError && error.status === 400 && [
    'invalid_body', 'invalid_id', 'invalid_message', 'invalid_attachment',
    'invalid_image_reference', 'unsupported_slash_command', 'codex_media_unsupported',
    'codex_image_tool_unavailable',
  ].includes(error.code);
}
