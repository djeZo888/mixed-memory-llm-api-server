// SPDX-License-Identifier: MIT
export function divider(input: number, upper: number, lower: number): number {
  if (![input, upper, lower].every(Number.isFinite) || upper <= 0 || lower <= 0) {
    throw new RangeError('Expected finite input and positive resistances');
  }
  return input * lower / (upper + lower);
}
