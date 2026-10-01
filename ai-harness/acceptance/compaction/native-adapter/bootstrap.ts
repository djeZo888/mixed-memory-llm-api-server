import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { join, resolve } from 'node:path';
import { createApp } from '../../../server/src/app.js';
import { composeCodexHost } from '../../../server/src/codex-host.js';
import { codexDeployment } from '../../../server/src/codex-deployment.js';
import { createProductionQwenVerifier, loadQwenReceipt } from '../../../server/src/codex-production.js';
import { readProtectedCredential } from '../../../server/src/protected-credential.js';
import { createGateway, type Gateway } from '../../../server/src/gateway.js';
import { GatewayOwnershipLedger } from '../../../server/src/gateway-ownership.js';
import { DISPATCH_STATE, DispatchFreeze } from '../../../server/src/dispatch-freeze.js';
import { DatabaseSync } from 'node:sqlite';
import { DispatchGuard } from './dispatch-guard.js';
import { createLayout, durableFile, privateFile } from './checkpoint.js';
import { sha256, stableJson } from './projection.js';
import { sourceClosure } from './source-closure.js';

export const FIXED_POLICY = Object.freeze({ version: '0.158.0', sourceRevision: '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3',
  gatewayUrl: 'http://10.0.2.2:8081/v1', gatewayHost: '127.0.0.1', gatewayPort: 8081,
  frontendHost: '127.0.0.1', frontendPort: 18081, contextWindow: 480000, autoCompactTokenLimit: 400000, maxOutputTokens: 65536 });
export interface BootstrapInput {
  review: { enabled: boolean; approvedBy: string; candidateCommit: string; notAfterUtc: string;
    policy: typeof FIXED_POLICY; files: Record<string, string>; productionStateReceiptSha256: string };
  actualCandidateCommit: string; privateBase: string; productionDataDir: string; repository: string;
  launcherPath: string; qwenReceiptPath: string; inferenceKeyPath: string; controlKeyPath: string;
  productionStateReceiptPath: string;
}
/** No side effects at import. Root must supply a concrete source-closure review
 * and a fresh, independently obtained normal owned-stop/quiescence receipt.
 * This helper neither stops production nor sweeps/kills/changes ports.
 */
export async function bootstrap(input: BootstrapInput) {
  const review = input.review, expiry = Date.parse(review?.notAfterUtc);
  if (review?.enabled !== true || review.approvedBy !== 'root' || !/^[a-f0-9]{40}$/.test(review.candidateCommit) ||
      input.actualCandidateCommit !== review.candidateCommit || !Number.isFinite(expiry) || expiry <= Date.now() ||
      expiry > Date.parse('2026-10-01T02:25:00Z') || stableJson(review.policy) !== stableJson(FIXED_POLICY)) throw Error('root_concrete_review_required_or_expired');
  if (process.platform !== 'linux' || process.getuid?.() === 0) throw Error('reviewed_linux_rootless_host_required');
  if (input.repository !== resolve(fileURLToPath(new URL('../../../../', import.meta.url)))) throw Error('reviewed_repository_is_not_imported_repository');
  // Root includes protected source successors, verifier/gateway/engine/launcher,
  // policy and egress files in the same review, not merely the entrypoint hash.
  const closure = await sourceClosure(input.repository, input.launcherPath, input.qwenReceiptPath);
  if (stableJson(closure) !== stableJson(review.files)) throw Error('imported_source_closure_mismatch');
  if (!input.launcherPath.endsWith('/deploy/run-codex.sh') || review.files[input.launcherPath] !== sha256(await readFile(input.launcherPath))) throw Error('reviewed_launcher_mismatch');
  if (review.files[input.qwenReceiptPath] !== sha256(await readFile(input.qwenReceiptPath))) throw Error('reviewed_qwen_receipt_mismatch');
  const productionBytes = await privateFile(input.productionStateReceiptPath);
  if (sha256(productionBytes) !== review.productionStateReceiptSha256) throw Error('production_state_receipt_mismatch');
  const production = JSON.parse(productionBytes.toString('utf8'));
  if (production.schema !== 1 || production.capturedBy !== 'root-owned-host-observation' ||
      production.dataDir !== input.productionDataDir || production.stopMethod !== 'normal-owned-stop' ||
      production.noWriters !== true || production.nativeSettled !== true || production.gatewaySettled !== true ||
      !/^[a-f0-9]{64}$/.test(production.preservedStateSha256 ?? '') ||
      !Number.isFinite(Date.parse(production.observedAt)) || Date.now() - Date.parse(production.observedAt) < 0 ||
      Date.now() - Date.parse(production.observedAt) > 60000) throw Error('fresh_preserved_production_quiescence_unavailable');
  const layout = await createLayout(input.privateBase, [input.productionDataDir, input.repository,
    input.inferenceKeyPath, input.controlKeyPath, input.productionStateReceiptPath]);
  const captures = join(layout.hostPrivate, 'captures');
  const { mkdir } = await import('node:fs/promises');
  await mkdir(captures, { mode: 0o700 });
  const guard = new DispatchGuard(captures);
  const receipt = await loadQwenReceipt(input.qwenReceiptPath);
  const inferenceKey = await readProtectedCredential(input.inferenceKeyPath);
  const controlKey = await readProtectedCredential(input.controlKeyPath);
  const verifyLane = createProductionQwenVerifier(receipt, { inferenceKey, controlKey });
  // Reuse the existing fail-closed held() semantics with a read-only connection.
  // Opening the normal owner would create/chmod shared production gate state.
  await privateFile(DISPATCH_STATE);
  const freezeDb = new DatabaseSync(DISPATCH_STATE, { readOnly: true });
  const freeze = { held: (alias: string) => DispatchFreeze.prototype.held.call({ db: freezeDb } as DispatchFreeze, alias), close: () => freezeDb.close() };
  let gateway: Gateway | undefined;
  const host = composeCodexHost(input.launcherPath, () => gateway, { protocolQualified: true, rootlessQualified: true,
    verifyLane, outputLimit: 65536, qualifiedAliases: Object.keys(receipt.lanes), nativeDelegationQualified: true });
  const held = () => Date.now() >= expiry || freeze.held('harness');
  const application = await createApp({ newChatEngine: 'codex', dataDir: layout.dataDir,
    allowedOrigins: ['http://127.0.0.1:18081'], launcher: input.launcherPath, ...codexDeployment({ enablePreview: true, runtime: host.runtime }),
    engineFactory: () => { throw Error('minimax_outside_adapter_scope'); },
    gatewayUrl: FIXED_POLICY.gatewayUrl, dispatchHeld: held,
    issueToken: id => gateway!.issueToken(id, 'codex'), revokeToken: token => gateway!.revokeToken(token), visionAvailable: false });
  const ownership = new GatewayOwnershipLedger(application.store.db).options();
  gateway = createGateway({ upstreamKey: inferenceKey, ownership, dispatchHeld: alias => held() || freeze.held(alias),
    qwenOutputLimit: 65536, responses: { ...host.responses!, countQwen: guard.wrap(host.responses!.countQwen) },
    diagnostics: { capture: guard.capture }, activeTimeoutMs: 120000, queueTimeoutMs: 120000 });
  let closed = false;
  const directProbes = new Map<string, { abort(): void; finished: Promise<void> }>();
  const close = async () => {
    if (closed) return;
    closed = true; host.stopSettlementObservation();
    const handles = [...directProbes.values()];
    for (const handle of handles) handle.abort();
    await Promise.all(handles.map(handle => handle.finished));
    await application.broker.close();
    await gateway!.close();
    await application.app.close();
    freeze.close();
  };
  try {
    // Fixed bind only. EADDRINUSE is retained and propagated; no fallback/sweep.
    await gateway.app.listen({ host: '127.0.0.1', port: 8081 });
    await application.app.listen({ host: '127.0.0.1', port: 18081 });
    await durableFile(join(layout.hostPrivate, 'bootstrap-receipt.json'), stableJson({
      schema: 1, candidateCommit: review.candidateCommit, policy: FIXED_POLICY, layout,
      reviewSha256: sha256(stableJson(review)), productionStateReceiptSha256: review.productionStateReceiptSha256,
      productionBrowserQualification: 'NOT_TESTED', runtimeBinaryQualification: 'NOT_TESTED' }) + '\n');
    return { application, gateway, host, guard, layout, close, expiresAt: expiry, verifyLane, directProbes, get closing() { return closed; } };
  } catch (error) {
    await durableFile(join(layout.hostPrivate, 'bootstrap-FAILED.json'), stableJson({
      outcome: 'failed', code: (error as NodeJS.ErrnoException).code === 'EADDRINUSE' ? 'EADDRINUSE' : 'bootstrap_failed', automaticRetry: false }) + '\n');
    await close(); throw error;
  }
}
export type TemporaryHost = Awaited<ReturnType<typeof bootstrap>>;
