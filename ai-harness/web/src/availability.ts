export type AvailabilityState = 'available' | 'unavailable' | 'unknown';
export interface HealthAvailability {
  qwenGpu0: AvailabilityState;
  qwenGpu1: AvailabilityState;
  image: AvailabilityState;
}
export function healthAvailability(value: unknown): HealthAvailability {
  const record = value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
  const state = (key: string): AvailabilityState =>
    record[key] === 'available' || record[key] === 'unavailable' ? record[key] : 'unknown';
  return { qwenGpu0: state('qwenGpu0'), qwenGpu1: state('qwenGpu1'), image: state('image') };
}
export function availabilityNotice(value?: HealthAvailability): string {
  const current = healthAvailability(value);
  const text = [current.qwenGpu0, current.qwenGpu1];
  const unavailable = text.filter((state) => state === 'unavailable').length;
  const messages: string[] = [];
  if (unavailable === 2) messages.push('Text service unavailable.');
  else if (unavailable === 1) messages.push('Text service is running with reduced capacity.');
  if (current.image === 'unavailable') messages.push('Image service unavailable.');
  if (text.includes('unknown') || current.image === 'unknown') messages.push('Some services are still being checked.');
  return messages.join(' ');
}
