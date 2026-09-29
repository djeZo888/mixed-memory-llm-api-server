/** Deployment receipt plus live, existing control/native APIs. No SSH or new daemon. */
import { request } from "node:http";
import { readFile, lstat } from "node:fs/promises";
import { QWEN_CODEX_PIN, type QwenCountQualification } from "./codex-qwen.js";
import { QwenAdmissionError, admissionContext, admissionReason, emitAdmission, type QwenAdmissionContext, type QwenAdmissionDiagnostic, type QwenAdmissionObserver, type QwenAdmissionReason } from "./codex-admission.js";

export const QWEN_SOURCE_PIN = Object.freeze({
  image: "sha256:0aa2afe62c04fdd4f06a38229e6941cb1e47f6b7c0863698b708f299d4f15ddf",
  adapterSha256: "e507ed81d1e3954afea1d31eb9f0bc7ef7ab8b9a76bb571499e1a5f9c53c7da4",
  pairAdapterSha256: "7e5ca90a8ede7be7ab1aa0a5cad669869d2c86385d6529680a32f585f850b77c",
});
export interface QwenDeploymentReceipt {
  schema: 1 | 2;
  source: typeof QWEN_CODEX_PIN & typeof QWEN_SOURCE_PIN;
  /** v2 pins immutable reviewed owner/profile policy, never a prior boot. */
  ownerPolicy?: typeof QWEN_OWNER_POLICY;
  nodeUrl?: string;
  lanes: Record<string, {
    controlUrl: string; controlSlot: string; nativeBaseUrl: string; deploymentId: string;
    activeIdentity?: string; generation?: number; containerId?: string; startedAt?: string;
    profileSha256?: string; gpuUuid?: string; serviceId?: string;
  }>;
}
// The existing authenticated owner verifies these pinned files, full launch
// argv/mounts/image/GPU UUID and acceptance source closure before endpoint.ready.
// A changed protected owner source requires root review, not a new runtime ID.
export const QWEN_OWNER_POLICY = Object.freeze({
  concurrentProfilesSha256: "4b597865ea5fabfdb27ca91c331c60de01a4a68b89590ebdb96f462ce52cbc8d",
  modelManifestSha256: "fb62b2689a4c57aa1265b1262830c8d0e3983061c9674640ec9704ce603a44be",
  controlAdapterSha256: "127f1e7123f7126ac37cd0308f76ac0acec9df463435b880fc874c0dd602a55a",
});
export const QWEN_REVIEWED_LANES = Object.freeze({
  "qwen3.8-27b-gpu0": Object.freeze({ controlSlot: "glm", serviceId: "qwen-gpu0",
    controlUrl: "http://10.156.100.60:30000/control/v1/status/glm", nativeBaseUrl: "http://10.156.100.60:30002/v1",
    deploymentId: "qwen38-27b-q0-480000-yarn4-bf16kv", profileSha256: "7c2587d74e8f4654574c74d8b6e955dac1db9a185fc1c0201bacee92b3ecffe4",
    gpuUuid: "GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237" }),
  "qwen3.8-27b": Object.freeze({ controlSlot: "qwen", serviceId: "qwen-gpu1",
    controlUrl: "http://10.156.100.60:30000/control/v1/status/qwen", nativeBaseUrl: "http://10.156.100.60:30004/v1",
    deploymentId: "qwen38-27b-q1-server-480000-yarn4-bf16kv", profileSha256: "8c717c154e8e2c84feb3ef9de83939ed9f597f5fbce0c0f325f5858ce1a8f0b3",
    gpuUuid: "GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528" }),
});
export function qwenPolicyReceipt(): QwenDeploymentReceipt {
  return { schema: 2, source: { ...QWEN_CODEX_PIN, ...QWEN_SOURCE_PIN }, ownerPolicy: QWEN_OWNER_POLICY,
    nodeUrl: "http://10.156.100.60:30008/control/v1/node/status", lanes: structuredClone(QWEN_REVIEWED_LANES) };
}
const fail = (reason: QwenAdmissionReason = "receipt_policy"): never => { throw new QwenAdmissionError(reason); };
const hex = (v: unknown) => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
export function validateQwenReceipt(value: unknown): QwenDeploymentReceipt {
  const v = value as QwenDeploymentReceipt;
  if (!v || ![1, 2].includes(v.schema) || !v.source || !v.lanes || !Object.keys(v.lanes).length) fail();
  for (const [key, expected] of Object.entries({ ...QWEN_CODEX_PIN, ...QWEN_SOURCE_PIN }))
    if ((v.source as any)[key] !== expected) fail();
  for (const [alias, lane] of Object.entries(v.lanes)) {
    if (!/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/.test(alias) || Object.hasOwn(Object.prototype,alias) || !lane) fail();
    if (v.schema === 1 && (!hex(lane.activeIdentity) || !hex(lane.containerId) ||
      !Number.isSafeInteger(lane.generation) || Number(lane.generation) < 0 ||
      typeof lane.startedAt !== "string" || !Number.isFinite(Date.parse(lane.startedAt)) ||
      !["glm", "qwen"].includes(lane.controlSlot) || !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/.test(lane.deploymentId))) fail();
    if (v.schema === 2) {
      if (!Object.hasOwn(QWEN_REVIEWED_LANES, alias) || v.nodeUrl !== "http://10.156.100.60:30008/control/v1/node/status" ||
          !v.ownerPolicy || Object.entries(QWEN_OWNER_POLICY).some(([k, expected]) => (v.ownerPolicy as any)[k] !== expected)) fail();
      const expected = QWEN_REVIEWED_LANES[alias as keyof typeof QWEN_REVIEWED_LANES];
      if (Object.keys(lane).length !== Object.keys(expected).length || Object.entries(expected).some(([k, value]) => (lane as any)[k] !== value)) fail();
    }
    for (const [address, pathname] of [[lane.controlUrl, `/control/v1/status/${lane.controlSlot}`], [lane.nativeBaseUrl, "/v1"]]) {
      let url: URL; try { url = new URL(address!); } catch { return fail(); }
      if (url.protocol !== "http:" || url.username || url.password || url.search || url.hash || url.pathname !== pathname ||
        !/^(?:10\.|127\.|192\.168\.|172\.(?:1[6-9]|2[0-9]|3[01])\.)[0-9.]+$/.test(url.hostname)) fail();
    }
  }
  return structuredClone(v);
}
export async function loadQwenReceipt(file: string): Promise<QwenDeploymentReceipt> {
  const st = await lstat(file);
  if (!st.isFile() || st.isSymbolicLink() || (st.mode & 0o022) !== 0 ||
      ![0, process.getuid?.()].includes(st.uid) || st.size > 32768) fail();
  return validateQwenReceipt(JSON.parse(await readFile(file, "utf8")));
}
export async function boundedControlGet(url: string, key: string, signal?: AbortSignal): Promise<any> {
  // Control rejects browser Sec-Fetch headers. Use the existing host HTTP style,
  // no browser fetch metadata, redirects, pooled connection or ambient proxy.
  return new Promise((resolve, reject) => {
    const req = request(url, { method: "GET", agent: false, headers: { authorization: `Bearer ${key}`, accept: "application/json" }, signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(30000)]) : AbortSignal.timeout(30000) }, response => {
      const chunks: Buffer[] = []; let size = 0;
      response.on("data", (chunk: Buffer) => { size += chunk.length; if (size > 512 * 1024) { response.destroy(); reject(Error("Bounded Qwen identity response exceeded")); } else chunks.push(chunk); });
      response.on("error", () => reject(Error("Qwen identity transport unavailable")));
      response.on("end", () => {
        if (response.statusCode !== 200) { reject(Error("Qwen identity HTTP unavailable")); return; }
        try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf8"))); } catch { reject(Error("Invalid Qwen identity response")); }
      });
    });
    req.on("error", () => reject(Error("Qwen identity transport unavailable"))); req.end();
  });
}
export function createProductionQwenVerifier(receiptValue: unknown, credentials: { controlKey: string; inferenceKey: string },
  get: (url: string, key: string) => Promise<any> = boundedControlGet, now: () => number = Date.now,
  observer?: QwenAdmissionObserver) {
  const receipt = validateQwenReceipt(receiptValue);
  return async (alias: string, context: QwenAdmissionContext = admissionContext("admission")): Promise<QwenCountQualification> => {
    if (!Object.hasOwn(receipt.lanes, alias)) return fail();
    const pin = receipt.lanes[alias] ?? fail();
    const stage = async <T>(step: QwenAdmissionDiagnostic["step"], work: () => Promise<T>): Promise<T> => {
      const start = performance.now();
      try {
        const result = await work();
        emitAdmission(observer, { schema: 1, ...context, lane: alias, step, outcome: "pass", reason: "ok", elapsedMs: performance.now() - start });
        return result;
      } catch (error) {
        emitAdmission(observer, { schema: 1, ...context, lane: alias, step, outcome: "reject", reason: admissionReason(error), elapsedMs: performance.now() - start });
        throw error;
      }
    };
    const read = async (url: string, key: string) => {
      try { const value = await get(url, key); if (!value || typeof value !== "object") return fail("transport"); return value; }
      catch (error) { if (error instanceof QwenAdmissionError) throw error; return fail("transport"); }
    };
    const fresh = (x: any) => x?.state === "ok" && x.freshness === "fresh" && Number.isFinite(x.age_ms) && x.age_ms >= 0 && x.age_ms <= 15000 &&
      Number.isFinite(Date.parse(x.observed_at)) && now() - Date.parse(x.observed_at) >= -2000 && now() - Date.parse(x.observed_at) <= 15000;
    const identity = async (phase: "before" | "after") => {
      const v = await stage(`control_${phase}`, async () => {
        // Historical slot "glm" owns Qwen0; no lifecycle switch is performed.
        const v = await read(pin.controlUrl, credentials.controlKey);
        const age = now() / 1000 - v.observed_at;
        if (v.schema_version !== 2 || v.slot !== pin.controlSlot) fail("control_schema");
        if (v.selected !== pin.deploymentId || v.observed_deployment !== pin.deploymentId) fail("selected_profile");
        if (v.desired !== "running" || v.container_running !== true || v.observation_available !== true) fail("runtime_state");
        if (v.storage_available !== true || v.state_persisted !== true) fail("storage_state");
        if (v.generation_current !== true || !Number.isSafeInteger(v.generation) || v.generation < 0 ||
            (receipt.schema === 1 && v.generation !== pin.generation)) fail("generation");
        if (!hex(v.active_identity) || (receipt.schema === 1 && v.active_identity !== pin.activeIdentity)) fail("runtime_identity");
        if (v.freshness !== "fresh" || !Number.isFinite(age) || age < -2 || age > 15) fail("freshness");
        if (v.mutation_busy !== false || v.current_operation !== null) fail("operation_pending");
        if (v.endpoint?.base_url !== pin.nativeBaseUrl || v.endpoint?.served_model !== alias ||
            v.endpoint?.authentication_required !== true) fail("endpoint_policy");
        if (receipt.schema === 2 && (v.observed !== "ready" || v.endpoint.ready !== true)) fail("owner_ready");
        return v;
      });
      if (receipt.schema === 1) return `${v.active_identity}:${v.generation}:${pin.containerId}:${pin.startedAt}`;
      return stage(`node_${phase}`, async () => {
        const node = await read(receipt.nodeUrl!, credentials.controlKey);
        if (node.schema_version !== 1 || node.node_id !== "ai-vm") fail("node_schema");
        if (typeof node.boot_id !== "string" || !/^[a-f0-9-]{36}$/.test(node.boot_id)) fail("boot_identity");
        if (!fresh(node)) fail("freshness");
        const service = Array.isArray(node.services) ? node.services.filter((s: any) => s?.service_id === pin.serviceId) : [];
        if (service.length !== 1) fail("service_identity");
        const s = service[0];
        if (!fresh(s)) fail("freshness");
        if (!Number.isSafeInteger(s.generation)) fail("generation");
        if (s.ready !== true) fail("owner_ready");
        if (s.hardware_latched !== false) fail("hardware_state");
        if (s.deployment_id !== pin.deploymentId || s.model_alias !== alias) fail("selected_profile");
        if (s.configured_context_tokens !== 480000) fail("token_capacity");
        if (JSON.stringify(s.required_gpu_uuids) !== JSON.stringify([pin.gpuUuid])) fail("hardware_state");
        return `${node.boot_id}:${v.active_identity}:${v.generation}:${s.generation}`;
      });
    };
    const before = await identity("before");
    await stage("native", async () => {
      const v = await read(new URL("/server_info", pin.nativeBaseUrl).href, credentials.inferenceKey);
      if (v.status !== "ready") fail("runtime_state");
      if (v.context_length !== 480000 || v.max_total_tokens !== 480000 || v.max_total_num_tokens !== 480000) fail("token_capacity");
      if (v.version !== "0.5.19" || v.served_model_name !== alias || v.max_running_requests !== 1 ||
          v.default_chat_template_kwargs?.enable_thinking !== false || v.tool_call_parser !== "qwen3_coder" || v.reasoning_parser !== "qwen3") fail("native_profile");
    });
    if (await identity("after") !== before) fail("identity_changed");
    return { ...QWEN_CODEX_PIN, alias, instanceId: before };
  };
}
