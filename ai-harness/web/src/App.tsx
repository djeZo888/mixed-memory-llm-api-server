import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import {
  ArrowDown,
  ArrowUpRight,
  FileText,
  Menu,
  MessageSquare,
  Plus,
  Terminal,
  Trash2,
  X,
} from 'lucide-react';
import { HarnessStore, busyKey, pendingRunIds } from './store';
import { isActive, type Status } from './types';
import { Composer } from './Composer';
import { ConversationReplies, WorkingStatus } from './Replies';

function Badge({ status }: { status: Status }) {
  return (
    <span className={`badge status-${status}`}>
      <span />
      {status}
    </span>
  );
}

export function App({ store }: { store: HarnessStore }) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [narrow, setNarrow] = useState(window.innerWidth <= 700);
  const sidebar = useRef<HTMLElement>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [following, setFollowing] = useState(true);
  const scroll = useRef<HTMLDivElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const sidebarButton = useRef<HTMLButtonElement>(null);
  const thread = state.thread;
  const selected = state.selectedId;
  const title =
    thread?.session.title ||
    state.sessions.find((s) => s.id === selected)?.title ||
    'New conversation';
  useEffect(() => {
    let remembered: string | null = null;
    try {
      remembered = localStorage.getItem('ai-harness:selected');
    } catch {
      /* Private browsing may disable storage. */
    }
    void store.start(remembered);
    return () => store.dispose();
  }, [store]);
  useEffect(() => {
    const resize = () => setNarrow(window.innerWidth <= 700);
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);
  useEffect(() => {
    if (sidebarOpen && narrow)
      sidebar.current?.querySelector<HTMLButtonElement>('.new-chat')?.focus();
  }, [sidebarOpen, narrow]);
  useEffect(() => {
    setFollowing(true);
    setConfirmDelete(null);
  }, [selected]);
  useEffect(() => {
    if (following) end.current?.scrollIntoView({ block: 'end' });
  }, [thread?.messages, following]);
  const select = (id: string) => {
    store.select(id);
    setSidebarOpen(false);
  };
  const dismissSidebar = () => {
    setSidebarOpen(false);
    requestAnimationFrame(() => sidebarButton.current?.focus());
  };
  const deleting = confirmDelete ? !!state.busy[busyKey('delete', confirmDelete)] : false;
  return (
    <div
      className="app-shell"
      onDragOver={(event) => {
        if (Array.from(event.dataTransfer.types).includes('Files')) event.preventDefault();
      }}
      onDrop={(event) => {
        if (
          Array.from(event.dataTransfer.types).includes('Files') ||
          event.dataTransfer.files.length
        )
          event.preventDefault();
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          if (sidebarOpen) dismissSidebar();
          setConfirmDelete(null);
        }
      }}
    >
      <a className="skip-link" href="#conversation">
        Skip to conversation
      </a>
      {sidebarOpen && (
        <button className="sidebar-scrim" aria-label="Close chat list" onClick={dismissSidebar} />
      )}
      <aside
        ref={sidebar}
        className={`sidebar ${sidebarOpen ? 'open' : ''}`}
        aria-label="Chat sidebar"
      >
        <div className="brand">
          <span className="brand-icon">
            <Terminal size={18} />
          </span>
          <span>
            ai-harness<small>WORKSPACE</small>
          </span>
          <button
            className="icon-button mobile-only close-sidebar"
            onClick={dismissSidebar}
            aria-label="Close sidebar"
          >
            <X size={19} />
          </button>
        </div>
        <button
          className="new-chat"
          disabled={!!state.busy[busyKey('create')]}
          onClick={() => {
            void store.create();
            setSidebarOpen(false);
          }}
        >
          <Plus size={18} />
          {state.busy[busyKey('create')] ? 'Creating…' : 'New chat'}
        </button>
        <div className="section-label">
          CONVERSATIONS <span>{state.sessions.length}</span>
        </div>
        <nav className="session-list" aria-label="Conversations">
          {state.listLoading && <p className="sidebar-hint">Loading conversations…</p>}
          {!state.listLoading && state.sessions.length === 0 && (
            <p className="sidebar-hint">Your conversations will appear here.</p>
          )}
          {state.sessions.map((session) => (
            <div
              className={`session-row ${session.id === selected ? 'selected' : ''}`}
              key={session.id}
            >
              <button
                className="session-select"
                onClick={() => select(session.id)}
                aria-current={session.id === selected ? 'page' : undefined}
              >
                <MessageSquare size={16} />
                <span>
                  <span className="session-title">{session.title || 'Untitled chat'}</span>
                  <span className={`session-state status-${session.status}`}>{session.status}</span>
                </span>
              </button>
              <button
                className="icon-button delete-chat"
                onClick={() => setConfirmDelete(session.id)}
                aria-label={`Delete chat ${session.title || 'Untitled chat'}`}
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="version-dot" />
          ai-harness <span>0.0.2</span>
          <p>A space for technical work.</p>
        </div>
      </aside>
      <main inert={sidebarOpen && narrow} className="main-pane" id="conversation" tabIndex={-1}>
        <header className="topbar">
          <button
            ref={sidebarButton}
            className="icon-button mobile-only"
            aria-label="Open chat list"
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen(true)}
          >
            <Menu size={20} />
          </button>
          <div className="chat-heading">
            <span className="eyebrow">CONVERSATION</span>
            <h1>{selected ? title : 'Your workspace'}</h1>
          </div>
          {thread && (
            <div className="header-actions">
              <Badge status={thread.session.status} />
              <button
                className="text-button handoff"
                disabled={
                  !!state.busy[busyKey('handoff', selected!)] ||
                  isActive(thread.session.status) ||
                  pendingRunIds(state, selected!).length > 0
                }
                onClick={() => void store.handoff(selected!)}
              >
                <span>Continue in new chat</span>
                <ArrowUpRight size={17} />
              </button>
            </div>
          )}
        </header>
        {selected && (
          <div className={`connection connection-${state.connection}`} role="status">
            <span className="connection-dot" />
            {state.connection === 'connected'
              ? 'Connected'
              : state.connection === 'reconnecting'
                ? 'Connection lost · reconnecting. Your task continues on the server.'
                : state.connection === 'connecting'
                  ? 'Connecting…'
                  : 'Offline'}
            {state.connection === 'connected' && (
              <span className="connection-note">Tasks continue when you close this page</span>
            )}
          </div>
        )}
        {thread && <WorkingStatus thread={thread} />}
        {state.error && (
          <div className="error-banner" role="alert">
            <span>{state.error}</span>
            <button
              className="text-button"
              onClick={() => {
                store.clearError();
                if (selected && !thread) store.select(selected);
                else {
                  void store.resync();
                  void store.refreshList();
                }
              }}
            >
              Retry sync
            </button>
            <button className="icon-button" aria-label="Dismiss error" onClick={store.clearError}>
              <X size={16} />
            </button>
          </div>
        )}
        <div
          className="conversation-scroll"
          ref={scroll}
          onScroll={() => {
            const el = scroll.current;
            if (el) setFollowing(el.scrollHeight - el.scrollTop - el.clientHeight < 100);
          }}
        >
          {!selected ? (
            <div className="empty-state">
              <div className="empty-symbol">
                <Terminal size={30} />
              </div>
              <span className="eyebrow">READY WHEN YOU ARE</span>
              <h2>What are we working on?</h2>
              <p>Research a question, investigate code, or work through a technical problem.</p>
              <button
                className="primary-button"
                disabled={!!state.busy[busyKey('create')]}
                onClick={() => void store.create()}
              >
                <Plus size={17} />
                Start a conversation
              </button>
              <div className="empty-capabilities">
                <span>
                  <FileText size={15} />
                  Files & documents
                </span>
                <span>
                  <Terminal size={15} />
                  Code & analysis
                </span>
              </div>
            </div>
          ) : state.loading ? (
            <div className="loading-state" role="status">
              Loading conversation…
            </div>
          ) : (
            <div className="conversation-content">
              {thread?.messages.length === 0 && (
                <div className="chat-empty">
                  <span className="empty-symbol">
                    <MessageSquare size={26} />
                  </span>
                  <h2>A fresh place to start.</h2>
                  <p>Send a message or attach a file below.</p>
                </div>
              )}
              {thread && <ConversationReplies thread={thread} />}
              {state.submitted[selected]?.length &&
                !thread?.runs.some((run) =>
                  ['queued', 'running', 'cancelling'].includes(run.status),
                ) && (
                  <p className="submitted" role="status">
                    Request accepted. Waiting for server status.
                  </p>
                )}
              <div ref={end} />
            </div>
          )}
        </div>
        {!following && selected && (
          <button
            className="jump-latest"
            onClick={() => {
              setFollowing(true);
              end.current?.scrollIntoView({
                behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
                  ? 'auto'
                  : 'smooth',
                block: 'end',
              });
            }}
          >
            <ArrowDown size={14} />
            Latest message
          </button>
        )}
        {selected && <Composer key={selected} id={selected} state={state} store={store} />}
      </main>
      {confirmDelete && (
        <DeleteDialog
          title={state.sessions.find((s) => s.id === confirmDelete)?.title ?? 'this chat'}
          busy={deleting}
          cancel={() => setConfirmDelete(null)}
          confirm={() => {
            void store.remove(confirmDelete).then((ok) => {
              if (ok) setConfirmDelete(null);
            });
          }}
        />
      )}
    </div>
  );
}
function DeleteDialog({
  title,
  busy,
  cancel,
  confirm,
}: {
  title: string;
  busy: boolean;
  cancel: () => void;
  confirm: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => {
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="delete-dialog"
      aria-labelledby="delete-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) cancel();
      }}
    >
      <h2 id="delete-title">Delete this chat?</h2>
      <p>
        “{title}” will leave your chat list. Any active task is cancelled. Generated project files
        are preserved.
      </p>
      <div>
        <button className="text-button" onClick={cancel} disabled={busy} autoFocus>
          Keep chat
        </button>
        <button className="danger-button" onClick={confirm} disabled={busy}>
          {busy ? 'Deleting…' : 'Delete chat'}
        </button>
      </div>
    </dialog>
  );
}
