import { useEffect, useState } from 'react';
import { ChevronDown, Download, FileText, LoaderCircle, Paperclip, Terminal } from 'lucide-react';
import { Markdown } from './Markdown';
import { groupReplies, type Reply } from './reply-groups';
import { bytes, formatTime } from './display';
import {
  artifactDownloadUrl,
  attachmentDownloadUrl,
  previewUrl,
  runZipUrl,
  safePublicUrl,
} from './urls';
import { isActive, type ActivityItem, type Artifact, type Message, type Thread } from './types';

function Timestamp({ value }: { value: string }) {
  return (
    <time dateTime={value} title="Europe/Ljubljana">
      {formatTime(value)}
    </time>
  );
}
function Text({ message }: { message: Message }) {
  return (
    <div className="markdown">
      <Markdown>{message.content}</Markdown>
    </div>
  );
}
function Progress({ messages, finalReady }: { messages: Message[]; finalReady: boolean }) {
  const [open, setOpen] = useState(!finalReady);
  useEffect(() => setOpen(!finalReady), [finalReady]);
  return (
    <details
      className="progress-panel"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <span>Progress</span>
        <span className="activity-count">
          {messages.length} {messages.length === 1 ? 'message' : 'messages'}
        </span>
        <ChevronDown size={15} />
      </summary>
      <div className="progress-messages">
        {messages.map((message) => (
          <section key={message.id} className="progress-message">
            <div className="message-meta">
              <strong>{message.phase === 'thinking' ? 'Reasoning' : 'Assistant update'}</strong>
              <Timestamp value={message.createdAt} />
            </div>
            <Text message={message} />
          </section>
        ))}
      </div>
    </details>
  );
}
function duration(item: ActivityItem): string | undefined {
  if (!item.startedAt || !item.finishedAt) return undefined;
  const elapsed = Date.parse(item.finishedAt) - Date.parse(item.startedAt);
  return Number.isFinite(elapsed) && elapsed >= 0 ? `${(elapsed / 1000).toFixed(1)} s` : undefined;
}
const activityKey = (item: ActivityItem) =>
  JSON.stringify([item.runId ?? null, item.legacy, item.id]);
function Activities({ items }: { items: ActivityItem[] }) {
  const [limit, setLimit] = useState(100);
  if (!items.length) return null;
  const legacy = items.filter(
    (item) =>
      item.legacy &&
      ['tool', 'subagent'].includes(item.kind) &&
      items.some(
        (canonical) =>
          !canonical.legacy && canonical.runId === item.runId && canonical.kind === item.kind,
      ),
  );
  const folded = new Set(legacy);
  const primary = items.filter((item) => !folded.has(item));
  return (
    <details className="activity">
      <summary>
        <Terminal size={15} />
        <span>Activity</span>
        <span className="activity-count">
          {primary.length} {primary.length === 1 ? 'item' : 'items'}
        </span>
        <ChevronDown size={15} />
      </summary>
      <ol aria-label="Lifecycle activity">
        {primary.slice(0, limit).map((item) => {
          const url = item.url ? safePublicUrl(item.url) : undefined;
          const elapsed = duration(item);
          return (
            <li key={activityKey(item)}>
              <div>
                <span className="activity-kind">
                  {item.legacy ? item.kind : item.name}
                  {item.status ? ` · ${item.status.replaceAll('_', ' ')}` : ''}
                </span>
                <span>
                  {elapsed && <span>{elapsed} · </span>}
                  <Timestamp value={item.finishedAt ?? item.updatedAt ?? item.createdAt} />
                </span>
              </div>
              <p>{item.label}</p>
              {item.command && (
                <code className="activity-command" tabIndex={0} aria-label="Tool command">
                  {item.command.slice(0, 6000)}
                </code>
              )}
              {item.url && (
                <p className="activity-url">
                  {url ? (
                    <a href={url} target="_blank" rel="noopener noreferrer">
                      {item.url.slice(0, 2000)}
                    </a>
                  ) : (
                    <span>{item.url.slice(0, 2000)}</span>
                  )}
                </p>
              )}
              {item.detail && (
                <details>
                  <summary>View detail</summary>
                  <pre tabIndex={0}>
                    {item.detail.slice(0, 6000)}
                    {item.detail.length >= 6000 ? '\n[Display limited to 6,000 characters]' : ''}
                  </pre>
                </details>
              )}
            </li>
          );
        })}
      </ol>
      {legacy.length > 0 && (
        <details className="legacy-events">
          <summary>Legacy events ({legacy.length})</summary>
          <p>Compatibility records retained without assuming an individual tool match.</p>
          <ol>
            {legacy.map((item) => (
              <li key={activityKey(item)}>
                <p>{item.label}</p>
                {item.detail && <pre tabIndex={0}>{item.detail.slice(0, 6000)}</pre>}
              </li>
            ))}
          </ol>
        </details>
      )}
      {limit < primary.length && (
        <button className="text-button show-more" onClick={() => setLimit(limit + 100)}>
          Show more activity ({primary.length - limit} remaining)
        </button>
      )}
    </details>
  );
}
function Preview({ artifact }: { artifact: Artifact }) {
  const [failed, setFailed] = useState(false);
  const url = previewUrl(artifact.id, artifact.previewUrl);
  useEffect(() => setFailed(false), [url]);
  if (!url) return null;
  return (
    <figure className="artifact-preview">
      {failed ? (
        <p role="status">Preview unavailable for {artifact.name}. Download the file below.</p>
      ) : (
        <img
          src={url}
          alt={artifact.name}
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
      )}
      <figcaption>{artifact.name}</figcaption>
    </figure>
  );
}
function ErrorNotices({
  items,
  unknownReply = false,
}: {
  items: ActivityItem[];
  unknownReply?: boolean;
}) {
  return (
    <>
      {items
        .filter((item) => item.kind === 'error')
        .map((item) => (
          <div
            key={activityKey(item)}
            className="run-error"
            role="alert"
            aria-label={unknownReply ? 'Error with unknown reply' : 'Reply error'}
          >
            {item.label}
          </div>
        ))}
    </>
  );
}
function Files({
  artifacts,
  zip,
  unassociated = false,
}: {
  artifacts: Artifact[];
  zip?: string;
  unassociated?: boolean;
}) {
  if (!artifacts.length) return null;
  return (
    <section
      className="artifacts"
      aria-label={unassociated ? 'Unassociated files' : 'Files from this reply'}
    >
      <div className="files-heading">
        <h2>{unassociated ? 'Files with unknown reply' : 'Files from this reply'}</h2>
        {artifacts.length > 1 && zip && (
          <a className="zip-link" href={zip} download>
            <Download size={14} />
            Download all ZIP
          </a>
        )}
      </div>
      <div className="reply-gallery">
        {artifacts.map((artifact) => (
          <Preview key={artifact.id} artifact={artifact} />
        ))}
      </div>
      {artifacts.map((artifact) => {
        const url = artifactDownloadUrl(artifact.id);
        const contents = (
          <>
            <span className="artifact-icon">
              <FileText size={19} />
            </span>
            <span>
              <strong>{artifact.name}</strong>
              <small>
                {bytes(artifact.size)} · {url ? 'Download' : 'Download unavailable'}
              </small>
            </span>
            {url && <Download size={17} />}
          </>
        );
        return url ? (
          <a className="artifact" key={artifact.id} href={url} download>
            {contents}
          </a>
        ) : (
          <div className="artifact" key={artifact.id}>
            {contents}
          </div>
        );
      })}
    </section>
  );
}
function UserMessage({ message, thread }: { message: Message; thread: Thread }) {
  const attachments = new Map(thread.attachments.map((attachment) => [attachment.id, attachment]));
  return (
    <article className="message message-user" aria-label="You message">
      <div className="avatar avatar-user">Y</div>
      <div className="message-body">
        <div className="message-meta">
          <strong>You</strong>
          <Timestamp value={message.createdAt} />
        </div>
        <Text message={message} />
        {!!message.attachmentIds?.length && (
          <ul className="message-attachments" aria-label="Uploaded files">
            {message.attachmentIds.map((id) => {
              const attachment = attachments.get(id);
              const url = attachment && attachmentDownloadUrl(id, attachment.downloadUrl);
              return (
                <li key={id}>
                  <Paperclip size={14} />
                  {attachment ? (
                    <>
                      {url ? (
                        <a href={url} download>
                          {attachment.name}
                        </a>
                      ) : (
                        <span>{attachment.name} · Download unavailable</span>
                      )}
                      <small>{bytes(attachment.size)}</small>
                    </>
                  ) : (
                    <span>Attached file · metadata unavailable (legacy upload)</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </article>
  );
}
function AssistantReply({ reply, thread }: { reply: Reply; thread: Thread }) {
  const progress = reply.messages.filter(
    (message) => message.phase === 'intermediate' || message.phase === 'thinking',
  );
  const responses = reply.messages.filter(
    (message) => message.phase !== 'intermediate' && message.phase !== 'thinking',
  );
  const finalReady = responses.some(
    (message) => message.phase === 'final' && message.streamState === 'completed',
  );
  const run = thread.runs.find((run) => run.id === reply.runId);
  const zip =
    reply.runId && run ? runZipUrl(thread.session.id, reply.runId, run.zipUrl) : undefined;
  if (!reply.messages.length && !reply.activity.length && !reply.artifacts.length) return null;
  return (
    <article
      className="message message-assistant assistant-reply"
      aria-label="Assistant reply"
      data-run-id={reply.runId}
    >
      <div className="avatar avatar-assistant">
        <Terminal size={17} />
      </div>
      <div className="message-body">
        {progress.length > 0 && <Progress messages={progress} finalReady={finalReady} />}
        {responses.map((message) => {
          const final = message.phase === 'final';
          return (
            <section
              key={message.id}
              className={final ? 'message-final' : 'message-response'}
              aria-label={final ? 'Final answer' : undefined}
            >
              <div className="message-meta">
                <strong>
                  {final
                    ? 'Final answer'
                    : message.streamState === 'streaming'
                      ? 'Assistant · responding'
                      : 'Legacy response'}
                </strong>
                <Timestamp value={message.createdAt} />
              </div>
              <Text message={message} />
            </section>
          );
        })}
        <ErrorNotices items={reply.activity} />
        <Activities items={reply.activity} />
        <Files artifacts={reply.artifacts} zip={zip} />
      </div>
    </article>
  );
}
export function ConversationReplies({ thread }: { thread: Thread }) {
  const { items, unassociated } = groupReplies(thread);
  return (
    <>
      {items.map((item) =>
        item.kind === 'user' ? (
          <UserMessage key={`user:${item.message.id}`} message={item.message} thread={thread} />
        ) : (
          <AssistantReply key={item.reply.key} reply={item.reply} thread={thread} />
        ),
      )}
      {(unassociated.activity.length > 0 || unassociated.artifacts.length > 0) && (
        <section className="unassociated-history" aria-label="History with unknown reply">
          <p>History with unknown reply association</p>
          <small>These records are preserved, but their reply could not be verified.</small>
          <ErrorNotices items={unassociated.activity} unknownReply />
          <Activities items={unassociated.activity} />
          <Files artifacts={unassociated.artifacts} unassociated />
        </section>
      )}
    </>
  );
}
export function WorkingStatus({ thread }: { thread: Thread }) {
  const runs = [...thread.runs].reverse();
  const current =
    runs.find((run) => run.status === 'cancelling') ??
    runs.find((run) => run.status === 'running') ??
    runs.find((run) => run.status === 'queued');
  // Aggregate session state can briefly become idle between queued turns.
  // A typed pending run still represents real work; preserve other emitted
  // session states, especially compacting, cancelling and terminal failures.
  const status =
    thread.session.status === 'idle'
      ? current?.status === 'cancelling'
        ? 'cancelling'
        : current?.status === 'running'
          ? 'running'
          : current?.status === 'queued'
            ? 'queued'
            : 'idle'
      : thread.session.status;
  const active = isActive(status);
  const summary =
    current?.subagents ??
    (!active && runs[0]?.subagents.active === 0 ? runs[0].subagents : undefined);
  const known = summary?.known && Number.isSafeInteger(summary.active) && summary.active! >= 0;
  const queued = thread.runs.filter((run) => run.status === 'queued').length;
  return (
    <div
      className={`working-status ${active ? 'is-working' : ''}`}
      role="status"
      aria-label="Run status"
      aria-live="polite"
    >
      <span>
        {active && <LoaderCircle className="working-spinner" size={16} aria-hidden="true" />}
        <strong>
          {active
            ? status === 'running'
              ? 'Running · working'
              : status[0].toUpperCase() + status.slice(1)
            : status === 'idle'
              ? 'Ready'
              : status}
        </strong>
      </span>
      <span>{known ? `Active subagents: ${summary.active}` : 'Active subagents: unknown'}</span>
      {queued > 0 && <span>{queued} queued for next turn</span>}
    </div>
  );
}
