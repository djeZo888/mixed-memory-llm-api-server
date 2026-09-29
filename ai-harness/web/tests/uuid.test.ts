import { afterEach, expect, it, vi } from 'vitest';
import { secureUUID } from '../src/uuid';

afterEach(() => vi.unstubAllGlobals());

it('uses the native secure-context UUID API when available', () => {
  const randomUUID = vi.fn(() => 'a3902d29-e815-49bc-bbe8-83bbe9f2fa4c');
  vi.stubGlobal('crypto', { randomUUID });
  expect(secureUUID()).toBe('a3902d29-e815-49bc-bbe8-83bbe9f2fa4c');
  expect(randomUUID).toHaveBeenCalledOnce();
});

it('sets UUID v4 version and variant while retaining cryptographic random bytes', () => {
  const getRandomValues = vi.fn((bytes: Uint8Array) => bytes.fill(0xff));
  vi.stubGlobal('crypto', { getRandomValues });
  expect(secureUUID()).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff');
  expect(getRandomValues).toHaveBeenCalledOnce();
});

it('fails closed without browser cryptographic randomness', () => {
  vi.stubGlobal('crypto', undefined);
  expect(secureUUID).toThrow('Secure random IDs are unavailable');
});
