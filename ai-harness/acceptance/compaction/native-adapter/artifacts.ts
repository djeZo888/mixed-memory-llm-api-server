import type { Store } from '../../../server/src/store.js';
import type { Files } from '../../../server/src/files.js';
import { durableFile } from './checkpoint.js';
import { sha256 } from './projection.js';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';

/** Read actual broker-registered immutable artifacts with Files' ownership/path
 * guard. No answers are copied from a controller, truth table or expected values.
 */
export async function collectContinuationArtifacts(store: Store, files: Files, hostPrivate: string, sessionId: string, runId: string) {
  const run = store.db.prepare('SELECT session_id,status FROM runs WHERE id=?').get(runId);
  if (run?.session_id !== sessionId || run.status !== 'completed') throw Error('continuation_run_not_owned_completed');
  const assistant = store.messages(sessionId).filter(m => m.runId === runId && m.role === 'assistant' && m.streamState === 'completed').at(-1);
  if (!assistant) throw Error('actual_completed_assistant_message_required_for_artifacts');
  store.db.prepare("UPDATE h002_file_refs SET message_id=? WHERE run_id=? AND message_id IS NULL AND file_id IN (SELECT id FROM files WHERE session_id=? AND kind='artifact')").run(assistant.id,runId,sessionId);
  const selected = store.artifactsForRun(sessionId, runId).filter(f => ['sensor-policy.json', 'engineering-calculation.json'].includes(f.name));
  if (selected.length !== 2 || new Set(selected.map(f => f.name)).size !== 2) throw Error('continuation_artifacts_absent_or_ambiguous');
  const artifacts: Record<string, unknown> = {}, receipts: unknown[] = [];
  for (const f of selected) {
    if (f.sessionId !== sessionId || f.runId !== runId) throw Error('continuation_artifact_foreign');
    const download = await files.download(f.id), chunks: Buffer[] = [];
    if (download.size > 1024 * 1024) { download.stream.destroy(); throw Error('continuation_artifact_bound'); }
    let count = 0;
    for await (const chunk of download.stream) { const b = Buffer.from(chunk); count += b.length; if (count > 1024 * 1024) { download.stream.destroy(); throw Error('continuation_artifact_bound'); } chunks.push(b); }
    const bytes = Buffer.concat(chunks), utf8 = bytes.toString('utf8');
    if (!Buffer.from(utf8).equals(bytes) || bytes.length !== download.size) throw Error('continuation_artifact_changed_or_not_utf8');
    artifacts[f.name] = JSON.parse(utf8);
    const captureId = randomUUID(); await durableFile(join(hostPrivate, `${captureId}-${f.name}`), bytes);
    receipts.push({ artifactId: f.id, runId: f.runId, messageId: f.messageId, name: f.name, bytes: bytes.length, sha256: sha256(bytes), captureId });
  }
  const receiptUtf8 = JSON.stringify({ source: 'owned-store-registered-continuation-artifacts', sessionId, runId, artifacts: receipts });
  await durableFile(join(hostPrivate, `${randomUUID()}-continuation-artifacts-receipt.json`), receiptUtf8);
  return { artifacts, artifactReceiptUtf8: receiptUtf8, artifactReceiptSha256: sha256(receiptUtf8) };
}
