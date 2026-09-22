import { api, ApiError, type Transport } from './api';
import { applyEvent, reconcileSnapshot } from './state';
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
  busy: Record<string, boolean>;
  attachments: Record<string, Attachment[]>;
  submitted: Record<string, string[] | undefined>;
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
    busy: {},
    attachments: {},
    submitted: {},
  };
  private listeners = new Set<() => void>();
  private generation = 0;
  private listGeneration = 0;
  private closed = false;
  private lifetime = 0;
  private completedRuns = new Map<string, Set<string>>();
  private handoffs = new Map<string, number>();
  private closeStream?: () => void;
  private read?: AbortController;
  private boot?: AbortController;
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
    void this.transport
      .health(this.boot.signal)
      .then((health) => {
        if (this.closed || lifetime !== this.lifetime) return;
        this.update({ visionAvailable: health.visionAvailable === true, healthLoaded: true });
      })
      .catch(() => {
        if (lifetime === this.lifetime) this.update({ healthLoaded: true });
      });
    await this.refreshList(false);
    if (!this.closed && lifetime === this.lifetime) {
      const id =
        this.state.sessions.find((s) => s.id === (this.state.selectedId ?? preferred))?.id ??
        this.state.sessions[0]?.id;
      if (id) this.select(id);
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
  }
  private showThread(thread: Thread) {
    const id = thread.session.id;
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
  private async loadInitial(id: string, generation: number) {
    this.read = new AbortController();
    try {
      const snapshot = await this.transport.snapshot(id, this.read.signal);
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
    const generation = this.generation;
    this.read = new AbortController();
    try {
      const snapshot = await this.transport.snapshot(id, this.read.signal);
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
  create = () => {
    const generation = this.generation;
    return this.action(
      'create',
      '',
      () => this.transport.create(),
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
    this.update({ sessions, attachments, submitted });
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
    if (
      (!text.trim() && attachments.length === 0) ||
      this.state.busy[busyKey('upload', id)] ||
      this.state.busy[busyKey('delete', id)]
    )
      return Promise.resolve(false);
    return this.action(
      'send',
      id,
      () =>
        this.transport.send(
          id,
          text,
          attachments.map((a) => a.id),
        ),
      ({ runId }) => {
        const used = new Set(attachments.map((a) => a.id));
        this.update({
          attachments: {
            ...this.state.attachments,
            [id]: (lookup(this.state.attachments, id) ?? []).filter((a) => !used.has(a.id)),
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
  handoff = (id: string) => {
    const before = this.handoffs.get(id) ?? 0;
    if (pendingRunIds(this.state, id).length) return Promise.resolve(false);
    return this.action(
      'handoff',
      id,
      () => this.transport.handoff(id),
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
  upload = (id: string, file: File) => this.uploadBatch(id, [file]);
  uploadBatch = async (id: string, files: File[], onUpdate?: (update: UploadUpdate) => void) => {
    if (
      this.closed ||
      this.state.busy[busyKey('send', id)] ||
      this.state.busy[busyKey('delete', id)]
    )
      return false;
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
        const attachedIds = new Set((lookup(this.state.attachments, id) ?? []).map((a) => a.id));
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
            (lookup(this.state.attachments, id) ?? []).some((a) => a.id === previous)
          ) {
            onUpdate?.({ file, status: 'ready' });
            continue;
          }
          try {
            const problem = uploadProblem(file, this.state.visionAvailable);
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
              attachments: {
                ...this.state.attachments,
                [id]: [
                  ...(lookup(this.state.attachments, id) ?? []).filter(
                    (a) => a.id !== attachment.id,
                  ),
                  attachment,
                ],
              },
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
