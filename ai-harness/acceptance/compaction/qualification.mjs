import { activeFacts } from './scorer.mjs';
import { validateRecord } from './evidence.mjs';

const permissions = new Set(['authorization', 'deployment_permission', 'vendor_authority', 'manufacturing_permission', 'calibration_write']);
const unfinished = new Set(['firmware_hash_state', 'erc_status', 'drc_status', 'bench_status', 'site_review', 'pending_check', 'cold_resume_status']);
const definitions = {
  criticalFacts: { mode: 'summary-only', cycles: [1, 2, 3], select: (f) => f.critical },
  corrections: { mode: 'summary-only', cycles: [2, 3], select: (f) => f.current.cycle > f.introducedCycle },
  supersededChoices: { mode: 'summary-only', cycles: [2, 3], select: (f) => f.versions.some((v) => v.cycle < f.current.cycle && v.value !== f.current.value) },
  authorization: { mode: 'summary-only', cycles: [1, 2, 3], select: (f) => permissions.has(f.id) },
  unfinishedChecks: { mode: 'summary-only', cycles: [1, 2, 3], select: (f) => unfinished.has(f.id) },
  continuation: { mode: 'continuation', cycles: [1, 2, 3] },
  durableRetrieval: { mode: 'durable-retrieval', cycles: [1, 2, 3] },
  coldResumeBaseline: { mode: 'cold-resume', cycles: [3] },
  coldResumeAfterContinuation: { mode: 'cold-resume-after-continuation', cycles: [3] },
  cleanChild: { mode: 'child-context', cycles: [3] },
};

// PASS here describes observed deterministic acceptance, never implied live
// fidelity. Per-observation qualification and full mandatory coverage survive
// aggregation; a partial stage or entirely synthetic run cannot qualify native.
export function summarizeQualification(records, truth) {
  const dimensions = Object.fromEntries(Object.entries(definitions).map(([name, definition]) => {
    const selected = records.filter((r) => r.mode === definition.mode && definition.cycles.includes(r.cycle));
    const observations = selected.map((record) => {
      const errors = validateRecord(record);
      const actualStatus = errors.length ? 'FAIL' : record.status;
      const facts = definition.select ? activeFacts(truth, record.cycle).filter(definition.select) : [];
      const failed = new Set((record.scores?.failures ?? []).map((v) => v.split(':')[0]));
      return { cycle: record.cycle, mode: record.mode, qualification: record.qualification,
        actualStatus, nativeStatus: record.qualification === 'native' ? actualStatus : 'NOT_TESTED',
        exactFacts: definition.select && record.scores ? { correct: facts.filter((f) => !failed.has(f.id)).length, total: facts.length } : null,
        evidenceRef: `${record.runId}:${record.cycle}:${record.mode}:${record.actionId.value ?? 'absent'}` };
    });
    const missingCycles = definition.cycles.filter((cycle) => !observations.some((o) => o.cycle === cycle));
    const duplicate = definition.cycles.some((cycle) => observations.filter((o) => o.cycle === cycle).length > 1);
    const actualStatus = duplicate || observations.some((o) => o.actualStatus === 'FAIL') ? 'FAIL' :
      observations.length && observations.every((o) => o.actualStatus === 'PASS') ? 'PASS' : 'NOT_TESTED';
    const nativeStatus = (duplicate && observations.some((o) => o.qualification === 'native')) || observations.some((o) => o.nativeStatus === 'FAIL') ? 'FAIL' :
      !missingCycles.length && observations.every((o) => o.nativeStatus === 'PASS') ? 'PASS' : 'NOT_TESTED';
    return [name, { actualStatus, nativeStatus, requiredCycles: definition.cycles, missingCycles, observations }];
  }));
  // A native fault is not mandatory semantic coverage. Unknown owned cleanup
  // still vetoes aggregate PASS, without turning missing proof into failure.
  const nativeFaults = records.filter((r) => r.qualification === 'native' && r.mode === 'fault');
  const nativeAcceptance = nativeFaults.some((r) => r.status === 'FAIL') || Object.values(dimensions).some((d) => d.nativeStatus === 'FAIL') ? 'FAIL' :
    !nativeFaults.length && Object.values(dimensions).every((d) => d.nativeStatus === 'PASS') ? 'PASS' : 'NOT_TESTED';
  return { schemaVersion: 1, nativeAcceptance, semanticAcceptance: nativeAcceptance, dimensions,
    limitation: 'ActualStatus covers observed deterministic checks only. Native PASS requires every mandatory dimension with native evidence and no native faults; source consistency does not attest a host or establish universal reliability.' };
}
