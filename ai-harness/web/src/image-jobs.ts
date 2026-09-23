import type { ImageJob, ImageJobState } from './types';

const order: Record<ImageJobState, number> = {
  awaiting_approval: 0,
  queued: 1,
  running: 2,
  saving: 3,
  completed: 4,
  failed: 4,
  cancelled: 4,
  interrupted: 4,
};
export const imageJobActive = (job: ImageJob) => order[job.state] < 4;

// GET and SSE can race. A stale persisted read may update queue metadata but
// must not rewind dispatch or settlement. Ordered persisted SSE is authoritative:
// known non-admission may legitimately requeue a dispatched job. Cancellation
// intent and immutable run ownership remain preserved in either path.
export function mergeImageJobs(
  current: ImageJob[],
  incoming: ImageJob[],
  sessionId: string,
  orderedEvent = false,
) {
  const jobs = new Map(
    current.filter((job) => job.sessionId === sessionId).map((job) => [job.id, job]),
  );
  for (const job of incoming) {
    if (job.sessionId !== sessionId) continue;
    const previous = jobs.get(job.id);
    if (
      previous &&
      (previous.runId !== job.runId || (!orderedEvent && order[job.state] < order[previous.state]))
    )
      continue;
    if (
      !orderedEvent &&
      previous &&
      order[previous.state] === 4 &&
      previous.state !== job.state &&
      !(Date.parse(job.finishedAt ?? '') > Date.parse(previous.finishedAt ?? ''))
    ) {
      // A cancelled delivery may acquire a retained artifact while draining,
      // without allowing an older response to revive a terminal state.
      jobs.set(job.id, { ...previous, ...(job.artifactId ? { artifactId: job.artifactId } : {}) });
      continue;
    }
    jobs.set(job.id, {
      ...job,
      ...(previous?.artifactId && !job.artifactId ? { artifactId: previous.artifactId } : {}),
      ...(previous?.actualSize && !job.actualSize ? { actualSize: previous.actualSize } : {}),
      cancelRequested: job.cancelRequested || previous?.cancelRequested === true,
    });
  }
  return [...jobs.values()];
}

export function imageElapsed(job: ImageJob, now: number): string {
  const elapsed = imageJobActive(job)
    ? now - Date.parse(job.createdAt)
    : (job.elapsedMs ??
      (job.finishedAt ? Date.parse(job.finishedAt) : NaN) - Date.parse(job.createdAt));
  if (!Number.isFinite(elapsed) || elapsed < 0) return 'Unknown';
  const seconds = Math.floor(elapsed / 1000);
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}
