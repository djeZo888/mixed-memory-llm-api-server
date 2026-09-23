import { useEffect, useState } from 'react';
import { imageElapsed, imageJobActive } from './image-jobs';
import type { ImageJob } from './types';

export interface ImageActions {
  decide: (jobId: string, decision: 'approve' | 'reject') => void;
  cancel: (jobId: string) => void;
  busy: (jobId: string) => boolean;
  reconnecting: boolean;
}
const stateLabels: Record<ImageJob['state'], string> = {
  awaiting_approval: 'Awaiting your approval',
  queued: 'Queued',
  running: 'Running',
  saving: 'Saving',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  interrupted: 'Interrupted',
};
export function ImageJobs({ jobs, actions }: { jobs: ImageJob[]; actions?: ImageActions }) {
  const [now, setNow] = useState(Date.now);
  const active = jobs.some(imageJobActive);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  return (
    <>
      {jobs.map((job) => {
        const busy = actions?.busy(job.id) ?? false;
        const draining = job.cancelRequested && ['running', 'saving'].includes(job.state);
        return (
          <section
            key={job.id}
            className={`image-job image-job-${job.state}`}
            aria-label={`Image job ${job.id}`}
          >
            <div className="image-job-heading">
              <strong>{job.operation === 'edit' ? 'Image edit' : 'Image generation'}</strong>
              <span role="status">
                {stateLabels[job.state]}
                {draining ? ' · Cancellation requested, draining' : ''}
              </span>
            </div>
            {actions?.reconnecting && imageJobActive(job) && (
              <p className="image-job-notice">
                Reconnecting · showing last saved state. The image job continues.
              </p>
            )}
            <dl className="image-job-metadata">
              <div>
                <dt>Elapsed</dt>
                <dd>{imageElapsed(job, now)}</dd>
              </div>
              {job.state === 'queued' && job.queuePosition != null && (
                <div>
                  <dt>Queue position</dt>
                  <dd>{job.queuePosition}</dd>
                </div>
              )}
              <div>
                <dt>{job.actualSize ? 'Output dimensions' : 'Requested dimensions'}</dt>
                <dd>{job.actualSize ?? job.requestedSize}</dd>
              </div>
              <div>
                <dt>Seed</dt>
                <dd>{job.seed}</dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd>{job.model}</dd>
              </div>
            </dl>
            {!!job.references.length && (
              <ul className="image-job-sources" aria-label="Image sources">
                {job.references.map((source, index) => (
                  <li key={`${source.sha256}:${index}`}>
                    <span>{source.name}</span> · {source.width}×{source.height}
                    {source.fileId && <small> · File {source.fileId}</small>}
                    <details>
                      <summary>Source fingerprint</summary>
                      <code>{source.sha256}</code>
                    </details>
                  </li>
                ))}
              </ul>
            )}
            {job.adjustment && (
              <div className="image-adjustment">
                <strong>
                  {job.state === 'awaiting_approval'
                    ? 'Approve the canvas change before processing'
                    : 'Canvas adjustment'}
                </strong>
                <ul aria-label="Original image dimensions">
                  {job.adjustment.sources.map((source, index) => (
                    <li key={`${source.sha256}:${index}`}>
                      {source.name}: {source.width}×{source.height}
                    </li>
                  ))}
                </ul>
                <p>
                  Proposed canvas: <strong>{job.adjustment.targetSize}</strong>
                </p>
                <p>{job.adjustment.reason}</p>
                <p>
                  Original files remain unchanged. Content is fitted with padding, without
                  stretching or cropping.
                </p>
                {job.state === 'awaiting_approval' && (
                  <div className="image-job-actions">
                    <button
                      type="button"
                      className="primary-button"
                      disabled={!actions || busy}
                      onClick={() => actions?.decide(job.id, 'approve')}
                    >
                      Approve resize
                    </button>
                    <button
                      type="button"
                      className="text-button"
                      disabled={!actions || busy}
                      onClick={() => actions?.decide(job.id, 'reject')}
                    >
                      Reject change
                    </button>
                  </div>
                )}
                {['queued', 'running', 'saving', 'completed'].includes(job.state) && (
                  <p>Canvas change approved.</p>
                )}
              </div>
            )}
            {job.state === 'awaiting_approval' && !job.adjustment && (
              <p role="alert">
                The saved adjustment is unavailable. Refresh to load the approval details.
              </p>
            )}
            {job.error && (
              <p className="run-error" role="alert">
                {job.error.message} <small>({job.error.code})</small>
              </p>
            )}
            {job.state === 'interrupted' && (
              <p>
                The job was interrupted and will not be replayed. Start a new request to try again.
              </p>
            )}
            {job.state === 'cancelled' && (
              <p>
                Image delivery cancelled.
                {job.artifactId
                  ? ' A late output was retained with its provenance in the files below.'
                  : ''}
              </p>
            )}
            {draining && (
              <p>The backend is finishing its active work. GPU cancellation is not immediate.</p>
            )}
            {imageJobActive(job) && (
              <button
                type="button"
                className="text-button"
                disabled={!actions || busy || job.cancelRequested}
                onClick={() => actions?.cancel(job.id)}
              >
                {job.cancelRequested ? 'Cancellation requested' : 'Cancel image job'}
              </button>
            )}
          </section>
        );
      })}
    </>
  );
}
