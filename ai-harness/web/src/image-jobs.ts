import type { ImageJob } from './types';

export const imageJobActive = (job: ImageJob) =>
  ['awaiting_approval', 'queued', 'running', 'saving'].includes(job.state);
const validRevision = (job: ImageJob) => Number.isSafeInteger(job.revision) && job.revision >= 1;

// Persisted revisions order GET, SSE and POST acknowledgements alike. State names
// are not an ordering: known non-admission may requeue a running job. Equal
// revisions are immutable duplicate records, and cannot change the stored job.
export function mergeImageJobs(current: ImageJob[], incoming: ImageJob[], sessionId: string) {
  const jobs = new Map(
    current
      .filter((job) => job.sessionId === sessionId && validRevision(job))
      .map((job) => [job.id, job]),
  );
  for (const job of incoming) {
    if (job.sessionId !== sessionId || !validRevision(job)) continue;
    const previous = jobs.get(job.id);
    if (previous && (previous.runId !== job.runId || job.revision <= previous.revision)) continue;
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
