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
  seed: z.number().int().min(Number.MIN_SAFE_INTEGER).max(Number.MAX_SAFE_INTEGER).optional(),
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
    .replace(/["']?\b(?:api[ _-]?key|(?:access[ _-]?|bearer[ _-]?)?token|secret|authorization|password)["']?\s*[:=]\s*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\S+)/giu, '[redacted]')
    .replace(/(?:[A-Za-z]:[\\/]|\\\\)[^\s,;)]+/gu, '[path omitted]')
    .replace(/(?:^|[\s=(])(?:\/[A-Za-z0-9_.~-]+){1,}(?:\/[^\s,;)]*)?/gu, ' [path omitted]')
    .replace(/[A-Za-z0-9+/=_-]{96,}/gu, '[data omitted]')
    .replace(/[\p{Cc}\p{Cf}]/gu, ' ').slice(0, max);
}
function safeId(value, token) { return identifier(value) && value.length < 96 && !value.includes(token) ? value : undefined; }
function modelName(value, token) {
  return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._/-]{0,94}$/u.test(value) && !value.includes(token) ? value : undefined;
}
function dimensions(value) {
  if (sizeValue(value)) return value;
  if (value && Number.isSafeInteger(value.width) && Number.isSafeInteger(value.height)
      && value.width > 0 && value.width <= 99999 && value.height > 0 && value.height <= 99999) {
    return { width: value.width, height: value.height };
  }
  return undefined;
}
function assign(target, key, value) { if (value !== undefined) target[key] = value; }
function publicReference(value, token) {
  if (!value || typeof value !== 'object') return {};
  const result = {};
  for (const key of ['id', 'fileId', 'artifactId']) assign(result, key, safeId(value[key], token));
  if (typeof value.name === 'string') assign(result, 'name', publicText(value.name.split(/[\\/]/u).at(-1), token, 256));
  for (const key of ['hash', 'sha256']) if (/^[a-f\d]{64}$/iu.test(value[key] ?? '')) result[key] = value[key];
  for (const key of ['dimensions', 'size']) assign(result, key, dimensions(value[key]));
  if (Number.isSafeInteger(value.width) && Number.isSafeInteger(value.height)) {
    const pair = dimensions(value); if (pair) Object.assign(result, pair);
  }
  if (relativePath(value.workspacePath) && !value.workspacePath.includes(token)) result.workspacePath = value.workspacePath;
  return result;
}
export function publicError(value, token, fallback = 'IMAGE_REQUEST_FAILED') {
  const result = { code: safeId(value?.code, token) ?? fallback, message: publicText(value?.message, token) || 'The image request failed. Check the image job card.' };
  // Unsupported size errors must retain the authoritative supported list.
  for (const key of ['supportedSizes', 'supported_sizes']) {
    if (Array.isArray(value?.[key])) result[key] = value[key].map(dimensions).filter(Boolean).slice(0, 64);
  }
  return result;
}
export function publicJob(value, token) {
  if (!value || !safeId(value.id, token) || !states.has(value.state)
      || !['generation', 'edit'].includes(value.operation)) {
    throw new ImageError('INVALID_JOB_RESPONSE', 'The gateway returned an invalid image job record.');
  }
  const result = { id: value.id, operation: value.operation, state: value.state };
  for (const key of ['requestId', 'runId', 'artifactId']) assign(result, key, safeId(value[key], token));
  // Session identity and prompt are intentionally not returned to model context.
  assign(result, 'model', modelName(value.model, token));
  for (const key of ['requestedSize', 'actualSize']) assign(result, key, dimensions(value[key]));
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
    assign(result.adjustment, 'targetSize', dimensions(value.adjustment.targetSize));
    assign(result.adjustment, 'reason', publicText(value.adjustment.reason, token));
    if (Array.isArray(value.adjustment.sources)) result.adjustment.sources = value.adjustment.sources.slice(0, LIMITS.references).map(item => publicReference(item, token));
  }
  if (value.state === 'completed' && relativePath(value.workspacePath) && !value.workspacePath.includes(token)) result.workspacePath = value.workspacePath;
  return result;
}

// Capability field selection is deliberate: opaque backend settings/URLs and
// unknown upstream additions never reach a model, even in nested profiles.
export function publicCapabilities(value, token) {
  const invalid = () => { throw new ImageError('INVALID_CAPABILITIES', 'The gateway returned invalid image operation capabilities.'); };
  if (!value || typeof value !== 'object' || !value.operations || Array.isArray(value.operations)
      || typeof value.operations !== 'object' || !('generation' in value.operations || 'edit' in value.operations)) invalid();
  const result = { operations: {} };
  assign(result, 'model', modelName(value.model, token));
  assign(result, 'reason', publicText(value.reason, token));
  for (const key of ['available', 'opaque']) if (typeof value[key] === 'boolean') result[key] = value[key];
  assign(result, 'defaultSize', dimensions(value.defaultSize));
  for (const operation of ['generation', 'edit']) {
    const source = value.operations[operation];
    const valid = source?.available === true && Array.isArray(source.profiles) && source.profiles.length <= 64
      && source.profiles.length > 0 && source.profiles.every(profile => profile && Number.isSafeInteger(profile.referenceCount)
        && profile.referenceCount >= 0 && profile.referenceCount <= LIMITS.references && Array.isArray(profile.sizes)
        && profile.sizes.length > 0 && profile.sizes.length <= 64 && profile.sizes.every(sizeValue));
    // A missing edit qualification must not erase valid generation discovery.
    result.operations[operation] = { available: valid, profiles: valid ? source.profiles.map(profile => ({ referenceCount: profile.referenceCount, sizes: [...profile.sizes] })) : [] };
    assign(result.operations[operation], 'reason', publicText(source?.reason, token));
  }
  return result;
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
    return { capabilities: publicCapabilities(data.capabilities ?? data, token) };
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
      job = publicJob(data.job ?? data, token);
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
        const next = publicJob(data.job ?? data, token);
        if (next.id !== job.id || next.requestId !== requestId || next.operation !== operation) throw new ImageError('INVALID_JOB_RESPONSE', 'The gateway returned an unrelated image job.');
        job = next; observationError = undefined;
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
