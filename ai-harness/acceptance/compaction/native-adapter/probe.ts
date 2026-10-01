import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { CodexConnection, isRecord, CodexProtocolError } from '../../../server/src/codex-connection.js';
import type { RootlessCodexProcess } from '../../../server/src/codex-engine.js';
import type { TemporaryHost } from './bootstrap.js';
import { normalizeNativeInput, bindReviewedEnvelope, type ProbeManifest } from './dispatch-guard.js';
import { emptyProbeMounts, durableFile } from './checkpoint.js';
import { identifier, requireIdentity, sha256, stableJson, summaryProbeText, summaryThreadParams } from './projection.js';

/** New isolated app-server process and thread for every probe. No fork/resume,
 * shared workspace, answer replay or merging into the parent is available here.
 * Passing fixtures proves source protocol behavior only, never native support.
 */
export async function summaryProbe(host: TemporaryHost, input: {
  parentNativeThreadId: string; summary: string; contextSha256: string; frozenPolicy: string;
  windowId: string; compactedRecordSha256: string; collectorSourceSha256: string; collectorManifestUtf8: string;
  request: unknown; manifest: ProbeManifest; childBrief?:string; actionId: string; runId: string; signal: AbortSignal;
}) {
  requireIdentity(input.parentNativeThreadId);
  if (host.launchHeld() || !input.summary.trim() || !/^[a-f0-9]{64}$/.test(input.contextSha256) || input.signal.aborted) throw Error('summary_checkpoint_mismatch_or_aborted');
  const ownedAbort = new AbortController();
  const totalDeadlineMs = Math.max(1, Math.min(120000, host.dispatchCutoffAt - Date.now()));
  const signal = AbortSignal.any([input.signal, ownedAbort.signal, AbortSignal.timeout(totalDeadlineMs)]);
  const text = input.childBrief ?? summaryProbeText(input.summary, input.frozenPolicy, input.request);
  if (input.manifest.userText !== text || input.manifest.contextSha256 !== input.contextSha256) throw Error('reviewed_summary_manifest_mismatch');
  const sessionId = randomUUID();
  const mounts = await emptyProbeMounts(host.layout.dataDir, [host.layout.hostPrivate]);
  if (host.closing || signal.aborted) throw Error('probe_host_closed_or_deadline_before_registration');
  const token = host.gateway.issueToken(sessionId, 'codex');
  const startedAt = new Date().toISOString();
  let nativeThreadId: string | undefined, nativeTurnId: string | undefined, child: RootlessCodexProcess | undefined;
  let connection: CodexConnection | undefined, nativeGone = false, gatewaySettled = false;
  let finalText: string | undefined, failure: string | undefined;
  const nativeEvents: unknown[] = [];
  const items = new Map<string, { started: any; completed?: any }>();
  let lastCompletedMessage: any, interrupt: Promise<unknown> | undefined;
  let finishHandle!: () => void;
  const finished = new Promise<void>(resolve => { finishHandle = resolve; });
  host.directProbes.set(sessionId, { abort: () => ownedAbort.abort(), finished });
  let terminalSeen: any, intentionalCleanup = false;
  let resolveTerminal!: () => void, rejectTerminal!: (error: Error) => void;
  const terminal = new Promise<void>((resolve, reject) => { resolveTerminal = resolve; rejectTerminal = reject; });
  void terminal.catch(() => undefined);
  const fail = (error?: Error) => {
    if (intentionalCleanup && terminalSeen && error?.message === 'App Server stream ended') return;
    failure = 'native_protocol_or_settlement_failure'; rejectTerminal(new CodexProtocolError(failure)); };
  const abort = () => {
    failure = 'probe_deadline_or_cancelled'; host.gateway.revokeSession(sessionId);
    // Only an observed owned turn can be interrupted. ACK does not settle work.
    if (connection && nativeThreadId && nativeTurnId && !interrupt) interrupt = connection.request('turn/interrupt', { threadId: nativeThreadId, turnId: nativeTurnId }).catch(() => undefined);
    else if (!nativeTurnId) connection?.fail(new CodexProtocolError(failure));
    rejectTerminal(new CodexProtocolError(failure));
  };
  const observe = (method: string, p: Record<string, unknown>) => {
    if (nativeEvents.length >= 4096 || Buffer.byteLength(stableJson(p)) > 4 * 1024 * 1024) throw Error('native_capture_limit');
    nativeEvents.push({ method, params: p, observedAt: new Date().toISOString() });
    if (method === 'sova/unsupportedRequest') throw Error('server_call_unavailable');
    if (method === 'thread/started') {
      if (!isRecord(p.thread) || !identifier(p.thread.id) || (nativeThreadId && nativeThreadId !== p.thread.id) || p.thread.id === input.parentNativeThreadId) throw Error('probe_thread_mismatch');
      nativeThreadId = p.thread.id; return;
    }
    if (method === 'turn/started' || method === 'turn/completed') {
      if (p.threadId !== nativeThreadId || !isRecord(p.turn) || !identifier(p.turn.id) || (nativeTurnId && nativeTurnId !== p.turn.id)) throw Error('probe_turn_mismatch');
      nativeTurnId = p.turn.id;
      if (method === 'turn/completed') {
        if (terminalSeen && stableJson(terminalSeen) !== stableJson(p)) throw Error('conflicting_native_terminal');
        terminalSeen = p;
        if (p.turn.status !== 'completed' || p.turn.error != null || !items.size || [...items.values()].some(v => !v.completed)) throw Error('probe_failed_or_unfinished_items');
        const last = lastCompletedMessage;
        if (!last || typeof last.text !== 'string' || !last.text.trim() || last.phase === 'commentary') throw Error('probe_answer_unavailable');
        if (p.turn.itemsView !== 'summary' || stableJson(p.turn.items) !== stableJson([last])) throw Error('terminal_summary_mismatch_or_not_loaded');
        finalText = last.text; resolveTerminal();
      }
      return;
    }
    if (method.startsWith('item/')) {
      if (terminalSeen || p.threadId !== nativeThreadId || p.turnId !== nativeTurnId) throw Error('probe_item_identity_mismatch');
      if (method === 'item/started' || method === 'item/completed') {
        if (!isRecord(p.item) || !identifier(p.item.id) || !['userMessage', 'agentMessage'].includes(String(p.item.type))) throw Error('probe_tool_or_unknown_item');
        if (p.item.type === 'agentMessage' && (typeof p.item.text !== 'string' ||
            (p.item.phase != null && !['commentary', 'final_answer'].includes(String(p.item.phase))))) throw Error('probe_agent_message_contract_mismatch');
        const previous = items.get(p.item.id);
        if (method === 'item/started') {
          if (previous && stableJson(previous.started) !== stableJson(p.item)) throw Error('conflicting_item_start');
          if (!previous) items.set(p.item.id, { started: p.item });
        } else {
          if (!previous || previous.started.type !== p.item.type || (previous.completed && stableJson(previous.completed) !== stableJson(p.item))) throw Error('unmatched_item_completion');
          if (!previous.completed && p.item.type === 'agentMessage') lastCompletedMessage = p.item;
          previous.completed = p.item;
        }
      } else if (method !== 'item/agentMessage/delta') throw Error('probe_unknown_item_notification');
    } else if (method === 'thread/status/changed') {
      if (p.threadId !== nativeThreadId || !isRecord(p.status) || typeof p.status.type !== 'string') throw Error('thread_status_identity_mismatch');
    } else if (!['thread/tokenUsage/updated', 'account/rateLimits/updated'].includes(method)) throw Error('probe_unknown_notification');
  };
  try {
    host.guard.register({ sessionId, actionId: input.actionId, runId: input.runId, mode: input.childBrief ? 'clean-child' : 'summary-only',
      parentNativeThreadId: input.parentNativeThreadId, manifest: input.manifest, signal,
      expiresAt: Math.min(host.dispatchCutoffAt, Date.now() + 120000), identity: () => ({ nativeThreadId, nativeTurnId }) });
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted || host.launchHeld()) throw Error('trusted_probe_launch_held_or_cancelled');
    child = await host.host.runtime.launchRootless({ sessionId, ...mounts, codexHome: join(mounts.profileDir, 'codex-home'),
      gatewayUrl: host.host.runtime.gatewayUrl, gatewayToken: token, modelPolicyVersion: host.host.runtime.modelPolicyVersion, receiptRunId: input.runId });
    if (signal.aborted) throw Error('probe_deadline_or_cancelled');
    connection = new CodexConnection(child.stdout, child.stdin, observe, fail, 15000);
    void child.exited.then(() => { if (!terminalSeen) connection?.fail(new CodexProtocolError('owned_native_process_died')); });
    const home = join(mounts.profileDir, 'codex-home');
    const initialized = await connection.request('initialize', { clientInfo: { name: 'h040-native-adapter', version: '1' },
      capabilities: { experimentalApi: true, requestAttestation: false } });
    if (!isRecord(initialized) || initialized.codexHome !== home || initialized.platformOs !== 'linux' ||
        initialized.platformFamily !== 'unix' || typeof initialized.userAgent !== 'string' || !initialized.userAgent.includes('0.158.0')) throw Error('probe_native_initialization_unqualified');
    connection.initialized();
    const result = await connection.request('thread/start', summaryThreadParams(mounts.workspace, input.frozenPolicy));
    if (!isRecord(result) || !isRecord(result.thread) || !identifier(result.thread.id) ||
        result.thread.id === input.parentNativeThreadId || (nativeThreadId && nativeThreadId !== result.thread.id) ||
        result.model !== 'qwen3.8-27b' || result.modelProvider !== 'sova' || result.cwd !== mounts.workspace || result.approvalPolicy !== 'never') throw Error('probe_start_policy_mismatch');
    nativeThreadId = result.thread.id;
    const turn = await connection.request('turn/start', { threadId: nativeThreadId, environments:[], input: [{ type: 'text', text, text_elements: [] }] });
    if (!isRecord(turn) || !isRecord(turn.turn) || !identifier(turn.turn.id) || !nativeTurnId || nativeTurnId !== turn.turn.id) throw Error('probe_start_turn_identity_mismatch');
    await terminal;
  } catch { failure ??= 'probe_native_failed'; }
  finally {
    try {
      host.gateway.revokeSession(sessionId); // Admission first; no new owned work.
      await interrupt;
      intentionalCleanup = !!terminalSeen && !failure;
      if (child) nativeGone = await child.terminateAndConfirm().catch(() => false);
      gatewaySettled = await host.gateway.confirmSettlement({ sessionId, nativeThreadId, activeTurnId: nativeTurnId }, 15000).catch(() => false);
      if (child) host.observer.gateway(sessionId, nativeThreadId, nativeTurnId ?? null, gatewaySettled);
    } catch { failure = 'probe_settlement_capture_failed'; }
    finally {
      signal.removeEventListener('abort', abort);
      try { host.guard.retire(sessionId); } finally { host.directProbes.delete(sessionId); finishHandle(); }
    }
  }
  if (!nativeGone || !gatewaySettled) failure = 'probe_owned_settlement_unconfirmed';
  const receipt = { sessionId, actionId: input.actionId, runId: input.runId, nativeThreadId: nativeThreadId ?? null,
    nativeTurnId: nativeTurnId ?? null, parentNativeThreadId: input.parentNativeThreadId,
    startedAt, settledAt: new Date().toISOString(), nativeGone, gatewaySettled, automaticReplay: false };
  await durableFile(join(host.layout.hostPrivate, `${sessionId}-native-output.json`), stableJson({ receipt, nativeEvents, failure, finalText }) + '\n');
  if (failure) return { ...receipt, outcome: 'failed', failure, settlement: { state: nativeGone && gatewaySettled ? 'released' : 'quarantined', receiptSha256: sha256(stableJson(receipt)), automaticReplay: false } };
  let answer: unknown;
  try { answer = JSON.parse(finalText!); } catch {
    const failure = { ...receipt, outcome: 'failed', failure: 'probe_answer_invalid_json',
      settlement: { state: 'released', receiptSha256: sha256(stableJson(receipt)), automaticReplay: false } };
    await durableFile(join(host.layout.hostPrivate, `${sessionId}-answer-FAILED.json`), stableJson(failure) + '\n');
    return failure;
  }
  const capture = host.guard.receipt(sessionId);
  const operation = host.observer.operation(sessionId);
  if (operation.method !== 'turn/start' || operation.nativeThreadId !== nativeThreadId || operation.nativeTurnId !== nativeTurnId) throw Error('probe_trace_identity_mismatch');
  const probeSettledOperationUtf8 = stableJson({ source: 'native-probe-settlement', runId: input.runId, actionId: input.actionId, windowId: input.windowId,
    parentNativeThreadId: input.parentNativeThreadId, nativeThreadId, nativeTurnId, parentStateSha256: input.contextSha256,
    status: 'completed', settlement: 'released', nativeProcessGone: nativeGone, gatewaySettled,
    firstRequestSha256: capture.captureSha256, normalizedRequestSha256: capture.normalizedSha256, startedAt: operation.request.observedAt, completedAt: operation.gateway.observedAt });
  const probeSettledOperationSha256 = sha256(probeSettledOperationUtf8);
  const projectionReceiptUtf8 = stableJson({ source: 'native-fresh-persisted-message-projection', logicalManifestFormat: 'h040-sorted-json-v1', runId: input.runId, actionId: input.actionId, windowId: input.windowId,
    parentNativeThreadId: input.parentNativeThreadId, nativeThreadId, nativeTurnId, parentStateSha256: input.contextSha256,
    compactedRecordSha256: input.compactedRecordSha256, summarySha256: sha256(input.summary), querySha256: sha256(stableJson(input.request)), policySha256: sha256(input.frozenPolicy),
    collectorSourceSha256: input.collectorSourceSha256, firstRequestSha256: capture.captureSha256, normalizedRequestSha256: capture.normalizedSha256, scopeReceiptSha256: (capture as any).scopeReceiptSha256 ?? null,
    inputManifestSha256: sha256(stableJson(normalizeNativeInput(JSON.parse(capture.firstRequestUtf8).input).map(m => sha256(stableJson(m))))),
    envelopeSha256: sha256(stableJson(bindReviewedEnvelope(input.manifest.envelope, nativeThreadId!, nativeTurnId!))), settledOperationSha256: probeSettledOperationSha256 });
  await durableFile(join(host.layout.hostPrivate, `${sessionId}-probe-settlement.json`), probeSettledOperationUtf8);
  if(!input.childBrief)await durableFile(join(host.layout.hostPrivate, `${sessionId}-projection.json`), projectionReceiptUtf8);
  return { ...receipt, outcome: 'completed', answer,
    durationMs: { state: 'measured', value: Date.parse(operation.gateway.observedAt) - Date.parse(operation.request.observedAt), source: 'host-native-probe-operation-observation', receiptSha256: probeSettledOperationSha256, reason: null }, isolation: { ...capture,
    ...(input.childBrief?{}:{collectorManifestUtf8: input.collectorManifestUtf8, projectionReceiptUtf8, projectionReceiptSha256: sha256(projectionReceiptUtf8)}), probeSettledOperationUtf8, probeSettledOperationSha256,
    scopeReceiptUtf8: (capture as any).scopeReceiptUtf8 ?? null, scopeReceiptSha256: (capture as any).scopeReceiptSha256 ?? null, toolsDenied: true, toolCalls: [], originalRecordIds: [],
    // Configuration/input checks do not attest actual container mounts or egress.
    filesDenied: null, networkDenied: null, accessiblePaths: (capture as any).physicalMounts ?? null, answerKeyExposed: null, parentHistoryExposed: null,
    mountAttestation: null, egressAttestation: null, qualifiedForkReceiptSha256: null,
    projection: input.childBrief?'fresh-thread-approved-brief-only':'fresh-thread-persisted-message-only', inputReceiptSha256: capture.captureSha256 },
    settlement: { state: 'released', receiptSha256: probeSettledOperationSha256, automaticReplay: false } };
}
