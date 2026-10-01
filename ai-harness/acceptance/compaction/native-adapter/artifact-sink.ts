import { mkdir, lstat } from 'node:fs/promises';
import { join } from 'node:path';
import type { Store } from '../../../server/src/store.js';
import type { Files } from '../../../server/src/files.js';
import { durableFile } from './checkpoint.js';
import { sha256, identifier } from './projection.js';
export interface ArtifactWrite { sessionId: string; runId: string; threadId: string; turnId: string; callId: string; name: string; jsonUtf8: string }
/** Exact host-owned JSON sink. The model receives no host path or arbitrary write/exec primitive. */
export function createArtifactSink(store: Store, files: Files) {
  const calls = new Set<string>();
  return async (input: ArtifactWrite, signal: AbortSignal) => {
    if (signal.aborted || ![input.sessionId,input.runId,input.threadId,input.turnId,input.callId].every(identifier) ||
        !['sensor-policy.json','engineering-calculation.json'].includes(input.name) || typeof input.jsonUtf8 !== 'string' || Buffer.byteLength(input.jsonUtf8) > 1048576 || !input.jsonUtf8.trim()) throw Error('artifact_write_outside_frozen_policy');
    const parsed = JSON.parse(input.jsonUtf8);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw Error('artifact_json_object_required');
    const s = store.getSession(input.sessionId), run = store.db.prepare('SELECT session_id,status FROM runs WHERE id=?').get(input.runId);
    if (run?.session_id !== input.sessionId || run.status !== 'running' || s.nativeSessionId !== input.threadId || s.nativeState.activeTurnId !== input.turnId || calls.has(input.callId)) throw Error('artifact_actual_run_native_ownership_required');
    const directory = join(files.workspace(s.workspaceId), `owned-artifacts-${input.runId}`);
    await files.assertNoLinks(files.workspace(s.workspaceId));
    try { await mkdir(directory,{mode:0o700}); } catch (e) { if ((e as NodeJS.ErrnoException).code !== 'EEXIST') throw e; }
    const st = await lstat(directory); if (!st.isDirectory() || st.isSymbolicLink() || st.uid !== process.getuid?.()) throw Error('artifact_directory_unsafe');
    if (signal.aborted) throw Error('artifact_write_cancelled');
    calls.add(input.callId);
    await durableFile(join(directory,input.name),input.jsonUtf8);
    // Cancellation after a write preserves bytes and never retries the call.
    if (signal.aborted) throw Error('artifact_write_cancelled_bytes_preserved');
    const current = store.getSession(input.sessionId), actualRun = store.db.prepare('SELECT session_id,status FROM runs WHERE id=?').get(input.runId);
    if (signal.aborted || actualRun?.session_id !== input.sessionId || actualRun.status !== 'running' || current.nativeSessionId !== input.threadId || current.nativeState.activeTurnId !== input.turnId) throw Error('artifact_registration_owner_changed_bytes_preserved');
    const artifact = await files.registerArtifact(input.sessionId,join(directory,input.name),input.name,'application/json',input.runId);
    return {artifactId:artifact.id,bytes:Buffer.byteLength(input.jsonUtf8),sha256:sha256(input.jsonUtf8)};
  };
}
