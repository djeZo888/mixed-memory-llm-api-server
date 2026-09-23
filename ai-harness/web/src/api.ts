import {
  eventTypes,
  type Attachment,
  type ImageJob,
  type ServerEvent,
  type Session,
  type Snapshot,
} from './types';

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
export const sessionPath = (id: string) => `/api/sessions/${encodeURIComponent(id)}`;
export const artifactPath = (id: string) => `/api/artifacts/${encodeURIComponent(id)}/download`;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body != null && !(init.body instanceof FormData) && !headers.has('Content-Type'))
    headers.set('Content-Type', 'application/json');
  const response = await fetch(path, {
    ...init,
    headers,
    cache: 'no-store',
  });
  const body = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      response.status,
      body?.error?.code ?? 'http_error',
      body?.error?.message ?? `Request failed (${response.status}).`,
    );
  if (body === null)
    throw new ApiError(
      response.status,
      'invalid_response',
      'The server returned an unreadable response.',
    );
  return body as T;
}
const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body) });
async function imageJobPost(path: string, body: unknown): Promise<{ job: ImageJob }> {
  const result = await post<ImageJob | { job: ImageJob }>(path, body);
  const job = result && typeof result === 'object' && 'job' in result ? result.job : result;
  if (!job || typeof job !== 'object' || !('id' in job) || typeof job.id !== 'string')
    throw new ApiError(
      200,
      'invalid_response',
      'The server returned an unreadable image job. Refresh its saved status.',
    );
  return { job: job as ImageJob };
}
export interface StreamCallbacks {
  event: (event: ServerEvent) => void;
  open: () => void;
  disconnected: () => void;
}
export interface Transport {
  health(signal?: AbortSignal): Promise<{ visionAvailable: boolean }>;
  imageCapabilities(signal?: AbortSignal): Promise<unknown>;
  list(signal?: AbortSignal): Promise<{ sessions: Session[] }>;
  snapshot(id: string, signal?: AbortSignal): Promise<Snapshot>;
  create(): Promise<{ session: Session }>;
  remove(id: string): Promise<{ status: 'deleting' | 'deleted' }>;
  send(
    id: string,
    text: string,
    attachmentIds: string[],
    imageReferences?: string[],
  ): Promise<{ runId: string }>;
  imageJobs(id: string, signal?: AbortSignal): Promise<{ jobs: ImageJob[] }>;
  approveImage(
    id: string,
    jobId: string,
    decision: 'approve' | 'reject',
  ): Promise<{ job: ImageJob }>;
  cancelImage(id: string, jobId: string): Promise<{ job: ImageJob }>;
  cancel(id: string): Promise<{ status: 'cancelling' }>;
  handoff(id: string): Promise<{ runId: string }>;
  upload(id: string, file: File): Promise<{ attachment: Attachment }>;
  stream(id: string, after: number, callbacks: StreamCallbacks): () => void;
}

export function subscribe(id: string, after: number, callbacks: StreamCallbacks): () => void {
  const source = new EventSource(`${sessionPath(id)}/events?after=${after}`);
  const receive = (raw: Event) => {
    if (!('data' in raw) || typeof raw.data !== 'string') return;
    try {
      const event = JSON.parse(raw.data) as ServerEvent;
      if (
        Number.isSafeInteger(event.id) &&
        event.id > 0 &&
        event.sessionId === id &&
        eventTypes.includes(event.type) &&
        event.data &&
        typeof event.data === 'object'
      )
        callbacks.event(event);
    } catch {
      /* Invalid frames do not advance the replay cursor. */
    }
  };
  // "message" handles ordinary envelopes and named message frames exactly once.
  for (const type of eventTypes) source.addEventListener(type, receive);
  source.onopen = callbacks.open;
  source.onerror = (event) => {
    if (!('data' in event)) callbacks.disconnected();
  };
  return () => source.close(); // Browser cleanup must never call /cancel.
}
export const api: Transport = {
  health: (signal) => request('/api/health', { signal }),
  imageCapabilities: (signal) => request('/api/image-capabilities', { signal }),
  list: (signal) => request('/api/sessions', { signal }),
  snapshot: (id, signal) => request(sessionPath(id), { signal }),
  create: () => post('/api/sessions', {}),
  remove: (id) => request(sessionPath(id), { method: 'DELETE' }),
  send: (id, text, attachmentIds, imageReferences) =>
    post(`${sessionPath(id)}/messages`, {
      text,
      attachmentIds,
      ...(imageReferences?.length ? { imageReferences } : {}),
    }),
  imageJobs: (id, signal) => request(`${sessionPath(id)}/image-jobs`, { signal }),
  approveImage: (id, jobId, decision) =>
    imageJobPost(`${sessionPath(id)}/image-jobs/${encodeURIComponent(jobId)}/approval`, {
      decision,
    }),
  cancelImage: (id, jobId) =>
    imageJobPost(`${sessionPath(id)}/image-jobs/${encodeURIComponent(jobId)}/cancel`, {}),
  cancel: (id) => post(`${sessionPath(id)}/cancel`, {}),
  handoff: (id) => post(`${sessionPath(id)}/handoff`, {}),
  upload: (id, file) => {
    const body = new FormData();
    body.append('file', file);
    return request(`${sessionPath(id)}/uploads`, { method: 'POST', body });
  },
  stream: subscribe,
};
