/** Transport bounds only; native token admission still reserves maximum output. */
export const MAX_MESSAGE_CHARACTERS = 2_000_000;
// A separate byte bound also rejects oversized JSON escaping/metadata.
export const MAX_MESSAGE_BODY_BYTES = 8 * 1024 * 1024;
