import type { RunSnapshot, Status } from './types';

export function currentRun(runs: readonly RunSnapshot[]): RunSnapshot | undefined {
  const newestFirst = [...runs].reverse();
  return (
    newestFirst.find((run) => run.status === 'cancelling') ??
    newestFirst.find((run) => run.status === 'running') ??
    newestFirst.find((run) => run.status === 'queued')
  );
}

export function resolveStatus(status: Status, runs: readonly RunSnapshot[] = []): Status {
  // An idle aggregate can arrive between queued turns. Only known typed runs
  // fill that gap; preserve all other emitted session states, including errors.
  if (status !== 'idle') return status;
  const pending = currentRun(runs)?.status;
  return pending === 'cancelling' || pending === 'running' || pending === 'queued'
    ? pending
    : status;
}
