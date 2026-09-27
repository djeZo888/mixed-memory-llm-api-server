import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { FRONTIER_MODEL, frontierConfiguration, type FrontierOptions, type FrontierRecord } from './frontier.js';
import { MIMO_MODEL } from './mimo.js';
import { readMimoEvidence, validateMimoIntegration, mimoObserver, type MimoFrontierOptions } from './mimo-frontier.js';
export interface ActiveFrontierSelection {
  model: typeof FRONTIER_MODEL | typeof MIMO_MODEL;
  mimoEnabled: boolean;
  mimoQualificationSha256: string | null;
  mimoContextWindow: number | null;
  mimoMaxOutputTokens: number | null;
}
export function activeFrontierSelection(value: unknown): ActiveFrontierSelection {
  const v = value as ActiveFrontierSelection;
  if (!v || ![FRONTIER_MODEL, MIMO_MODEL].includes(v.model) || typeof v.mimoEnabled !== 'boolean') throw Error('Invalid frontier selection');
  if (v.model === MIMO_MODEL && (!v.mimoEnabled || typeof v.mimoQualificationSha256 !== 'string' || !/^[a-f0-9]{64}$/.test(v.mimoQualificationSha256) ||
    !Number.isSafeInteger(v.mimoContextWindow) || v.mimoContextWindow! < 2 || v.mimoContextWindow! > 1048576 ||
    !Number.isSafeInteger(v.mimoMaxOutputTokens) || v.mimoMaxOutputTokens! < 1 || v.mimoMaxOutputTokens! > 65536 || v.mimoMaxOutputTokens! >= v.mimoContextWindow!)) throw Error('Unqualified MiMo selection');
  return v;
}
export function loadFrontierSelection(): ActiveFrontierSelection {
  return activeFrontierSelection(JSON.parse(readFileSync(new URL('../../config/active-frontier.json', import.meta.url), 'utf8')));
}
export function loadActiveFrontier(selection: ActiveFrontierSelection, upstreamKey: FrontierOptions['upstreamKey'], onRequestState: (r: FrontierRecord) => void): FrontierOptions | MimoFrontierOptions | undefined {
  if (selection.model === FRONTIER_MODEL) {
    const glm = frontierConfiguration(JSON.parse(readFileSync(new URL('../../config/frontier.json', import.meta.url), 'utf8')));
    return glm ? { ...glm, upstreamKey, onRequestState } : undefined;
  }
  const candidate = JSON.parse(readFileSync(new URL('../../config/mimo-candidate.json', import.meta.url), 'utf8'));
  if (!candidate.enabled || !candidate.qualified || candidate.model !== MIMO_MODEL) throw Error('MiMo candidate disabled');
  const receipt = readMimoEvidence('/etc/ai-harness/mimo-qualification.json');
  if (createHash('sha256').update(receipt.text).digest('hex') !== selection.mimoQualificationSha256) throw Error('MiMo receipt not reviewed');
  const { qualification, capacity, nativePins } = validateMimoIntegration(receipt.value);
  if (selection.mimoContextWindow !== qualification.identity.actualSlotContext || selection.mimoMaxOutputTokens !== Math.min(65536, qualification.identity.maxOutputTokens)) throw Error('MiMo profile/capacity mismatch');
  return { provider: 'mimo', contextWindow: qualification.identity.actualSlotContext, qualification, capacity,
    upstreamKey, onRequestState, serialCompletionQualified: true, observe: mimoObserver(qualification, nativePins, upstreamKey) };
}
