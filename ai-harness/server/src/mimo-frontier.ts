/** Narrow MiMo integration contract; all production evidence is host-owned.
 * Candidate JSON never proves native identity, allocation or settlement. */
import { constants, lstatSync, openSync, fstatSync, readFileSync, closeSync, realpathSync } from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import type { FrontierRecord } from './frontier.js';
import { MIMO_MODEL, type MimoBackendIdentity, type MimoQualification, validateMimoQualification } from './mimo.js';
export const MIMO_URL = 'http://10.156.100.60:30012/v1';
export const MIMO_PRODUCTION_OUTPUT = 65536;
export interface MimoFrontierOptions {
  provider: 'mimo';
  contextWindow: number;
  qualification: MimoQualification;
  capacity: { published: 1048576; configured: number; allocated: number; occupiedTested: number };
  upstreamKey: string | (() => string | Promise<string>);
  observe: (signal: AbortSignal) => Promise<MimoBackendIdentity>;
  /** Request-local current owner capsule; production must not replay receipt IDs
   * as observations after a reboot/restart. Existing admission owns this call. */
  current?: (signal: AbortSignal) => Promise<{
    qualification: MimoQualification;
    observe: (signal: AbortSignal) => Promise<MimoBackendIdentity>;
  }>;
  /** Root/W1 qualification of the pinned one-slot serial scheduling contract.
   * Allows normal next-request admission, never process/model switching. */
  serialCompletionQualified: true;
  onRequestState: (record: FrontierRecord) => void;
  fixtureUrl?: string;
  fixtureQueueTimeoutMs?: number;
}
export function mimoUrl(options: MimoFrontierOptions): string {
  if (!options.fixtureUrl) {
    if (options.fixtureQueueTimeoutMs !== undefined) throw Error('Fixture clock without fixture');
    return MIMO_URL;
  }
  const u = new URL(options.fixtureUrl);
  if (u.protocol !== 'http:' || u.hostname !== '127.0.0.1' || u.username || u.password || u.search || u.hash || u.pathname !== '/v1') throw Error('Invalid MiMo fixture URL');
  return u.href.replace(/\/$/, '');
}
/** Nonsecret root-owned receipt, no links or writable ancestry. Read from one
 * bounded descriptor; immutable qualification is pinned by reviewed release hash. */
export function readMimoEvidence(file: string): { text: string; value: any } {
  if (!path.isAbsolute(file) || realpathSync(file) !== file) throw Error('Unsafe evidence path');
  for (let p = path.dirname(file);; p = path.dirname(p)) {
    const s = lstatSync(p);
    if (!s.isDirectory() || s.uid !== 0 || (s.mode & 0o022)) throw Error('Unsafe evidence ancestry');
    if (p === '/') break;
  }
  const before = lstatSync(file);
  if (!before.isFile() || before.uid !== 0 || before.nlink !== 1 || (before.mode & 0o022) || before.size > 65536) throw Error('Unsafe evidence file');
  const fd = openSync(file, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const s = fstatSync(fd);
    if (s.ino !== before.ino || s.dev !== before.dev || s.size !== before.size) throw Error('Changed evidence');
    const text = readFileSync(fd, 'utf8');
    if (Buffer.byteLength(text) > 65536) throw Error('Oversized evidence');
    return { text, value: JSON.parse(text) };
  } finally { closeSync(fd); }
}
export interface MimoNativePins {
  buildInfo: string;
  modelPath: string;
  chatTemplateSha256: string;
  toolTemplateSha256: string | null;
}
const sha = (s: string) => createHash('sha256').update(s).digest('hex');
/** Runtime fields only. Artifact/process provenance remains static qualification,
 * not invented native attestation. No restart/switch while this owner is active. */
export function observeMimoNative(props: any, slots: any, q: MimoQualification, pins: MimoNativePins): MimoBackendIdentity {
  if (props?.model_alias !== MIMO_MODEL || props?.build_info !== pins.buildInfo || props?.model_path !== pins.modelPath ||
    props?.is_sleeping !== false || props?.total_slots !== 1 || props?.default_generation_settings?.n_ctx !== q.identity.actualSlotContext ||
    typeof props?.chat_template !== 'string' || sha(props.chat_template) !== pins.chatTemplateSha256 ||
    (props.chat_template_tool_use === undefined ? null : typeof props.chat_template_tool_use === 'string' ? sha(props.chat_template_tool_use) : 'invalid') !== pins.toolTemplateSha256 ||
    props?.modalities?.vision !== false || props?.modalities?.video !== false || props?.modalities?.audio !== false ||
    !Array.isArray(slots) || slots.length !== 1 || slots[0]?.id !== 0 || slots[0]?.n_ctx !== q.identity.actualSlotContext || slots[0]?.speculative !== false ||
    typeof slots[0]?.is_processing !== 'boolean' || Object.hasOwn(slots[0], 'prompt') || Object.hasOwn(slots[0], 'generated')) throw Error('MiMo native identity/capacity mismatch');
  return q.identity;
}
export async function nativeJson(url: string, key: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { redirect: 'error', headers: { authorization: `Bearer ${key}` }, signal });
  if (!response.ok || !response.body) { await response.body?.cancel(); throw Error('MiMo observation unavailable'); }
  const reader = response.body.getReader(); let bytes = 0; const chunks: Uint8Array[] = [];
  try { for (;;) { const r = await reader.read(); if (r.done) break; bytes += r.value.byteLength; if (bytes > 1024 * 1024) throw Error('Oversized MiMo observation'); chunks.push(r.value); } }
  finally { await reader.cancel().catch(() => {}); }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks)));
}
export function mimoObserver(q: MimoQualification, pins: MimoNativePins, key: MimoFrontierOptions['upstreamKey']) {
  return async (signal: AbortSignal): Promise<MimoBackendIdentity> => {
    const credential = typeof key === 'function' ? await key() : key;
    if (!credential || !/^[\x21-\x7e]+$/.test(credential)) throw Error('Invalid MiMo credential');
    const bounded = AbortSignal.any([signal, AbortSignal.timeout(15000)]);
    const base = MIMO_URL.replace(/\/v1$/, '');
    const props = await nativeJson(`${base}/props`, credential, bounded);
    const slots = await nativeJson(`${base}/slots`, credential, bounded);
    return observeMimoNative(props, slots, q, pins);
  };
}
export function validateMimoIntegration(value: any): { qualification: MimoQualification; capacity: MimoFrontierOptions['capacity']; nativePins: MimoNativePins } {
  const qualification = validateMimoQualification(value?.qualification);
  const c = value?.capacity;
  if (value?.serviceId !== MIMO_MODEL || value?.privatePort !== 30012 || value?.full17ToolRosterQualified !== true ||
    value?.strictNestedSchemasQualified !== true || value?.serialCompletionQualified !== true ||
    c?.published !== 1048576 || !Number.isSafeInteger(c?.configured) || c.configured < qualification.identity.actualSlotContext ||
    c?.allocated !== qualification.identity.actualSlotContext || !Number.isSafeInteger(c?.occupiedTested) || c.occupiedTested < 1 || c.occupiedTested >= c.allocated) throw Error('MiMo integration unqualified');
  const pins = value?.nativePins;
  if (typeof pins?.buildInfo !== 'string' || !pins.buildInfo || typeof pins?.modelPath !== 'string' || !pins.modelPath ||
    !/^[a-f0-9]{64}$/.test(pins?.chatTemplateSha256) || pins.chatTemplateSha256 !== qualification.identity.loadedTemplateSha256 || !(pins?.toolTemplateSha256 === null || /^[a-f0-9]{64}$/.test(pins?.toolTemplateSha256))) throw Error('MiMo native pins missing');
  return { qualification, capacity: Object.freeze({ ...c }), nativePins: Object.freeze({ ...pins }) };
}
