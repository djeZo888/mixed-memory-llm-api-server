import {verifyManifestSourceIdentity} from './model-artifact-identity.mjs';
import schema from './evidence.schema.json' with { type: 'json' };
import { actionIdFor } from './scorer.mjs';

export const absent = (reason) => ({ value: null, reason });
export const metadata = (value) => ({ value, reason: null });
export const unknownMeasurement = (reason, state = 'absent') => ({ state, value: null, source: null, receiptSha256: null, reason });
export const measured = (value, source, receiptSha256) => ({ state: 'measured', value, source, receiptSha256, reason: null });

// Small offline validator for exactly the keywords used by the checked-in schema.
// The schema is also consumable by a full Draft 2020-12 validator at integration.
export function validateShape(value, rule = schema, path = '$', rootSchema = rule) {
  if (rule.$ref) return validateShape(value, rule.$ref.split('/').slice(1).reduce((v, k) => v[k], rootSchema), path, rootSchema);
  if (rule.oneOf) {
    const passing = rule.oneOf.filter((r) => !validateShape(value, r, path, rootSchema).length);
    return passing.length === 1 ? [] : [`${path}:oneOf`];
  }
  const errors = [];
  const actualType = value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
  const types = rule.type === undefined ? null : Array.isArray(rule.type) ? rule.type : [rule.type];
  if (types && !types.some((t) => t === 'integer' ? Number.isSafeInteger(value) : t === actualType)) return [`${path}:type`];
  if ('const' in rule && value !== rule.const) errors.push(`${path}:const`);
  if (rule.enum && !rule.enum.includes(value)) errors.push(`${path}:enum`);
  if (typeof value === 'string') {
    if (rule.minLength !== undefined && value.length < rule.minLength) errors.push(`${path}:minLength`);
    if (rule.pattern && !new RegExp(rule.pattern).test(value)) errors.push(`${path}:pattern`);
  }
  if (typeof value === 'number') {
    if (rule.minimum !== undefined && value < rule.minimum) errors.push(`${path}:minimum`);
    if (rule.maximum !== undefined && value > rule.maximum) errors.push(`${path}:maximum`);
  }
  if (actualType === 'array' && rule.items) value.forEach((v, i) => errors.push(...validateShape(v, rule.items, `${path}[${i}]`, rootSchema)));
  if (actualType === 'object') {
    for (const key of rule.required ?? []) if (!Object.hasOwn(value, key)) errors.push(`${path}.${key}:required`);
    for (const [key, val] of Object.entries(value)) {
      if (rule.properties?.[key]) errors.push(...validateShape(val, rule.properties[key], `${path}.${key}`, rootSchema));
      else if (rule.additionalProperties === false) errors.push(`${path}.${key}:additionalProperty`);
    }
  }
  return errors;
}

export function validateRecord(record) {
  const errors = validateShape(record);
  if (errors.length) return errors;
  if (record.scores) {
    for (const category of ['critical', 'noncritical']) {
      const s = record.scores[category];
      if (s.correct > s.total) errors.push(`score-overflow:${category}`);
    }
    if (record.status === 'PASS' && (record.scores.failures.length || ['critical', 'noncritical'].some((k) => record.scores[k].correct !== record.scores[k].total))) errors.push('pass-with-inexact-facts');
    if (['summary-only', 'durable-retrieval', 'cold-resume'].includes(record.mode)) {
      const [critical, noncritical] = [[49, 7], [56, 8], [62, 10]][record.cycle - 1];
      if (record.scores.critical.total !== critical || record.scores.noncritical.total !== noncritical) errors.push('fact-denominator-mismatch');
    }
  }
  if (record.trigger.type === 'auto' && !record.trigger.evidence.some((e) => e.kind === 'native-request-metadata' && e.nativeRequestKind === 'compaction' && e.nativeTrigger === 'auto')) errors.push('automatic-trigger-unattributed');
  if (record.trigger.type === 'manual' && !record.trigger.evidence.some((e) => e.kind === 'manual-action' || (record.qualification === 'synthetic' && e.kind === 'synthetic'))) errors.push('manual-action-unattributed');
  if (record.qualification === 'native' && record.trigger.evidence.some((e) => e.kind === 'synthetic')) errors.push('synthetic-native-evidence');
  if (record.settlement.automaticReplay) errors.push('automatic-replay-forbidden');
  if (record.settlement.state !== 'unknown' && !record.settlement.receiptSha256) errors.push('settlement-unproven');
  if (record.failure && record.status === 'PASS') errors.push('original-failure-hidden');
  if (record.status === 'PASS') {
    if (record.checks.status !== 'PASS' || record.checks.errors.length) errors.push('pass-with-failed-checks');
    if (record.nativeOutcome !== 'completed' || record.settlement.state !== 'released') errors.push('pass-without-completion-and-settlement');
    if (!record.originals.recoverable || !record.originals.receiptSha256 || record.originals.beforeSha256 !== record.originals.afterSha256) errors.push('pass-without-original-preservation');
    if (['summary-only', 'durable-retrieval', 'cold-resume'].includes(record.mode) && (!record.scores || record.scores.critical.total + record.scores.noncritical.total === 0)) errors.push('pass-without-score');
    if (['summary-only', 'cold-resume'].includes(record.mode) && (record.retrieval.used !== false || record.retrieval.callIds.length || record.retrieval.sourceIds.length || record.isolation.status !== 'PASS' || !record.isolation.receiptSha256)) errors.push('summary-not-isolated');
    if (record.mode === 'durable-retrieval' && (record.retrieval.used !== true || !record.retrieval.callIds.length || !record.retrieval.sourceIds.length || !record.retrieval.traceSha256 || record.isolation.status !== 'PASS' || !record.isolation.receiptSha256)) errors.push('durable-retrieval-unproven');
    if (['continuation', 'cold-resume-after-continuation'].includes(record.mode) && Object.keys(record.artifactHashes).length !== 2) errors.push('continuation-artifacts-absent');
    if (record.mode === 'child-context' && (record.isolation.status !== 'PASS' || !record.isolation.receiptSha256)) errors.push('child-context-unproven');
    if (record.qualification === 'native') {
      if (!record.operationWindowId.value || !record.nativeCompactionWindowId.value ||
        !record.nativeCompactionWindowId.value.startsWith(record.compactionNativeThreadId.value + ':') ||
        !/^\d+$/.test(record.nativeCompactionWindowId.value.slice((record.compactionNativeThreadId.value ?? '').length + 1))) errors.push('native-and-host-operation-window-unproven');
      if (record.trigger.type !== 'manual' || !record.trigger.evidence.some((e) => e.kind === 'manual-action' && e.runId === record.runId && e.actionId === record.compactionActionId.value && e.nativeThreadId === record.compactionNativeThreadId.value) || record.compactionActionId.value !== actionIdFor(record.runId, record.cycle, 'compact')) errors.push('native-manual-attribution-required');
      if (['summary-only', 'durable-retrieval', 'cold-resume'].includes(record.mode) &&
        (record.nativeThreadId.value !== record.isolation.nativeThreadId || record.nativeTurnId.value !== record.isolation.nativeTurnId || record.nativeThreadId.value === record.compactionNativeThreadId.value || record.isolation.parentNativeThreadId !== record.compactionNativeThreadId.value || record.actionId.value !== record.isolation.actionId)) errors.push('native-probe-identity-binding');
      if (['summary-only', 'durable-retrieval', 'cold-resume', 'child-context'].includes(record.mode) && (!record.isolation.firstRequestSha256 || !record.isolation.inputManifestSha256 || !record.isolation.scopeReceiptSha256 || record.isolation.firstRequestSha256 !== record.isolation.receiptSha256)) errors.push('native-first-request-proof-absent');
      if (record.actionId.value !== actionIdFor(record.runId, record.cycle, record.mode)) errors.push('native-action-identity-binding');
      for (const [key, value] of Object.entries(record.runtime)) if (typeof value === 'object' && value.value === null) {const typed=['modelRevision','tokenizerRevision'].includes(key)&&value.identity?.kind==='MANIFEST_SOURCE_REVISION'&&value.artifactEvidence&&verifyManifestSourceIdentity(value.artifactEvidence.receipt,value.artifactEvidence.expected).status==='SOURCE_VALID'&&JSON.stringify(value.identity)===JSON.stringify(verifyManifestSourceIdentity(value.artifactEvidence.receipt,value.artifactEvidence.expected).identity);if(!typed)errors.push(`native-pass-unpinned:${key}`);}
      if(record.mode==='cold-resume-after-continuation'&&record.nativeTurnId.value===null&&(!record.processRestart||record.processRestart.beforeProcessId===record.processRestart.afterProcessId||record.processRestart.nativeThreadId!==record.nativeThreadId.value))errors.push('actual-no-generation-application-restart-unproven');
      for (const key of (record.mode==='cold-resume-after-continuation'&&record.processRestart?['actionId','nativeThreadId']:['actionId', 'nativeThreadId', 'nativeTurnId'])) if (record[key].value === null) errors.push(`native-pass-unidentified:${key}`);
      if (record.runtime.version.value !== '0.158.0' || record.runtime.sourceRevision.value !== '064c6b8c737f5b41d171fdda80bd9ef10ad06eb3') errors.push('native-runtime-pin-mismatch');
      if (record.durationMs.state !== 'measured') errors.push('native-duration-absent');
    }
  }
  return errors;
}
