/** Bound observation even when a host adapter ignores AbortSignal. This is not settlement proof. */
export function technicalVisionWithinSignal<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const abort = () => reject(new Error("observation ended"));
    if (signal.aborted) { promise.catch(() => {}); reject(new Error("observation ended")); return; }
    signal.addEventListener("abort", abort, { once: true });
    promise.then(resolve, reject).finally(() => signal.removeEventListener("abort", abort));
  });
}
