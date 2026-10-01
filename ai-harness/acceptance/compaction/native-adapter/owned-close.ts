/** Every caller awaits the same teardown. Setting a flag is admission closure,
 * never evidence that asynchronous producer cleanup already finished. */
export function ownedClose(operation: () => Promise<void>) {
  let completion: Promise<void> | undefined;
  return () => completion ??= (async () => { await operation(); })();
}
/** Diagnostics cannot prevent cleanup of an already acquired native/app/port
 * owner. Preserve the original failure and separately retain persistence failure. */
export async function failedBootstrap(original: unknown, diagnostic: () => Promise<void>, close: () => Promise<void>): Promise<never> {
  const failures = [original];
  try { await diagnostic(); } catch (error) { failures.push(error); }
  try { await close(); } catch (error) { failures.push(error); }
  if (failures.length === 1) throw original;
  throw new AggregateError(failures, 'bootstrap_failed_diagnostics_or_teardown_unconfirmed');
}
