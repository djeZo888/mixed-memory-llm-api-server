import { readSubmission, saveSubmission, acknowledgeSubmission, forgetSubmission, submissionRejected, type PendingSubmission } from './submissions';
import type { CodexHealth, EngineKind } from './types';
import { api, ApiError, type Transport } from './api';
import { healthAvailability, type HealthAvailability } from './availability';
import { applyEvent, reconcileSnapshot } from './state';
import { imageJobActive, mergeImageJobs } from './image-jobs';
import {
  canStageEditReference,
  imageCapabilities,
  imageReferencesAvailable,
  type ImageCapabilities,
} from './image-capabilities';
import { uploadKey, uploadProblem } from './uploads';
import type { Attachment, ServerEvent, Session, Snapshot, Thread } from './types';

export interface ViewState {
  sessions: Session[];
  selectedId: string | null;
  thread: Thread | null;
  loading: boolean;
  listLoading: boolean;
  error: string | null;
  connection: 'connecting' | 'connected' | 'reconnecting' | 'offline';
  visionAvailable: boolean;
  healthLoaded: boolean;
  codexAvailable?: boolean;
  codexHealth?: CodexHealth;
  serviceAvailability?: HealthAvailability;
  imageCapabilities: ImageCapabilities | null;
  imageCapabilitiesLoaded: boolean;
  imageJobsError: string | null;
  busy: Record<string, boolean>;
  attachments: Record<string, Attachment[]>;
  imageReferences: Record<string, Attachment[]>;
  submitted: Record<string, string[] | undefined>;
  pendingSubmissions: Record<string, PendingSubmission | undefined>;
}
export interface UploadUpdate {
  file: File;
  status: 'uploading' | 'ready' | 'error';
  error?: string;
}
const messageOf = (error: unknown) =>
  error instanceof Error ? error.message : 'The request could not be completed.';
export const busyKey = (action: string, id = '') => `${action}:${id}`;
// Opaque server IDs may match Object.prototype names.
export const lookup = <T>(record: Record<string, T>, id: string): T | undefined =>
  Object.hasOwn(record, id) ? record[id] : undefined;
export const runPending = (status: string) => ['queued', 'running', 'cancelling'].includes(status);
export function pendingRunIds(state: ViewState, id: string): string[] {
  const runs = state.thread?.session.id === id ? state.thread.runs : [];
  const terminal = new Set(runs.filter((run) => !runPending(run.status)).map((run) => run.id));
  return [
    ...new Set([
      ...(lookup(state.submitted, id) ?? []).filter((runId) => !terminal.has(runId)),
      ...runs.filter((run) => runPending(run.status)).map((run) => run.id),
    ]),
  ];
}
export const codexSpecialistAvailable = (state: ViewState, count = 1) =>
  state.codexAvailable === true && state.codexHealth?.imageToolEnabled === true &&
  canStageEditReference(state.imageCapabilities, count);

export class HarnessStore {
  private state: ViewState = {
    sessions: [],
    selectedId: null,
    thread: null,
    loading: false,
    listLoading: true,
    error: null,
    connection: 'offline',
    visionAvailable: false,
    healthLoaded: false,
    imageCapabilities: null,
    imageCapabilitiesLoaded: false,
    imageJobsError: null,
    busy: {},
    attachments: {},
    imageReferences: {},
    submitted: {},
    pendingSubmissions: {},
  };
  private listeners = new Set<() => void>();
  private generation = 0;
  private listGeneration = 0;
  private closed = false;
  private lifetime = 0;
  private capabilityGeneration = 0;
  private completedRuns = new Map<string, Set<string>>();
  private handoffs = new Map<string, number>();
  private closeStream?: () => void;
  private read?: AbortController;
  private boot?: AbortController;
  private healthRead?: AbortController;
  private healthTimer?: ReturnType<typeof setInterval>;
  private deleted = new Set<string>();
  private uploadedFiles = new Map<string, Map<string, string>>();
  private resyncing = false;
  private resyncAgain = false;
  private buffered: ServerEvent[] = [];
  constructor(
    private transport: Transport = api,
    private remember: (id: string | null) => void = () => {},
  ) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private update(patch: Partial<ViewState>) {
    if (this.closed) return;
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }
  clearError = () => this.update({ error: null });
  async start(preferred?: string | null) {
    this.closed = false;
    const lifetime = ++this.lifetime;
    this.boot = new AbortController();
    clearInterval(this.healthTimer);
    void this.refreshHealth();
    this.healthTimer = setInterval(() => void this.refreshHealth(), 5000);
    void this.refreshImageCapabilities();
    await this.refreshList(false);
    if (!this.closed && lifetime === this.lifetime) {
      const id =
        this.state.sessions.find((s) => s.id === (this.state.selectedId ?? preferred))?.id ??
        this.state.sessions[0]?.id;
      if (id) this.select(id);
    }
  }
  private async refreshHealth() {
    // Do not replace hung work until it settles, even if it ignores cancellation.
    if (this.closed || this.healthRead) return;
    const lifetime = this.lifetime;
    const read = new AbortController();
    this.healthRead = read;
    const current = () => !this.closed && lifetime === this.lifetime;
    const unknown = () => {
      if (current())
        this.update({
          healthLoaded: true,
          codexAvailable: false,
          serviceAvailability: healthAvailability(undefined),
        });
    };
    const deadline = setTimeout(() => {
      read.abort();
      unknown();
    }, 2000);
    try {
      const health = await this.transport.health(read.signal);
      if (!current() || read.signal.aborted) return;
      this.update({
        visionAvailable: health.visionAvailable === true,
        codexAvailable: health.engines?.codex?.available === true,
        codexHealth: health.engines?.codex,
        healthLoaded: true,
        serviceAvailability: healthAvailability(health.availability),
      });
    } catch {
      unknown();
    } finally {
      clearTimeout(deadline);
      if (this.healthRead === read) this.healthRead = undefined;
    }
  }
  private async refreshImageCapabilities() {
    const lifetime = this.lifetime;
    const ticket = ++this.capabilityGeneration;
    try {
      const value = await this.transport.imageCapabilities(this.boot?.signal);
      if (this.closed || lifetime !== this.lifetime || ticket !== this.capabilityGeneration) return;
      this.update({ imageCapabilities: imageCapabilities(value), imageCapabilitiesLoaded: true });
    } catch {
      if (!this.closed && lifetime === this.lifetime && ticket === this.capabilityGeneration)
        this.update({ imageCapabilities: null, imageCapabilitiesLoaded: true });
    }
  }
  dispose() {
    this.closed = true;
    this.lifetime++;
    this.generation++;
    this.listGeneration++;
    this.closeStream?.();
    this.read?.abort();
    this.boot?.abort();
    this.healthRead?.abort();
    clearInterval(this.healthTimer);
  }
  async refreshList(reconcileSelection = true) {
    const ticket = ++this.listGeneration;
    try {
      const { sessions } = await this.transport.list(this.boot?.signal);
      if (this.closed || ticket !== this.listGeneration) return;
      const visible = sessions.filter((s) => !this.deleted.has(s.id) && s.status !== 'deleting');
      this.update({ sessions: visible, listLoading: false });
      if (
        reconcileSelection &&
        this.state.selectedId &&
        !visible.some((s) => s.id === this.state.selectedId)
      )
        this.select(visible[0]?.id ?? null);
    } catch (error) {
      if (!this.closed && ticket === this.listGeneration)
        this.update({ listLoading: false, error: messageOf(error) });
    }
  }
  select = (id: string | null) => {
    if (id && this.deleted.has(id)) return;
    this.generation++;
    this.closeStream?.();
    this.closeStream = undefined;
    this.read?.abort();
    this.read = undefined;
    this.resyncing = false;
    this.resyncAgain = false;
    this.buffered = [];
    this.remember(id);
    this.update({
      selectedId: id,
      thread: null,
      loading: !!id,
      error: null,
      connection: id ? 'connecting' : 'offline',
      imageJobsError: null,
    });
    if (id) void this.loadInitial(id, this.generation);
  };
  private current(id: string, generation: number) {
    return !this.closed && this.state.selectedId === id && this.generation === generation;
  }
  private hydrateCompletions(snapshot: Snapshot) {
    const completed = this.completedRuns.get(snapshot.session.id) ?? new Set<string>();
    for (const event of snapshot.events)
      if (event.sessionId === snapshot.session.id && event.type === 'done')
        completed.add(event.data.runId);
    for (const run of snapshot.runs ?? []) if (!runPending(run.status)) completed.add(run.id);
    this.completedRuns.set(snapshot.session.id, completed);
    this.clearSettledCompaction(snapshot.session.id);
  }
  private showThread(thread: Thread) {
    const id = thread.session.id;
    // Only recover pending data after a successful owned-chat snapshot.
    try {
      this.update({ pendingSubmissions: { ...this.state.pendingSubmissions, [id]: readSubmission(id) } });
    } catch (error) { this.update({ error: messageOf(error) }); }
    const terminal = new Set(
      thread.runs.filter((run) => !runPending(run.status)).map((run) => run.id),
    );
    const submitted = (lookup(this.state.submitted, id) ?? []).filter(
      (runId) => !terminal.has(runId) && !this.completedRuns.get(id)?.has(runId),
    );
    this.update({
      thread,
      submitted: { ...this.state.submitted, [id]: submitted.length ? submitted : undefined },
      sessions: this.state.sessions.map((s) => (s.id === id ? thread.session : s)),
    });
  }
  private async readSnapshot(id: string, signal: AbortSignal): Promise<Snapshot> {
    const snapshot = await this.transport.snapshot(id, signal);
    try {
      const { jobs } = await this.transport.imageJobs(id, signal);
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
      if (this.state.selectedId === id) this.update({ imageJobsError: null });
      const previous = this.state.thread?.session.id === id ? this.state.thread.imageJobs : [];
      return { ...snapshot, imageJobs: mergeImageJobs(previous ?? [], jobs, id) };
    } catch (error) {
      if (signal.aborted) throw error;
      if (this.state.selectedId === id)
        this.update({
          imageJobsError: `Image status unavailable: ${messageOf(error)} Last saved jobs remain visible.`,
        });
      // Image status is additive: preserve text chat and known jobs during an
      // image-route failure. Persisted image_job events can still advance them.
      const previous = this.state.thread?.session.id === id ? this.state.thread.imageJobs : [];
      return {
        ...snapshot,
        imageJobs: mergeImageJobs(previous ?? [], snapshot.imageJobs ?? [], id),
      };
    }
  }
  private async loadInitial(id: string, generation: number) {
    this.read = new AbortController();
    try {
      const snapshot = await this.readSnapshot(id, this.read.signal);
      if (!this.current(id, generation) || snapshot.session.id !== id) return;
      if (snapshot.session.status === 'deleting') {
        this.forget(id);
        return;
      }
      this.hydrateCompletions(snapshot);
      const thread = reconcileSnapshot(snapshot);
      this.showThread(thread);
      this.update({ loading: false });
      this.closeStream = this.transport.stream(id, thread.lastEventId, {
        event: (event) => {
          if (this.current(id, generation)) this.receive(event);
        },
        open: () => {
          if (this.current(id, generation)) {
            this.update({ connection: 'connected' });
            void this.resync();
          }
        },
        disconnected: () => {
          if (this.current(id, generation)) this.update({ connection: 'reconnecting' });
        },
      });
    } catch (error) {
      this.readFailure(error, id, generation);
    }
  }
  private readFailure(error: unknown, id: string, generation: number) {
    if (!this.current(id, generation)) return;
    if (error instanceof ApiError && [404, 410].includes(error.status)) {
      this.forget(id);
      void this.refreshList();
      return;
    }
    this.update({ loading: false, error: messageOf(error) });
  }
  private receive(event: ServerEvent) {
    const thread = this.state.thread;
    if (!thread || event.sessionId !== thread.session.id || event.id <= thread.lastEventId) return;
    if (this.resyncing) this.buffered.push(event);
    this.showThread(applyEvent(thread, event));
    if (event.type === 'state' && event.data.status === 'deleting') {
      this.forget(event.sessionId);
      return;
    }
    this.handleControl(event);
  }
  private handleControl(event: ServerEvent, fromSnapshot = false) {
    if (event.type === 'run' && !runPending(event.data.run.status)) {
      const completed = this.completedRuns.get(event.sessionId) ?? new Set<string>();
      completed.add(event.data.run.id);
      this.completedRuns.set(event.sessionId, completed);
      this.clearSettledCompaction(event.sessionId);
    }
    if (
      event.type === 'state' &&
      !['queued', 'running', 'compacting', 'cancelling'].includes(event.data.status) &&
      !this.state.thread?.runs.length
    )
      this.update({ submitted: { ...this.state.submitted, [event.sessionId]: undefined } });
    if (event.type === 'done') {
      const completed = this.completedRuns.get(event.sessionId) ?? new Set<string>();
      completed.add(event.data.runId);
      this.completedRuns.set(event.sessionId, completed);
      this.clearSettledCompaction(event.sessionId);
      const pending = (lookup(this.state.submitted, event.sessionId) ?? []).filter(
        (id) => id !== event.data.runId,
      );
      this.update({
        submitted: {
          ...this.state.submitted,
          [event.sessionId]: pending.length ? pending : undefined,
        },
      });
      if (!fromSnapshot) void this.resync();
      void this.refreshList(false);
    }
    if (event.type === 'handoff') {
      this.handoffs.set(event.sessionId, (this.handoffs.get(event.sessionId) ?? 0) + 1);
      this.update({ submitted: { ...this.state.submitted, [event.sessionId]: undefined } });
      const target = event.data.newSessionId;
      if (target && !this.deleted.has(target)) {
        // Navigate only a new event from the still-selected source conversation.
        this.select(target);
        void this.refreshList(false);
      }
    }
  }
  resync = async () => {
    const id = this.state.selectedId;
    if (!id || !this.state.thread) return;
    if (this.resyncing) {
      this.resyncAgain = true;
      return;
    }
    this.resyncing = true;
    this.buffered = [];
    void this.refreshImageCapabilities();
    const generation = this.generation;
    this.read = new AbortController();
    try {
      const snapshot = await this.readSnapshot(id, this.read.signal);
      if (!this.current(id, generation) || snapshot.session.id !== id) return;
      const thread = reconcileSnapshot(snapshot, this.buffered);
      if (thread.session.status === 'deleting') {
        this.forget(id);
        return;
      }
      // An older/cached snapshot without a cutoff must not rewind the cursor or UI.
      const renderedCursor = this.state.thread?.lastEventId ?? 0;
      if (thread.lastEventId >= renderedCursor) {
        this.hydrateCompletions(snapshot);
        this.showThread(thread);
        // A reconnect GET can win the race against SSE replay. Do not lose an
        // unseen handoff/done just because the snapshot advanced our cursor.
        for (const event of snapshot.events
          .filter((event) => event.sessionId === id && event.id > renderedCursor)
          .sort((a, b) => a.id - b.id)) {
          if (!this.current(id, generation)) break;
          this.handleControl(event, true);
        }
      }
    } catch (error) {
      this.readFailure(error, id, generation);
    } finally {
      if (this.current(id, generation)) {
        this.resyncing = false;
        this.buffered = [];
        if (this.resyncAgain) {
          this.resyncAgain = false;
          void this.resync();
        }
      }
    }
  };
  private async action<T>(
    action: string,
    id: string,
    execute: () => Promise<T>,
    success: (result: T) => void,
  ): Promise<boolean> {
    const key = busyKey(action, id);
    if (this.state.busy[key] || this.deleted.has(id)) return false;
    const generation = this.generation;
    this.update({ busy: { ...this.state.busy, [key]: true }, error: null });
    try {
      const result = await execute();
      if (!this.closed && !this.deleted.has(id)) success(result);
      return true;
    } catch (error) {
      if (!this.closed && (id === '' || this.current(id, generation)))
        this.update({ error: messageOf(error) });
      return false;
    } finally {
      this.update({ busy: { ...this.state.busy, [key]: false } });
    }
  }
  create = (engineKind: 'minimax' | 'codex' = 'minimax') => {
    if (engineKind === 'codex' && !this.state.codexAvailable) {
      this.update({ error: 'Codex preview is not available yet.' });
      return Promise.resolve();
    }
    const generation = this.generation;
    return this.action(
      'create',
      '',
      () => this.transport.create(engineKind === 'minimax' ? undefined : engineKind),
      ({ session }) => {
        this.listGeneration++;
        this.update({
          sessions: [session, ...this.state.sessions.filter((s) => s.id !== session.id)],
        });
        if (this.generation === generation) this.select(session.id);
      },
    );
  };
  private forget(id: string) {
    this.deleted.add(id);
    this.listGeneration++;
    const sessions = this.state.sessions.filter((s) => s.id !== id);
    const attachments = { ...this.state.attachments };
    delete attachments[id];
    const submitted = { ...this.state.submitted };
    delete submitted[id];
    const imageReferences = { ...this.state.imageReferences };
    delete imageReferences[id];
    const pendingSubmissions = { ...this.state.pendingSubmissions };
    delete pendingSubmissions[id];
    try { forgetSubmission(id); } catch { /* deleted guard still prevents submission */ }
    this.update({ sessions, attachments, submitted, imageReferences, pendingSubmissions });
    if (this.state.selectedId === id) this.select(sessions[0]?.id ?? null);
  }
  remove = (id: string) =>
    this.action(
      'delete',
      id,
      () => this.transport.remove(id),
      () => this.forget(id),
    );
  send = (id: string, text: string) => {
    const attachments = lookup(this.state.attachments, id) ?? [];
    const imageReferences = lookup(this.state.imageReferences, id) ?? [];
    if (this.state.thread?.session.id === id && this.state.thread.session.engineKind === 'codex' && imageReferences.length && !codexSpecialistAvailable(this.state,imageReferences.length)) {
      this.update({error:'Codex image specialist is unavailable.'}); return Promise.resolve(false);
    }
    if (
      (!text.trim() && attachments.length === 0 && imageReferences.length === 0) ||
      this.state.busy[busyKey('upload', id)] ||
      this.state.busy[busyKey('delete', id)]
    )
      return Promise.resolve(false);
    return this.sendSubmission(id, () => {
      if (readSubmission(id))
        throw new Error('A submitted message is awaiting acknowledgement. Retry the saved submission first.');
      const pending: PendingSubmission = {
        version: 1, sessionId: id, submissionId: crypto.randomUUID(), text,
        attachmentIds: attachments.map((a) => a.id),
        imageReferences: imageReferences.map((a) => a.id),
      };
      saveSubmission(pending);
      return pending;
    });
  };
  retrySubmission = (id: string) => this.sendSubmission(id, () => {
    const pending = readSubmission(id);
    if (!pending) throw new Error('There is no saved submission to retry.');
    return pending;
  });
  private sendSubmission(id: string, prepare: () => PendingSubmission) {
    // Read-only/deleted/other-chat state cannot send recovered browser data.
    if (this.state.thread?.session.id !== id || this.state.loading ||
      this.state.busy[busyKey('delete', id)] || this.state.thread.session.status === 'deleting')
      return Promise.resolve(false);
    let pending: PendingSubmission;
    return this.action(
      'send', id,
      async () => {
        pending = prepare();
        this.update({ pendingSubmissions: { ...this.state.pendingSubmissions, [id]: pending } });
        let result: { runId: string };
        try {
          result = await this.transport.send(id, pending.text, [...pending.attachmentIds],
            [...pending.imageReferences], pending.submissionId);
        } catch (error) {
          if (submissionRejected(error) && !this.deleted.has(id)) {
            acknowledgeSubmission(pending);
            this.update({ pendingSubmissions: { ...this.state.pendingSubmissions, [id]: undefined } });
          }
          throw error;
        }
        if (!result || typeof result.runId !== 'string' || !result.runId)
          throw new Error('Submission acknowledgement was unreadable. Retry the saved submission.');
        // A late known ACK is still authoritative after navigation/dispose.
        if (!this.deleted.has(id)) acknowledgeSubmission(pending);
        return result;
      },
      ({ runId }) => {
        const used = new Set(pending.attachmentIds);
        const referenced = new Set(pending.imageReferences);
        this.update({
          pendingSubmissions: { ...this.state.pendingSubmissions, [id]: undefined },
          attachments: {
            ...this.state.attachments,
            [id]: (lookup(this.state.attachments, id) ?? []).filter((a) => !used.has(a.id)),
          },
          imageReferences: {
            ...this.state.imageReferences,
            [id]: (lookup(this.state.imageReferences, id) ?? []).filter((a) => !referenced.has(a.id)),
          },
          submitted: {
            ...this.state.submitted,
            [id]:
              this.completedRuns.get(id)?.has(runId) ||
              this.state.thread?.runs.some((run) => run.id === runId && !runPending(run.status))
                ? lookup(this.state.submitted, id)
                : [...new Set([...(lookup(this.state.submitted, id) ?? []), runId])],
          },
        });
        if (this.state.selectedId === id) void this.resync();
      },
    );
  }
  private imageAction(id: string, jobId: string, decision?: 'approve' | 'reject') {
    const job =
      this.state.thread?.session.id === id
        ? this.state.thread.imageJobs?.find((candidate) => candidate.id === jobId)
        : undefined;
    if (!job || !imageJobActive(job) || (decision && job.state !== 'awaiting_approval'))
      return Promise.resolve(false);
    return this.action(
      `image:${jobId}`,
      id,
      () =>
        decision
          ? this.transport.approveImage(id, jobId, decision)
          : this.transport.cancelImage(id, jobId),
      ({ job: updated }) => {
        const thread = this.state.thread;
        // Never let a delayed POST acknowledgement overwrite a newer SSE state.
        if (
          thread?.session.id === id &&
          thread.imageJobs?.find((item) => item.id === jobId) === job &&
          updated.id === jobId &&
          updated.runId === job.runId
        )
          this.showThread({
            ...thread,
            imageJobs: mergeImageJobs(thread.imageJobs ?? [], [updated], id),
          });
        if (this.state.selectedId === id) void this.resync();
      },
    );
  }
  approveImage = (id: string, jobId: string, decision: 'approve' | 'reject') =>
    this.imageAction(id, jobId, decision);
  cancelImage = (id: string, jobId: string) => this.imageAction(id, jobId);
  addImageReference = (id: string, artifactId: string) => {
    if (this.state.thread?.session.id !== id || this.state.busy[busyKey('send', id)]) return;
    const artifact = this.state.thread.artifacts.find((item) => item.id === artifactId);
    if (!artifact || !['image/png', 'image/jpeg'].includes(artifact.mimeType)) return;
    const current = lookup(this.state.imageReferences, id) ?? [];
    if (current.some((item) => item.id === artifactId)) return;
    if (!canStageEditReference(this.state.imageCapabilities, current.length + 1) ||
      (this.state.thread.session.engineKind === 'codex' && !codexSpecialistAvailable(this.state, current.length + 1))) {
      this.update({
        error: `Image editing with ${current.length + 1} reference(s) is unavailable.`,
      });
      return;
    }
    this.update({
      imageReferences: { ...this.state.imageReferences, [id]: [...current, artifact] },
    });
  };
  removeImageReference = (id: string, artifactId: string) => {
    if (this.state.busy[busyKey('send', id)]) return;
    this.update({
      imageReferences: {
        ...this.state.imageReferences,
        [id]: (lookup(this.state.imageReferences, id) ?? []).filter(
          (item) => item.id !== artifactId,
        ),
      },
    });
  };
  cancel = (id: string) => {
    const cursor = this.state.thread?.lastEventId;
    return this.action(
      'cancel',
      id,
      () => this.transport.cancel(id),
      ({ status }) => {
        const thread = this.state.thread;
        // A late acknowledgement must not replace a newer terminal state event.
        if (thread?.session.id === id && thread.lastEventId === cursor)
          this.showThread({ ...thread, session: { ...thread.session, status } });
        if (this.state.selectedId === id) void this.resync();
      },
    );
  };
  private compactionAction(id: string): { actionId: string; runId?: string } | undefined {
    const raw = sessionStorage.getItem(`ai-harness:compaction:${id}`);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (
      typeof saved?.actionId !== 'string' ||
      !/^[a-zA-Z0-9_-]{1,80}$/.test(saved.actionId) ||
      (saved.runId !== undefined && typeof saved.runId !== 'string')
    )
      throw new Error(
        'Saved compaction action is unreadable; refresh its status before starting another.',
      );
    return saved;
  }
  private clearSettledCompaction(id: string) {
    try {
      const saved = this.compactionAction(id);
      if (saved?.runId && this.completedRuns.get(id)?.has(saved.runId))
        sessionStorage.removeItem(`ai-harness:compaction:${id}`);
    } catch {
      // Retaining an uncertain action is safer than generating a replacement.
    }
  }
  compact = (id: string) => {
    if (
      this.state.thread?.session.id !== id ||
      this.state.thread.session.engineKind !== 'codex' ||
      pendingRunIds(this.state, id).length
    )
      return Promise.resolve(false);
    return this.action(
      'compact',
      id,
      async () => {
        this.clearSettledCompaction(id);
        const saved = this.compactionAction(id);
        const action = saved ?? { actionId: crypto.randomUUID() };
        // Persist before dispatch: a lost acknowledgement or page refresh must
        // reconcile this exact action instead of compacting a second time.
        sessionStorage.setItem(`ai-harness:compaction:${id}`, JSON.stringify(action));
        try {
          const result = await this.transport.compact(id, action.actionId);
          if (typeof result?.runId !== 'string' || !result.runId)
            throw new Error('Compaction acknowledgement omitted its run ID');
          sessionStorage.setItem(
            `ai-harness:compaction:${id}`,
            JSON.stringify({ ...action, runId: result.runId }),
          );
          return result;
        } catch (error) {
          if (
            error instanceof ApiError &&
            error.status >= 400 &&
            error.status < 500 &&
            error.status !== 408
          ) {
            // Rejection of a retry cannot prove the original uncertain attempt
            // was never accepted. Only a fresh action's rejection releases it.
            if (!saved) sessionStorage.removeItem(`ai-harness:compaction:${id}`);
            throw error;
          }
          throw new Error(
            'Compaction outcome is unconfirmed. Retry Compact context to check the same action.',
          );
        }
      },
      ({ runId }) => {
        const settled = this.completedRuns.get(id)?.has(runId);
        this.clearSettledCompaction(id);
        this.update({
          submitted: { ...this.state.submitted, [id]: settled ? undefined : [runId] },
        });
        if (this.state.selectedId === id) void this.resync();
      },
    );
  };
  handoff = (id: string, engineKind?: EngineKind) => {
    const before = this.handoffs.get(id) ?? 0;
    if (pendingRunIds(this.state, id).length) return Promise.resolve(false);
    const source = this.state.thread?.session.id === id
      ? this.state.thread.session : this.state.sessions.find(session => session.id === id);
    const target = engineKind ?? source?.engineKind ?? 'minimax';
    if (target === 'codex' && !this.state.codexAvailable) {
      this.update({ error: 'Codex preview is not available yet.' });
      return Promise.resolve(false);
    }
    return this.action(
      'handoff',
      id,
      () => this.transport.handoff(id, engineKind),
      ({ runId }) => {
        const settled =
          this.completedRuns.get(id)?.has(runId) || (this.handoffs.get(id) ?? 0) !== before;
        this.update({
          submitted: { ...this.state.submitted, [id]: settled ? undefined : [runId] },
        });
        if (this.state.selectedId === id) void this.resync();
      },
    );
  };
  reuseFile = (id: string, fileId: string) => {
    if (
      !this.transport.reference ||
      this.state.busy[busyKey('send', id)] ||
      this.state.busy[busyKey('delete', id)]
    )
      return Promise.resolve(false);
    return this.action(
      'upload',
      id,
      () => this.transport.reference!(id, fileId),
      ({ attachment }) => {
        this.update({
          attachments: {
            ...this.state.attachments,
            [id]: [...(lookup(this.state.attachments, id) ?? []), attachment],
          },
        });
      },
    );
  };
  upload = (id: string, file: File) => this.uploadBatch(id, [file]);
  uploadBatch = async (id: string, files: File[], onUpdate?: (update: UploadUpdate) => void) => {
    if (
      this.closed ||
      this.state.busy[busyKey('send', id)] ||
      this.state.busy[busyKey('delete', id)]
    )
      return false;
    // Engine identity belongs to the upload target, even when navigation changes
    // the visible thread while a previous file is awaiting its response.
    const targetSession = this.state.thread?.session.id === id
      ? this.state.thread.session : this.state.sessions.find(session => session.id === id);
    const targetIsCodex = targetSession?.engineKind === 'codex';
    const unique = [...new Map(files.map((file) => [uploadKey(file), file])).values()];
    if (!unique.length) return false;
    const generation = this.generation;
    let allSucceeded = true;
    // Hold one lock for the entire batch, including the gap between requests.
    // A send can never capture a partially uploaded selection.
    const accepted = await this.action(
      'upload',
      id,
      async () => {
        const known = this.uploadedFiles.get(id) ?? new Map<string, string>();
        const attachedIds = new Set([...(lookup(this.state.attachments, id) ?? []), ...(lookup(this.state.imageReferences, id) ?? [])].map((a) => a.id));
        for (const [key, attachmentId] of known) {
          if (!attachedIds.has(attachmentId)) known.delete(key);
        }
        this.uploadedFiles.set(id, known);
        for (const file of unique) {
          if (this.closed || this.deleted.has(id) || this.state.busy[busyKey('delete', id)]) {
            allSucceeded = false;
            onUpdate?.({ file, status: 'error', error: 'Upload stopped because the chat closed.' });
            continue;
          }
          const previous = known.get(uploadKey(file));
          if (
            previous &&
            [...(lookup(this.state.attachments, id) ?? []), ...(lookup(this.state.imageReferences, id) ?? [])].some((a) => a.id === previous)
          ) {
            onUpdate?.({ file, status: 'ready' });
            continue;
          }
          try {
            const codex = targetIsCodex;
            const imageFile = file.type.startsWith('image/') || /\.(png|jpe?g|gif|webp|svg|avif|heic|bmp|tiff?)$/i.test(file.name);
            const specialist = codex && imageFile;
            if (specialist && (!['image/png','image/jpeg'].includes(file.type) || !codexSpecialistAvailable(this.state,(lookup(this.state.imageReferences,id) ?? []).length+1)))
              throw new Error('Codex image specialist accepts qualified PNG/JPEG references only; native image recognition is unavailable.');
            const problem = uploadProblem(
              file,
              codex ? specialist : this.state.visionAvailable || imageReferencesAvailable(this.state.imageCapabilities),
            );
            if (problem) throw new Error(problem);
            onUpdate?.({ file, status: 'uploading' });
            const { attachment } = await this.transport.upload(id, file);
            if (this.closed || this.deleted.has(id)) {
              allSucceeded = false;
              continue;
            }
            known.set(uploadKey(file), attachment.id);
            const thread = this.state.thread;
            this.update({
              ...(specialist ? {
                imageReferences: {...this.state.imageReferences,[id]:[...(lookup(this.state.imageReferences,id) ?? []).filter(a=>a.id!==attachment.id),attachment]},
              } : {attachments: {
                ...this.state.attachments,
                [id]: [...(lookup(this.state.attachments,id) ?? []).filter(a=>a.id!==attachment.id),attachment],
              }}),
              ...(thread?.session.id === id
                ? {
                    thread: {
                      ...thread,
                      attachments: [
                        ...thread.attachments.filter((a) => a.id !== attachment.id),
                        attachment,
                      ],
                    },
                  }
                : {}),
            });
            onUpdate?.({ file, status: 'ready' });
          } catch (error) {
            allSucceeded = false;
            const problem = messageOf(error);
            onUpdate?.({ file, status: 'error', error: problem });
            if (this.current(id, generation)) this.update({ error: problem });
          }
        }
      },
      () => {},
    );
    return accepted && allSucceeded;
  };
  removeAttachment = (id: string, attachmentId: string) => {
    if (this.state.busy[busyKey('send', id)]) return;
    this.update({
      attachments: {
        ...this.state.attachments,
        [id]: (lookup(this.state.attachments, id) ?? []).filter((a) => a.id !== attachmentId),
      },
    });
  };
}
