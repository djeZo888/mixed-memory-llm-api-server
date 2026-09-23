import type { ImageOperation } from './types';

export interface ImageProfile {
  referenceCount: number;
  sizes: string[];
}
export interface ImageCapabilities {
  model?: string;
  operations: Partial<Record<ImageOperation, { available: boolean; profiles: ImageProfile[] }>>;
}
const object = (value: unknown): Record<string, unknown> | undefined =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;

// Keep the capability boundary narrow: absent, unknown or malformed operation
// profiles never advertise editing or substitute generation for editing.
export function imageCapabilities(value: unknown): ImageCapabilities {
  const input = object(value);
  const operations = object(input?.operations);
  const result: ImageCapabilities = { operations: {} };
  if (typeof input?.model === 'string') result.model = input.model;
  for (const operation of ['generation', 'edit'] as const) {
    const record = object(operations?.[operation]);
    if (!record || record.available !== true || !Array.isArray(record.profiles)) continue;
    const profiles: ImageProfile[] = [];
    for (const raw of record.profiles) {
      const profile = object(raw);
      if (
        !profile ||
        !Number.isSafeInteger(profile.referenceCount) ||
        Number(profile.referenceCount) < 0 ||
        !Array.isArray(profile.sizes)
      )
        continue;
      const sizes = profile.sizes.filter(
        (size): size is string => typeof size === 'string' && /^[1-9]\d*x[1-9]\d*$/.test(size),
      );
      if (sizes.length) profiles.push({ referenceCount: Number(profile.referenceCount), sizes });
    }
    if (profiles.length) result.operations[operation] = { available: true, profiles };
  }
  return result;
}
export const editAvailable = (capabilities: ImageCapabilities | null, count = 1) =>
  capabilities?.operations.edit?.profiles.some((profile) => profile.referenceCount === count) ===
  true;
// A draft may collect references toward a qualified count (for example two),
// without claiming that every intermediate count is an enabled edit operation.
export const canStageEditReference = (capabilities: ImageCapabilities | null, count = 1) =>
  capabilities?.operations.edit?.profiles.some((profile) => profile.referenceCount >= count) ===
  true;
export const imageReferencesAvailable = (capabilities: ImageCapabilities | null) =>
  Object.values(capabilities?.operations ?? {}).some((operation) =>
    operation.profiles.some((profile) => profile.referenceCount > 0),
  );
