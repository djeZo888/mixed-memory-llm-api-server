import type { ImageOperation } from './types';

export interface ImageProfile {
  operation: ImageOperation;
  size: string;
  references: number;
  transparent: false;
  evidence_sha256: string;
  native_size?: string;
  crop_bottom?: number;
}
export interface ImageCapabilities {
  model?: string;
  ready: boolean;
  admitting: boolean;
  busy: boolean;
  profiles: ImageProfile[];
}
const object = (value: unknown): Record<string, unknown> | undefined =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
const size = (value: unknown): value is string =>
  typeof value === 'string' && /^[1-9]\d*x[1-9]\d*$/.test(value);

// Parse the unchanged upstream profile array. Absent or malformed edit records
// never advertise editing, and generation profiles cannot enable editing.
export function imageCapabilities(value: unknown): ImageCapabilities {
  const input = object(value);
  const result: ImageCapabilities = {
    ready: input?.ready === true,
    admitting: input?.admitting === true,
    busy: input?.busy === true,
    profiles: [],
  };
  if (typeof input?.model === 'string') result.model = input.model;
  if (!Array.isArray(input?.profiles)) return result;
  for (const raw of input.profiles) {
    const profile = object(raw);
    if (
      !profile ||
      !['generation', 'edit'].includes(String(profile.operation)) ||
      !size(profile.size) ||
      !Number.isSafeInteger(profile.references) ||
      Number(profile.references) < 0 ||
      profile.transparent !== false ||
      typeof profile.evidence_sha256 !== 'string' ||
      !/^[a-f\d]{64}$/i.test(profile.evidence_sha256)
    )
      continue;
    result.profiles.push({
      operation: profile.operation as ImageOperation,
      size: profile.size,
      references: Number(profile.references),
      transparent: false,
      evidence_sha256: profile.evidence_sha256,
      ...(size(profile.native_size) ? { native_size: profile.native_size } : {}),
      ...(Number.isSafeInteger(profile.crop_bottom) && Number(profile.crop_bottom) >= 0
        ? { crop_bottom: Number(profile.crop_bottom) }
        : {}),
    });
  }
  return result;
}
export const editAvailable = (capabilities: ImageCapabilities | null, count = 1) =>
  capabilities?.profiles.some(
    (profile) => profile.operation === 'edit' && profile.references === count,
  ) === true;
// A draft can collect references toward a qualified count without claiming
// qualification for every intermediate count.
export const canStageEditReference = (capabilities: ImageCapabilities | null, count = 1) =>
  capabilities?.profiles.some(
    (profile) => profile.operation === 'edit' && profile.references >= count,
  ) === true;
export const imageReferencesAvailable = (capabilities: ImageCapabilities | null) =>
  capabilities?.profiles.some((profile) => profile.references > 0) === true;
