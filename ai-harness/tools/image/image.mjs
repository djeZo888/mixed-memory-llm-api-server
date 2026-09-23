// SPDX-License-Identifier: MIT
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { z } from 'zod';

export const GATEWAY = 'http://10.0.2.2:8081/v1';
export const LIMITS = Object.freeze({ budgetMs: 50 * 60_000, requestMs: 30_000, bodyBytes: 256 * 1024, stdioBytes: 128 * 1024, prompt: 16_000, references: 16 });
const states = new Set(['awaiting_approval', 'queued', 'running', 'saving', 'completed', 'failed', 'cancelled', 'interrupted']);
const terminal = new Set(['completed', 'failed', 'cancelled', 'interrupted']);
const controls = /[\p{Cc}\p{Cf}]/u;
const identifier = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/u.test(value);
const sizeValue = value => typeof value === 'string' && /^[1-9]\d{0,4}x[1-9]\d{0,4}$/u.test(value);
export function relativePath(value) {
  return typeof value === 'string' && value.length > 0 && value.length <= 1024 && !controls.test(value)
    && !/[\\:%?#]/u.test(value) && !value.startsWith('/')
    && value.split('/').every(part => part && part !== '.' && part !== '..' && part !== '~');
}
const reference = z.union([
  z.object({ fileId: z.string().refine(identifier, 'Use a current-session file ID') }).strict(),
  z.object({ workspacePath: z.string().refine(relativePath, 'Use an anchored relative workspace path') }).strict(),
]);
const fields = {
  prompt: z.string().trim().min(1).max(LIMITS.prompt).refine(value => !/[\p{Cf}\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/u.test(value), 'Invalid prompt characters'),
  size: z.string().refine(sizeValue, 'Use a supported WIDTHxHEIGHT size').optional(),
  seed: z.number().int().min(0).max(Number.MAX_SAFE_INTEGER).optional(),
};
export const capabilitiesInput = z.object({}).strict();
export const generateInput = z.object({ ...fields, references: z.array(reference).max(LIMITS.references).optional() }).strict();
export const editInput = z.object({ ...fields, references: z.array(reference).min(1).max(LIMITS.references) }).strict();

export function configuredToken(env) {
  const value = env.AI_HARNESS_GATEWAY_TOKEN;
  if ((env.AI_HARNESS_GATEWAY_URL !== undefined && env.AI_HARNESS_GATEWAY_URL !== GATEWAY)
      || typeof value !== 'string' || value.length < 16 || value.length > 4096 || controls.test(value)) {
    throw new Error('Missing or invalid session gateway configuration.');
  }
  return value;
}

export class ImageError extends Error {
  constructor(code, message, detail = {}) { super(message); this.name = 'ImageError'; this.code = code; this.detail = detail; }
}

// Only explicitly selected public metadata crosses the gateway/tool boundary.
// Never spread upstream objects or echo fetch/JSON/validation exceptions.
function publicText(value, token, max = 600) {
  if (typeof value !== 'string') return undefined;
  return value.split(token).join('[redacted]')
    .replace(/(?:data:|https?:\/\/|file:\/\/|Bearer\s+)\S+/giu, '[redacted]')
    .replace(/["']?\b(?:api[ _-]?key|(?:access[ _-]?|bearer[ _-]?|approval[ _-]?)?token|secret|authorization|password)["']?\s*[:=]\s*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\S+)/giu, '[redacted]')
    .replace(/(?:[A-Za-z]:[\\/]|\\\\)[^\s,;)]+/gu, '[path omitted]')
    .replace(/(?:^|[\s=(])(?:\/[A-Za-z0-9_.~-]+){1,}(?:\/[^\s,;)]*)?/gu, ' [path omitted]')
    .replace(/[A-Za-z0-9+/=_-]{96,}/gu, '[data omitted]')
    .replace(/[\p{Cc}\p{Cf}]/gu, ' ').slice(0, max);
}
function safeId(value, token) { return identifier(value) && value.length < 96 && !value.includes(token) ? value : undefined; }
function modelName(value, token) {
  return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._/-]{0,94}$/u.test(value) && !value.includes(token) ? value : undefined;
}
function assign(target, key, value) { if (value !== undefined) target[key] = value; }
function publicReference(value, token, adjustment = false) {
  if (!value || typeof value !== 'object') return {};
  const result = {};
  for (const key of ['referenceId', 'fileId']) assign(result, key, safeId(value[key], token));
  if (typeof value.name === 'string') assign(result, 'name', publicText(value.name.split(/[\\/]/u).at(-1), token, 256));
  if (/^[a-f\d]{64}$/iu.test(value.sha256 ?? '')) result.sha256 = value.sha256;
  for (const key of adjustment ? ['width', 'height', 'workingWidth', 'workingHeight'] : ['width', 'height']) {
    if (Number.isSafeInteger(value[key]) && value[key] > 0) result[key] = value[key];
  }
  if (adjustment && value.padding && ['top', 'right', 'bottom', 'left'].every(key => Number.isSafeInteger(value.padding[key]) && value.padding[key] >= 0)) {
    result.padding = Object.fromEntries(['top', 'right', 'bottom', 'left'].map(key => [key, value.padding[key]]));
  }
  return result;
}
export function publicError(value, token, fallback = 'IMAGE_REQUEST_FAILED') {
  const result = { code: safeId(value?.code, token) ?? fallback, message: publicText(value?.message, token) || 'The image request failed. Check the image job card.' };
  return result;
}
export function publicJob(value, token) {
  if (!value || !safeId(value.id, token) || !states.has(value.state)
      || !['generation', 'edit'].includes(value.operation) || !Number.isSafeInteger(value.revision) || value.revision < 1) {
    throw new ImageError('INVALID_JOB_RESPONSE', 'The gateway returned an invalid image job record.');
  }
  const result = { id: value.id, revision: value.revision, operation: value.operation, state: value.state };
  for (const key of ['requestId', 'runId', 'artifactId']) assign(result, key, safeId(value[key], token));
  // Session identity and prompt are intentionally not returned to model context.
  assign(result, 'model', modelName(value.model, token));
  for (const key of ['requestedSize', 'actualSize']) if (sizeValue(value[key])) result[key] = value[key];
  for (const key of ['seed', 'elapsedMs', 'queuePosition']) {
    if (Number.isSafeInteger(value[key]) && (key === 'seed' || value[key] >= 0)) result[key] = value[key];
  }
  for (const key of ['createdAt', 'startedAt', 'finishedAt']) {
    if (typeof value[key] === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/u.test(value[key])) result[key] = value[key];
  }
  if (typeof value.cancelRequested === 'boolean') result.cancelRequested = value.cancelRequested;
  if (Array.isArray(value.references)) result.references = value.references.slice(0, LIMITS.references).map(item => publicReference(item, token));
  if (value.error) result.error = publicError(value.error, token);
  if (value.adjustment && typeof value.adjustment === 'object') {
    result.adjustment = {};
    if (sizeValue(value.adjustment.targetSize)) result.adjustment.targetSize = value.adjustment.targetSize;
    assign(result.adjustment, 'reason', publicText(value.adjustment.reason, token));
    if (Array.isArray(value.adjustment.sources)) result.adjustment.sources = value.adjustment.sources.slice(0, LIMITS.references).map(item => publicReference(item, token, true));
  }
  if (value.state === 'completed' && relativePath(value.outputPath) && !value.outputPath.includes(token)) result.outputPath = value.outputPath;
  return result;
}

// Capability field selection is deliberate: opaque backend settings/URLs and
// unknown upstream additions never reach a model, even in nested profiles.
export function publicCapabilities(value, token) {
  const invalid = () => { throw new ImageError('INVALID_CAPABILITIES', 'The gateway returned invalid image operation capabilities.'); };
  if (!value || typeof value !== 'object' || !Array.isArray(value.profiles) || value.profiles.length > 64) invalid();
  const result = {};
  for (const key of ['ready', 'admitting', 'busy']) if (typeof value[key] === 'boolean') result[key] = value[key];
  for (const key of ['state', 'model', 'runtime_revision', 'model_id', 'model_revision']) assign(result, key, modelName(value[key], token));
  if (/^sha256:[a-f\d]{64}$/iu.test(value.runtime_image_digest ?? '')) result.runtime_image_digest = value.runtime_image_digest;
  result.profiles = [];
  for (const profile of value.profiles) {
    if (!profile || !['generation', 'edit'].includes(profile.operation) || !sizeValue(profile.size)
        || !Number.isSafeInteger(profile.references) || profile.references < 0 || profile.references > LIMITS.references
        || profile.transparent !== false || !/^[a-f\d]{64}$/iu.test(profile.evidence_sha256 ?? '')) continue;
    const out = { operation: profile.operation, size: profile.size, references: profile.references, transparent: profile.transparent };
    if (/^[a-f\d]{64}$/iu.test(profile.evidence_sha256 ?? '')) out.evidence_sha256 = profile.evidence_sha256;
    if (sizeValue(profile.native_size)) out.native_size = profile.native_size;
    if (Number.isSafeInteger(profile.crop_bottom) && profile.crop_bottom >= 0) out.crop_bottom = profile.crop_bottom;
    result.profiles.push(out);
  }
  // These reviewed upstream records remain in their original shape. Sanitize
  // nested primitives without manufacturing an operations/defaults projection.
  for (const key of ['limits', 'defaults', 'masks', 'response_format', 'output_format']) assign(result, key, capabilityData(value[key], token));
  return result;
}

function capabilityData(value, token, depth = 0) {
  if (depth > 5) return undefined;
  if (value === null || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value))) return value;
  if (typeof value === 'string') return publicText(value, token);
  if (Array.isArray(value)) return value.slice(0, 64).map(item => capabilityData(item, token, depth + 1)).filter(item => item !== undefined);
  if (value && typeof value === 'object') {
    const out = {};
    for (const [key, item] of Object.entries(value).slice(0, 64)) {
      if (!/^[A-Za-z][A-Za-z0-9_]{0,63}$/u.test(key) || /(?:api.?key|token|secret|auth|password|base64|data|bytes|path|url|host)/iu.test(key)) continue;
      assign(out, key, capabilityData(item, token, depth + 1));
    }
    return out;
  }
  return undefined;
}

async function boundedJSON(response) {
  if (!/^application\/(?:[\w.-]+\+)?json(?:\s*;|$)/iu.test(response.headers.get('content-type') ?? '')) throw new ImageError('INVALID_RESPONSE', 'The image gateway did not return JSON.');
  const length = response.headers.get('content-length');
  if (length && (!/^\d+$/u.test(length) || Number(length) > LIMITS.bodyBytes)) throw new ImageError('RESPONSE_TOO_LARGE', 'Image job metadata exceeded its size limit.');
  if (!response.body) throw new ImageError('INVALID_RESPONSE', 'The image gateway returned an empty response.');
  const reader = response.body.getReader(); const parts = []; let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      total += value.byteLength;
      if (total > LIMITS.bodyBytes) throw new ImageError('RESPONSE_TOO_LARGE', 'Image job metadata exceeded its size limit.');
      parts.push(value);
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
  try {
    const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(parts, total)));
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
    return value;
  } catch { throw new ImageError('INVALID_RESPONSE', 'The image gateway returned invalid JSON metadata.'); }
}

export function createImageClient({ token, fetchImpl = fetch, now = Date.now, sleep = (ms, signal) => delay(ms, undefined, { signal }), newRequestId = randomUUID } = {}) {
  configuredToken({ AI_HARNESS_GATEWAY_TOKEN: token });
  async function request(path, method, body, signal, remaining) {
    const timeout = AbortSignal.timeout(Math.max(1, Math.min(LIMITS.requestMs, remaining)));
    const combined = AbortSignal.any([timeout, ...(signal ? [signal] : [])]);
    let response;
    try {
      response = await fetchImpl(`${GATEWAY}${path}`, {
        method, redirect: 'error', signal: combined,
        headers: { Accept: 'application/json', Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      const data = await boundedJSON(response);
      if (!response.ok) {
        const error = publicError(data.error, token);
        throw new ImageError(error.code, error.message, { ...error, httpStatus: response.status });
      }
      return data;
    } catch (error) {
      if (error instanceof ImageError) throw error;
      throw new ImageError('GATEWAY_UNAVAILABLE', 'Image gateway transport failed; no submission retry was made.');
    } finally { await response?.body?.cancel().catch(() => {}); }
  }
  async function capabilities(input = {}, { signal } = {}) {
    if (!capabilitiesInput.safeParse(input).success) throw new ImageError('INVALID_INPUT', 'image_capabilities accepts no arguments.');
    const data = await request('/image-capabilities', 'GET', undefined, signal, LIMITS.requestMs);
    return publicCapabilities(data, token);
  }
  async function invoke(operation, input, { signal, onProgress } = {}) {
    const parsed = (operation === 'edit' ? editInput : generateInput).safeParse(input);
    if (!['generation', 'edit'].includes(operation) || !parsed.success) throw new ImageError('INVALID_INPUT', 'Use prompt, optional supported size/seed, and current-session file IDs or anchored relative workspace references only.');
    if (signal?.aborted) throw new ImageError('OBSERVATION_STOPPED', 'The tool stopped before image submission.');
    const requestId = newRequestId();
    if (!identifier(requestId)) throw new ImageError('INVALID_REQUEST_ID', 'Image request identity could not be created.');
    const started = now(); const deadline = started + LIMITS.budgetMs;
    const body = { requestId, operation, ...parsed.data, ...(operation === 'generation' && !parsed.data.size ? { size: '1920x1080' } : {}) };
    let job;
    try {
      const data = await request('/image-jobs', 'POST', body, signal, deadline - now());
      job = publicJob(data.job, token);
      if (job.requestId !== requestId || job.operation !== operation) throw new ImageError('INVALID_JOB_RESPONSE', 'The gateway returned a different request identity or operation.');
    } catch (error) {
      // A response error proves no usable acceptance record, not non-admission.
      // Retain requestId for recovery and never repeat this POST, even for 429.
      const known = error instanceof ImageError && error.detail.httpStatus && error.detail.httpStatus < 500;
      return { requestId, ...(known ? {} : { submissionUncertain: true }), error: { code: error.code, message: error.message, ...error.detail },
        instruction: known ? 'Check the error and image job card before requesting another image.' : 'Submission may have been accepted. Check the existing image job card; do not resubmit this request.' };
    }
    let attempt = 0; let observationError;
    while (true) {
      if (job.state === 'awaiting_approval') return { job, instruction: 'Use the user approval card to approve or reject the exact resize/canvas adjustment. Do not submit another job or approve through a tool.' };
      if (terminal.has(job.state)) return { job };
      if (signal?.aborted || now() >= deadline) return { job, observationStopped: true,
        ...(observationError ? { error: observationError } : {}),
        instruction: 'The submitted image job survives this tool ending. Check its image job card for the result; do not resubmit. Active cancellation drains until the backend settles.' };
      // elapsedMs is server metadata, not a fabricated percentage or state.
      if (onProgress && Number.isSafeInteger(job.elapsedMs)) {
        // Transport notification completion must not extend the observation budget.
        const progressJob = job;
        Promise.resolve().then(() => onProgress(progressJob)).catch(() => {});
      }
      const waitMs = Math.min(1000 * 2 ** Math.min(attempt++, 4), 15_000, deadline - now());
      try { await sleep(waitMs, signal); } catch { continue; }
      if (signal?.aborted || now() >= deadline) continue;
      try {
        const data = await request(`/image-jobs/${encodeURIComponent(job.id)}`, 'GET', undefined, signal, deadline - now());
        const next = publicJob(data.job, token);
        if (next.id !== job.id || next.requestId !== requestId || next.operation !== operation) throw new ImageError('INVALID_JOB_RESPONSE', 'The gateway returned an unrelated image job.');
        if (next.revision > job.revision) job = next;
        observationError = undefined;
      } catch (error) {
        observationError = { code: error.code, message: error.message, ...error.detail };
        if (error.detail?.httpStatus && ![408, 429].includes(error.detail.httpStatus) && error.detail.httpStatus < 500) {
          return { job, observationStopped: true, error: observationError, instruction: 'Polling stopped. The submitted job was not cancelled. Check the existing image job card; do not resubmit.' };
        }
      }
    }
  }
  return { capabilities, invoke };
}
