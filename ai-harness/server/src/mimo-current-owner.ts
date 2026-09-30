/** Reattest the existing supervised owner. No new endpoint, daemon or queue.
 * Static artifact/source/template/allocation review remains in the protected
 * receipt. Boot + canonical node generation attests current native/supervisor/
 * proxy identities (node_observation._mimo), never a saved instance string. */
import { MIMO_MODEL, validateMimoQualification, type MimoQualification } from "./mimo.js";
import { nativeJson, observeMimoNative, MIMO_URL, type MimoFrontierOptions, type MimoNativePins } from "./mimo-frontier.js";
import { boundedControlGet } from "./codex-production.js";
import { ApiError } from "./errors.js";
const NODE = "http://10.156.100.60:30008/control/v1/node/status";
export const MIMO_GPU_UUID = "GPU-69acfa26-8b60-61b5-702d-aee252c163cc";
const refuse = (): never => { throw new ApiError(503, "mimo_current_owner_unqualified", "Current MiMo owner is not qualified"); };
export function mimoOwnerStamp(value: any, context: number, now = Date.now()): string {
  const fresh = (v: any) => v?.state === "ok" && v.freshness === "fresh" && Number.isFinite(v.age_ms) && v.age_ms >= 0 && v.age_ms <= 15000 &&
    Number.isFinite(Date.parse(v.observed_at)) && now - Date.parse(v.observed_at) >= -2000 && now - Date.parse(v.observed_at) <= 15000;
  const matches = Array.isArray(value?.services) ? value.services.filter((s: any) => s.service_id === MIMO_MODEL) : [];
  if (value?.schema_version !== 1 || value.node_id !== "ai-vm" || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(value.boot_id) ||
      !fresh(value) || matches.length !== 1) return refuse();
  const s = matches[0];
  if (!fresh(s) || !Number.isSafeInteger(s.generation) || s.generation < 0 || s.ready !== true || s.hardware_latched !== false ||
      s.availability !== "available" || s.reason !== null || s.model_alias !== MIMO_MODEL ||
      s.deployment_id !== `mimo-v2.6-pro-rl-${context}-mxfp4` || s.configured_context_tokens !== context || s.max_output_tokens !== 65536 ||
      JSON.stringify(s.required_gpu_uuids) !== JSON.stringify([MIMO_GPU_UUID])) return refuse();
  return `${value.boot_id}:${s.generation}`;
}

export function createCurrentMimoProvider(reviewed: MimoQualification, pins: MimoNativePins,
  key: MimoFrontierOptions["upstreamKey"], controlKey: () => Promise<string>,
  get: (url: string, key: string, signal: AbortSignal) => Promise<any> = (url, credential, signal) => url === NODE ? boundedControlGet(url, credential, signal) : nativeJson(url, credential, signal),
  now: () => number = Date.now): NonNullable<MimoFrontierOptions["current"]> {
  const immutable = validateMimoQualification(reviewed);
  return async signal => {
    const bounded = AbortSignal.any([signal, AbortSignal.timeout(15000)]);
    const control = await controlKey();
    const credential = typeof key === "function" ? await key() : key;
    if (![control, credential].every(v => typeof v === "string" && /^[\x21-\x7e]+$/.test(v))) return refuse();
    const stamp = async (s: AbortSignal) => mimoOwnerStamp(await get(NODE, control, s), immutable.identity.actualSlotContext, now());
    const expected = await stamp(bounded);
    const qualification = validateMimoQualification({ ...immutable, identity: { ...immutable.identity,
      serverInstance: `node-owner:${expected}`, serverGeneration: expected } });
    const observe = async (requestSignal: AbortSignal) => {
      const limited = AbortSignal.any([requestSignal, AbortSignal.timeout(15000)]);
      if (await stamp(limited) !== expected) return refuse();
      const base = MIMO_URL.replace(/\/v1$/, "");
      const props = await get(`${base}/props`, credential, limited);
      const slots = await get(`${base}/slots`, credential, limited);
      const result = observeMimoNative(props, slots, qualification, pins);
      if (await stamp(limited) !== expected) return refuse();
      return result;
    };
    // Qualify before native counting. All later count/generation/drain checks
    // retain exactly this stamp; restart causes refusal, never transparent replay.
    await observe(bounded);
    return { qualification, observe };
  };
}
