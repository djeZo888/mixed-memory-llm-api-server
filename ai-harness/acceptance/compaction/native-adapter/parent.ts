import { CodexEngine } from '../../../server/src/codex-engine.js';
import type { EngineUpdate, NativeEngineState } from '../../../server/src/contracts.js';
import type { TemporaryHost } from './bootstrap.js';
import { durableFile } from './checkpoint.js';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { stableJson } from './projection.js';

/** Initialization only, with the same launch gate and owned close registry as
 * probes. No prompt is sent to obtain an ID. Callbacks come from the native engine.
 */
export async function openNativeParent(h: TemporaryHost, sessionId: string, callerSignal: AbortSignal, expectedResumeThreadId?:string) {
  await h.authorizeTaskAction?.(sessionId,'parent-initialize-'+randomUUID(),callerSignal);
  if (h.closing || h.launchHeld() || callerSignal.aborted) throw Error('trusted_parent_launch_held_or_aborted');
  const ownedAbort = new AbortController(), signal = AbortSignal.any([callerSignal, ownedAbort.signal]);
  let finish!: () => void;
  const finished = new Promise<void>(resolve => { finish = resolve; });
  const s = h.application.store.getSession(sessionId);
  if(s.engineKind!=='codex'||(expectedResumeThreadId ? s.nativeSessionId!==expectedResumeThreadId : !!s.nativeSessionId))throw Error('fresh_or_exact_adopted_parent_required');
  let engine: CodexEngine | undefined, token: string | undefined, cancellation: Promise<void> | undefined, failure: unknown;
  const events: ({ type: 'state'; state: NativeEngineState } | { type: 'native-id'; id: string } | { type: 'update'; update: EngineUpdate })[] = [];
  const abort = () => { ownedAbort.abort(); h.gateway.revokeSession(s.id); if (engine) { cancellation ??= engine.close(); void cancellation.catch(() => undefined); } };
  // Register BEFORE prepare/launch awaits. Host close aborts then awaits this
  // operation's actual cleanup, even if initialization or capture fails.
  h.directProbes.set(s.id, { abort, finished });
  signal.addEventListener('abort', abort, { once: true });
  try {
    await h.application.files.prepare(s.id, s.workspaceId);
    if (signal.aborted || h.launchHeld()) throw Error('trusted_parent_launch_held_or_aborted');
    token = h.gateway.issueToken(s.id, 'codex');
    engine = new CodexEngine({ sessionId: s.id, engineKind: s.engineKind, engineVersion: s.engineVersion,
      modelPolicyVersion: s.modelPolicyVersion, nativeState: s.nativeState,nativeSessionId:expectedResumeThreadId,
      onNativeState: state => { h.application.store.setNativeState(s.id, 'codex', state); events.push({ type: 'state', state }); },
      onNativeSessionId: id => { h.application.store.setNative(s.id, id, 'codex'); events.push({ type: 'native-id', id }); },
      onUpdate: update => { events.push({ type: 'update', update }); },
      profileDir: h.application.files.profile(s.id), workspace: h.application.files.workspace(s.workspaceId),
      launcher: h.launcherPath, gatewayUrl: h.host.runtime.gatewayUrl, gatewayToken: token, stderrPath: h.application.files.log(s.id),
      dispatchHeld: () => signal.aborted || h.launchHeld(), onExit: () => { if (token) h.gateway.revokeToken(token); } }, h.host.runtime);
    if (signal.aborted || h.launchHeld()) throw Error('trusted_parent_launch_held_or_aborted');
    await engine.start();
  } catch (error) { failure = error; }
  finally {
    try {
      h.gateway.revokeSession(s.id);
      try { await engine?.close(); await cancellation; } catch (error) { failure ??= error; }
      try { await durableFile(join(h.layout.hostPrivate, `${randomUUID()}-parent-initialization.json`), stableJson({ source: 'actual-codex-engine-callbacks', sessionId, events, failed: !!failure })); }
      catch (error) { failure ??= error; h.application.store.setNativeState(s.id, 'codex', { ...h.application.store.getSession(s.id).nativeState, ownership: 'uncertain' }); }
    } finally { signal.removeEventListener('abort', abort); h.directProbes.delete(s.id); finish(); }
  }
  const actual = h.application.store.getSession(s.id);
  if (failure || signal.aborted || !actual.nativeSessionId || actual.nativeState.ownership !== 'idle' || !h.observer.settled(s.id)) throw Error('parent_initialization_or_settlement_unqualified');
  return { sessionId: s.id, nativeThreadId: actual.nativeSessionId };
}
