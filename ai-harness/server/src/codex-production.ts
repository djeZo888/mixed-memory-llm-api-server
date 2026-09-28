/** Deployment receipt plus live, existing control/native APIs. No SSH or new daemon. */
import { request } from "node:http";
import { readFile, lstat } from "node:fs/promises";
import { QWEN_CODEX_PIN, type QwenCountQualification } from "./codex-qwen.js";
import { ApiError } from "./errors.js";

export const QWEN_SOURCE_PIN = Object.freeze({
  image: "sha256:0aa2afe62c04fdd4f06a38229e6941cb1e47f6b7c0863698b708f299d4f15ddf",
  adapterSha256: "e507ed81d1e3954afea1d31eb9f0bc7ef7ab8b9a76bb571499e1a5f9c53c7da4",
  pairAdapterSha256: "7e5ca90a8ede7be7ab1aa0a5cad669869d2c86385d6529680a32f585f850b77c",
});
export interface QwenDeploymentReceipt {
  schema: 1;
  source: typeof QWEN_CODEX_PIN & typeof QWEN_SOURCE_PIN;
  /** Exact independently inspected container/start/source bound to the control identity.
   * A restarted or replaced instance needs a new reviewed deployment receipt. */
  lanes: Record<string, {
    controlUrl: string; controlSlot: string; nativeBaseUrl: string; deploymentId: string;
    activeIdentity: string; generation: number; containerId: string; startedAt: string;
  }>;
}
const fail = (): never => { throw new ApiError(503, "codex_qwen_identity_unqualified", "Current Qwen identity or native allocation is not qualified"); };
const hex = (v: unknown) => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
export function validateQwenReceipt(value: unknown): QwenDeploymentReceipt {
  const v = value as QwenDeploymentReceipt;
  if (!v || v.schema !== 1 || !v.source || !v.lanes || !Object.keys(v.lanes).length) fail();
  for (const [key, expected] of Object.entries({ ...QWEN_CODEX_PIN, ...QWEN_SOURCE_PIN }))
    if ((v.source as any)[key] !== expected) fail();
  for (const [alias, lane] of Object.entries(v.lanes)) {
    if (!/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/.test(alias) || Object.hasOwn(Object.prototype,alias) || !lane || !hex(lane.activeIdentity) || !hex(lane.containerId) ||
      !Number.isSafeInteger(lane.generation) || lane.generation < 0 ||
      typeof lane.startedAt !== "string" || !Number.isFinite(Date.parse(lane.startedAt)) ||
      !["glm", "qwen"].includes(lane.controlSlot) || !/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/.test(lane.deploymentId)) fail();
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
async function boundedGet(url: string, key: string): Promise<any> {
  // Control rejects browser Sec-Fetch headers. Use the existing host HTTP style,
  // no browser fetch metadata, redirects, pooled connection or ambient proxy.
  return new Promise((resolve, reject) => {
    const req = request(url, { method: "GET", agent: false, headers: { authorization: `Bearer ${key}`, accept: "application/json" }, signal: AbortSignal.timeout(12000) }, response => {
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
  get: (url: string, key: string) => Promise<any> = boundedGet, now: () => number = Date.now) {
  const receipt = validateQwenReceipt(receiptValue);
  return async (alias: string): Promise<QwenCountQualification> => {
    if (!Object.hasOwn(receipt.lanes, alias)) return fail();
    const pin = receipt.lanes[alias] ?? fail();
    const identity = async () => {
      // Historical slot "glm" owns Qwen0; this endpoint performs no model switch.
      // adapter.py binds active_identity to immutable ID, image and StartedAt.
      const v = await get(pin.controlUrl, credentials.controlKey);
      const age = now() / 1000 - v.observed_at;
      if (v.schema_version !== 2 || v.slot !== pin.controlSlot || v.selected !== pin.deploymentId ||
          v.observed_deployment !== pin.deploymentId || v.desired !== "running" || v.container_running !== true ||
          v.observation_available !== true || v.storage_available !== true || v.state_persisted !== true ||
          v.generation_current !== true || v.generation !== pin.generation || v.active_identity !== pin.activeIdentity ||
          v.freshness !== "fresh" || !Number.isFinite(age) || age < -2 || age > 15 || v.mutation_busy !== false ||
          v.current_operation !== null || v.endpoint?.base_url !== pin.nativeBaseUrl ||
          v.endpoint?.served_model !== alias || v.endpoint?.authentication_required !== true) fail();
    };
    await identity();
    const v = await get(new URL("/server_info", pin.nativeBaseUrl).href, credentials.inferenceKey);
    if (v.status !== "ready" || v.version !== "0.5.19" || v.served_model_name !== alias ||
        v.context_length !== 480000 || v.max_total_tokens !== 480000 || v.max_total_num_tokens !== 480000 ||
        v.max_running_requests !== 1 || v.default_chat_template_kwargs?.enable_thinking !== false ||
        v.tool_call_parser !== "qwen3_coder" || v.reasoning_parser !== "qwen3") fail();
    await identity();
    return { ...QWEN_CODEX_PIN, alias, instanceId: `${pin.activeIdentity}:${pin.generation}:${pin.containerId}:${pin.startedAt}` };
  };
}
