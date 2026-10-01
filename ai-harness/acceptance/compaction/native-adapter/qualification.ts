import {verifyFreshArtifactOwner} from '../artifact-source-proof.mjs';
import {verifyManifestSourceIdentity} from '../model-artifact-identity.mjs';
import { verifyInstalledBuild } from './build-closure.mjs';
import {assertNormalRestartQualification,isNormalRestartTicket,type NormalRestartTicket} from './normal-restart-ticket.js';
import { assertRestartTicketForConfig,isRestartTicket,type RestartTicket } from './restart.js';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { privateFile } from './checkpoint.js';
import { sha256, stableJson, reviewSnapshot } from './projection.js';
import {FULL_RETENTION_TASKS} from './policy-selection.js';
import { reviewedAuthorization } from '../authorization.mjs';
const qualified = new WeakSet<object>();
export const isQualifiedEntry = (value: unknown): value is EntryQualification => !!value && typeof value === 'object' && qualified.has(value);
export const STAGE_CAPABILITIES = Object.freeze(['qualified-fresh-persisted-message-projection','host-captured-probe-input','tools-and-files-denied-for-summary','settlement-receipts']);
export const FULL_CAPABILITIES = Object.freeze([...STAGE_CAPABILITIES,'scoped-original-record-retrieval','qualified-durable-holdout-projection','cold-resume','cold-resume-after-continuation','clean-child-context']);
export interface EntryQualification {
  runtime: Record<string,{value:string|null;reason:string|null;identity?:any;artifactEvidence?:any}>;
  profile: 'h041-summary-stage-v1' | 'h041-full-retention-v1';
  receiptSources: Record<string,string>; scopePolicies: Record<string,any>;
  qualificationSha256: string; sourceBuildManifestSha256: string;routeInstanceId:string;
}
/** Only a private root-reviewed Linux producer packet can open the entry. All
 * six runtime pins are captured before open; default exports have no packet. */
export async function qualifyEntry(config: any,restart?:RestartTicket|NormalRestartTicket): Promise<EntryQualification> {
  if(restart&&!isRestartTicket(restart)&&!isNormalRestartTicket(restart))throw Error('verified_restart_qualification_reuse_required');
  if(restart){if(isNormalRestartTicket(restart))assertNormalRestartQualification(restart,config);else assertRestartTicketForConfig(restart,config);}
  if (process.platform !== 'linux' || !process.getuid?.()) throw Error('actual_rootless_linux_entry_qualification_required');
  reviewedAuthorization(config?.bootstrap?.review);
  const review = config.bootstrap.review;
  if (!config.enabled || review.approvedBy !== 'root' || !['h041-summary-stage-v1','h041-full-retention-v1'].includes(config.profile) || !/^[a-f0-9]{64}$/.test(config.qualificationSha256 ?? '')) throw Error('concrete_qualified_entry_disabled');
  const bytes = await privateFile(config.qualificationPath);
  if (sha256(bytes) !== config.qualificationSha256 || review.qualificationSha256 !== sha256(bytes)) throw Error('reviewed_actual_entry_producer_packet_required');
  const packet = JSON.parse(bytes.toString('utf8'));
  if (packet.source !== 'root-owned-linux-no-generation-qualification' || packet.candidateCommit !== review.candidateCommit || packet.windowId !== review.authorization.windowId ||
      packet.route?.alias !== 'qwen3.8-27b' || packet.route?.service !== 'qwen-gpu1' || packet.route?.controlSlot !== 'qwen' || packet.route?.endpoint !== 'http://10.156.100.60:30004/v1' ||
      typeof packet.route.instanceId!=='string'||!packet.route.instanceId||!packet.route.operationId || !packet.route.identitySha256 || !Number.isFinite(Date.parse(packet.observedAt)) || Date.now() - Date.parse(packet.observedAt) < 0 || (!restart&&Date.now() - Date.parse(packet.observedAt) > 60000)) throw Error('fresh_current_linux_route_qualification_required');
  if(!restart&&review.artifactIdentityExpected?.proofVersion==='retained-linux-files-v1'&&verifyFreshArtifactOwner(packet.artifactIdentity,review.artifactIdentityExpected,review.freshArtifactOwnerExpected,packet.route).status!=='SOURCE_VALID')throw Error('actual_fresh_owner_and_manifest_protection_required');
  const keys = ['version','sourceRevision','binarySha256','model','modelRevision','tokenizerRevision'];
  const runtime: EntryQualification['runtime'] = {};
  for (const key of keys) {
    const evidence = packet.pins?.[key];
    if(['modelRevision','tokenizerRevision'].includes(key)&&evidence?.value===null&&review.runtimePins?.[key]?.kind==='MANIFEST_SOURCE_REVISION'){const expected=review.artifactIdentityExpected;if(!expected||!['separate-raw-files-v2','retained-linux-files-v1'].includes(expected.proofVersion)||typeof evidence.rawUtf8!=='string'||sha256(evidence.rawUtf8)!==evidence.rawSha256||!Array.isArray(evidence.jsonPath)||evidence.exitCode!==0||evidence.capturedBy!=='root-owned-linux-readback'||evidence.jsonPath.reduce((v:any,k:string)=>v?.[k],JSON.parse(evidence.rawUtf8))!==null)throw Error('actual_native_revision_null_capture_required');const verification=verifyManifestSourceIdentity(packet.artifactIdentity,expected);if(verification.status!=='SOURCE_VALID'||stableJson(verification.identity)!==stableJson(review.runtimePins[key]))throw Error('actual_typed_current_artifact_source_identity_required');runtime[key]={value:null,reason:key==='modelRevision'?'Native revision explicitly reported null; immutable artifact source independently bound':'Native tokenizer revision unreported; producer projection null; immutable artifact source independently bound',identity:verification.identity,artifactEvidence:{receipt:packet.artifactIdentity,expected}};continue;}
    if (!evidence || typeof evidence.value !== 'string' || !evidence.value || typeof evidence.rawUtf8 !== 'string' || sha256(evidence.rawUtf8) !== evidence.rawSha256 ||
        !Array.isArray(evidence.argv) || !evidence.argv.length || evidence.exitCode !== 0 || evidence.capturedBy !== 'root-owned-linux-readback' || review.runtimePins?.[key] !== evidence.value) throw Error('actual_six_runtime_pin_captures_required');
    // Each pin is extracted from captured producer bytes by its independently
    // reviewed JSON path (or exact text), never merely repeated in a wrapper.
    const extracted = evidence.jsonPath ? evidence.jsonPath.reduce((v:any,k:string) => v?.[k],JSON.parse(evidence.rawUtf8)) : evidence.rawUtf8.trim();
    if (extracted !== evidence.value) throw Error('runtime_pin_not_in_actual_capture');
    runtime[key] = {value:evidence.value,reason:null};
  }
  if (runtime.version.value !== '0.158.0' || runtime.sourceRevision.value !== '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3' || runtime.model.value !== 'qwen3.8-27b' || !/^[a-f0-9]{64}$/.test(runtime.binarySha256.value??'')) throw Error('retained_runtime_pin_mismatch');
  const manifestBytes = await privateFile(config.sourceBuildManifestPath);
  if (sha256(manifestBytes) !== review.sourceBuildManifestSha256) throw Error('reviewed_source_and_executed_build_required');
  const manifest = JSON.parse(manifestBytes.toString('utf8'));
  await verifyInstalledBuild(config.bootstrap.repository,manifest);
  for (const mode of config.profile === 'h041-summary-stage-v1' ? ['summary-only'] : ['summary-only','read-original','clean-child']) if (!packet.scopePolicies?.[mode] || stableJson(packet.scopePolicies[mode]) !== stableJson(review.scopePolicies?.[mode])) throw Error('independently_reviewed_scope_policy_missing');
  if(config.profile==='h041-full-retention-v1'&&(!FULL_RETENTION_TASKS.includes(review.authorization.task)||!['v1','v2'].includes(review.retentionParentPolicy?.collaborationVersion)||stableJson(packet.retentionParentPolicy)!==stableJson(review.retentionParentPolicy)||!review.retentionParentPolicy.artifactPolicy||!review.retentionParentPolicy.childPolicy||!review.retentionParentPolicy.collaborationToolNames||!review.childProjectionSpec||stableJson(packet.childProjectionSpec)!==stableJson(review.childProjectionSpec)||stableJson(review.childProjectionSpec.envelope)!==stableJson(review.childResponseEnvelope)))throw Error('distinct_initial_source_frozen_retention_parent_policy_required');
  if (!packet.receiptSources || stableJson(packet.receiptSources) !== stableJson(review.receiptSources)) throw Error('receipt_source_pins_missing');
  const result = reviewSnapshot({ runtime, profile: config.profile, receiptSources: packet.receiptSources, scopePolicies: packet.scopePolicies, qualificationSha256: sha256(bytes), sourceBuildManifestSha256: sha256(manifestBytes),routeInstanceId:packet.route.instanceId });
  qualified.add(result); return result;
}
