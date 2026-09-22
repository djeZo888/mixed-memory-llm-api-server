import { useEffect, useRef, useState, type DragEvent } from 'react';
import { ArrowUp, FileText, Paperclip, Square, X } from 'lucide-react';
import { HarnessStore, busyKey, lookup, pendingRunIds, type ViewState } from './store';
import { ContextMeter } from './ContextMeter';
import { contextForThread } from './context';
import { isActive } from './types';
import { uploadAccept, uploadKey } from './uploads';

interface UploadItem {
  key: string;
  name: string;
  status: 'queued' | 'uploading' | 'error';
  error?: string;
}
const bytes = (size: number) =>
  size >= 1024 * 1024
    ? `${(size / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(size / 1024))} KB`;
const hasFiles = (event: DragEvent) =>
  Array.from(event.dataTransfer.types).includes('Files') || event.dataTransfer.files.length > 0;

export function Composer({
  store,
  state,
  id,
}: {
  store: HarnessStore;
  state: ViewState;
  id: string;
}) {
  const [text, setText] = useState('');
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [dropNotice, setDropNotice] = useState('');
  const input = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const uploadLock = useRef(false);
  const sendLock = useRef(false);
  const composing = useRef(false);
  const dragDepth = useRef(0);
  const attachments = lookup(state.attachments, id) ?? [];
  const busy = (action: string) => state.busy[busyKey(action, id)];
  const locked =
    uploading || busy('send') || busy('upload') || busy('delete') || state.loading || !state.thread;
  const active = isActive(state.thread?.session.status) || pendingRunIds(state, id).length > 0;
  useEffect(() => {
    input.current?.focus();
  }, []);

  async function send() {
    const submitted = text;
    if (locked || uploadLock.current || sendLock.current || (!text.trim() && !attachments.length))
      return;
    sendLock.current = true;
    try {
      if (await store.send(id, submitted)) setText((value) => (value === submitted ? '' : value));
    } finally {
      sendLock.current = false;
      input.current?.focus();
    }
  }

  async function attach(files: File[]) {
    if (!files.length) return;
    if (locked || uploadLock.current || sendLock.current) {
      setDropNotice(
        'Please wait for the current request to finish, then attach these files again.',
      );
      return;
    }
    uploadLock.current = true;
    setUploading(true);
    setDropNotice('');
    const unique = [...new Map(files.map((file) => [uploadKey(file), file])).values()];
    const keys = new Set(unique.map(uploadKey));
    setUploads((items) => [
      ...items.filter((item) => !keys.has(item.key)),
      ...unique.map((file) => ({
        key: uploadKey(file),
        name: file.name,
        status: 'queued' as const,
      })),
    ]);
    try {
      await store.uploadBatch(id, unique, (update) => {
        const key = uploadKey(update.file);
        const status = update.status;
        setUploads((items) =>
          status === 'ready'
            ? items.filter((item) => item.key !== key)
            : items.map((item) =>
                item.key === key ? { ...item, status, error: update.error } : item,
              ),
        );
      });
    } finally {
      uploadLock.current = false;
      setUploading(false);
      // A competing action may reject the batch before any requests begin.
      setUploads((items) =>
        items.map((item) =>
          keys.has(item.key) && item.status !== 'error'
            ? {
                ...item,
                status: 'error',
                error: 'Upload did not complete. Attach this file again to retry.',
              }
            : item,
        ),
      );
    }
  }

  return (
    <div
      className={`composer-wrap${dragging ? ' drop-active' : ''}`}
      onDragEnter={(event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        dragDepth.current++;
        setDragging(true);
      }}
      onDragOver={(event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = locked ? 'none' : 'copy';
      }}
      onDragLeave={(event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (!dragDepth.current) setDragging(false);
      }}
      onDrop={(event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        event.stopPropagation();
        dragDepth.current = 0;
        setDragging(false);
        void attach(Array.from(event.dataTransfer.files));
      }}
    >
      <ContextMeter context={contextForThread(state.thread)} />
      {dragging && (
        <div className="drop-hint" role="status">
          Drop files to attach
        </div>
      )}
      {dropNotice && (
        <p className="upload-notice" role="status">
          {dropNotice}
        </p>
      )}
      <form
        className="composer"
        aria-label="Message composer"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        {attachments.length > 0 && (
          <ul className="attachments" aria-label="Attached files">
            {attachments.map((attachment) => (
              <li key={attachment.id}>
                <FileText size={15} />
                <span title={attachment.name}>{attachment.name}</span>
                <small>{bytes(attachment.size)} · Ready</small>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Remove attachment ${attachment.name}`}
                  disabled={!!busy('send')}
                  onClick={() => store.removeAttachment(id, attachment.id)}
                >
                  <X size={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
        {uploads.length > 0 && (
          <ul
            className="attachments upload-status"
            aria-label="File upload status"
            aria-live="polite"
          >
            {uploads.map((item) => (
              <li key={item.key} className={`upload-${item.status}`}>
                <FileText size={15} />
                <span title={item.name}>{item.name}</span>
                <small>
                  {item.status === 'queued'
                    ? 'Queued'
                    : item.status === 'uploading'
                      ? 'Uploading…'
                      : item.error}
                </small>
                {item.status === 'error' && (
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Dismiss upload error for ${item.name}`}
                    onClick={() =>
                      setUploads((items) => items.filter((other) => other.key !== item.key))
                    }
                  >
                    <X size={14} />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        <label className="sr-only" htmlFor="message-input">
          Message
        </label>
        <textarea
          id="message-input"
          ref={input}
          rows={3}
          placeholder="Ask a question or describe a task…"
          value={text}
          disabled={!!locked}
          aria-describedby="composer-keyboard-hint"
          onChange={(event) => setText(event.target.value)}
          onCompositionStart={() => {
            composing.current = true;
          }}
          onCompositionEnd={() => {
            composing.current = false;
          }}
          onKeyDown={(event) => {
            if (
              event.key === 'Enter' &&
              (event.ctrlKey || event.metaKey) &&
              !composing.current &&
              !event.nativeEvent.isComposing &&
              event.nativeEvent.keyCode !== 229
            ) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <div className="composer-actions">
          <input
            ref={fileInput}
            className="sr-only"
            type="file"
            multiple
            tabIndex={-1}
            aria-label="Upload file"
            accept={uploadAccept + (state.visionAvailable ? ',image/*' : '')}
            disabled={!!locked}
            onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              event.target.value = '';
              void attach(files);
            }}
          />
          <button
            type="button"
            className="text-button attach-button"
            disabled={!!locked}
            onClick={() => fileInput.current?.click()}
          >
            <Paperclip size={17} />
            {uploading || busy('upload') ? 'Uploading…' : 'Attach files'}
          </button>
          <div className="send-actions">
            {active && (
              <button
                type="button"
                className="stop-button"
                title="Stop active and queued turns"
                disabled={!!busy('cancel') || state.thread?.session.status === 'cancelling'}
                onClick={() => void store.cancel(id)}
              >
                <Square size={12} fill="currentColor" />
                {state.thread?.session.status === 'cancelling' ? 'Cancelling' : 'Stop all'}
              </button>
            )}
            <button
              className="send-button"
              type="submit"
              aria-label={active ? 'Queue message for next turn' : 'Send message'}
              title={active ? 'Queue for next turn' : 'Send message'}
              disabled={!!locked || (!text.trim() && !attachments.length)}
            >
              <ArrowUp size={20} />
            </button>
          </div>
        </div>
      </form>
      {active && (
        <p className="composer-queue-note">
          New messages queue for the next turn. Stop cancels active and queued turns.
        </p>
      )}
      <div className="composer-note">
        <span>
          {state.healthLoaded
            ? state.visionAvailable
              ? 'PDF, source, text and image files · 50 MiB per file'
              : 'PDF, source and text files · 50 MiB per file · Images unavailable'
            : 'Checking attachment capabilities…'}
        </span>
        <span className="keyboard-hint" id="composer-keyboard-hint">
          Enter for a new line · Ctrl / Cmd + Enter to send
        </span>
      </div>
    </div>
  );
}
