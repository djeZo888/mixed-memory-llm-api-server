import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { ConversationReplies, WorkingStatus } from '../src/Replies';
import { formatTime } from '../src/display';
import { applyEvent } from '../src/state';
import { HarnessStore } from '../src/store';
import {
  artifactDownloadUrl,
  attachmentDownloadUrl,
  previewUrl,
  runZipUrl,
  safePublicUrl,
} from '../src/urls';
import { createdAt, fixtureTransport, session, snapshot } from './fixtures';
import {
  replyActivity,
  replyArtifact,
  replyMessage,
  replyRun,
  replyThread,
  runEvent,
} from './reply-fixtures';

describe('reply-level conversation presentation', () => {
  it('collapses emitted progress when a final arrives, preserving text for reopening and reload', async () => {
    const user = userEvent.setup();
    let thread = replyThread({
      messages: [
        replyMessage('question', 'user', 'Inspect the fixtures', { runId: 'run/one' }),
        replyMessage('progress', 'assistant', 'I am checking the fixtures.', {
          runId: 'run/one',
          phase: 'intermediate',
          streamState: 'streaming',
        }),
      ],
      runs: [replyRun('run/one')],
    });
    const { rerender, unmount } = render(<ConversationReplies thread={thread} />);
    expect(
      screen.getByText('Progress', { selector: 'summary span' }).closest('details'),
    ).toHaveAttribute('open');
    thread = applyEvent(
      thread,
      runEvent(
        1,
        'message',
        {
          message: replyMessage('progress', 'assistant', 'I am checking the fixtures.', {
            runId: 'run/one',
            phase: 'intermediate',
            streamState: 'completed',
          }),
        },
        'run/one',
      ),
    );
    thread = applyEvent(
      thread,
      runEvent(
        2,
        'assistant_delta',
        {
          messageId: 'final',
          text: 'The fixtures pass.',
          phase: 'unclassified',
        },
        'run/one',
      ),
    );
    rerender(<ConversationReplies thread={thread} />);
    expect(screen.queryByLabelText('Final answer')).not.toBeInTheDocument();
    thread = applyEvent(
      thread,
      runEvent(
        3,
        'message',
        {
          message: replyMessage('final', 'assistant', 'The fixtures pass.', {
            runId: 'run/one',
            phase: 'final',
            streamState: 'completed',
          }),
        },
        'run/one',
      ),
    );
    rerender(<ConversationReplies thread={thread} />);
    const progress = screen.getByText('Progress', { selector: 'summary span' }).closest('details');
    expect(progress).not.toHaveAttribute('open');
    expect(screen.getByLabelText('Final answer')).toHaveClass('message-final');
    expect(
      within(screen.getByLabelText('Final answer')).getByText('The fixtures pass.'),
    ).toBeInTheDocument();
    expect(within(progress!).getByText('I am checking the fixtures.')).toBeInTheDocument();
    await user.click(screen.getByText('Progress', { selector: 'summary span' }));
    expect(progress).toHaveAttribute('open');
    unmount();
    render(<ConversationReplies thread={thread} />);
    expect(
      screen.getByText('Progress', { selector: 'summary span' }).closest('details'),
    ).not.toHaveAttribute('open');
    expect(screen.getByText('I am checking the fixtures.')).toBeInTheDocument();
    expect(screen.getByText('The fixtures pass.')).toBeInTheDocument();
  });

  it('retains legacy assistant text without inventing a progress/final phase', () => {
    const thread = replyThread({
      messages: [
        replyMessage('old-user', 'user', 'Earlier request'),
        replyMessage('old-answer', 'assistant', 'Earlier complete answer'),
      ],
    });
    render(<ConversationReplies thread={thread} />);
    expect(screen.getByText('Earlier request')).toBeInTheDocument();
    expect(screen.getByText('Earlier complete answer')).toBeInTheDocument();
    expect(screen.queryByText('Progress')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Final answer')).not.toBeInTheDocument();
  });

  it('keeps unassociated historic activity visible without attributing it to the latest reply', () => {
    const thread = replyThread({
      messages: [
        replyMessage('user-one', 'user', 'First request', { runId: 'run/one' }),
        replyMessage('answer-one', 'assistant', 'First answer', { runId: 'run/one' }),
        replyMessage('user-two', 'user', 'Second request', { runId: 'run/two' }),
        replyMessage('answer-two', 'assistant', 'Second answer', { runId: 'run/two' }),
      ],
      events: [
        runEvent(1, 'progress', { kind: 'tool', label: 'Orphan tool activity' }, 'missing-run'),
      ],
    });
    render(<ConversationReplies thread={thread} />);
    const replies = screen.getAllByRole('article', { name: 'Assistant reply' });
    expect(replies).toHaveLength(2);
    for (const reply of replies)
      expect(within(reply).queryByText('Orphan tool activity')).not.toBeInTheDocument();
    expect(screen.getByText('Orphan tool activity', { selector: 'p' })).toBeInTheDocument();
  });

  it('scopes historical run failures to their reply and keeps unknown failures separate from later successful replies', () => {
    const thread = replyThread({
      messages: [
        replyMessage('failed-answer', 'assistant', 'Earlier partial response', {
          runId: 'failed-run',
        }),
        replyMessage('success-answer', 'assistant', 'Later successful response', {
          runId: 'success-run',
          phase: 'final',
          streamState: 'completed',
        }),
      ],
      events: [
        runEvent(
          1,
          'error',
          { code: 'old_failure', message: 'Earlier run failed during inspection' },
          'failed-run',
        ),
        runEvent(
          2,
          'error',
          { code: 'legacy_failure', message: 'Archived failure without matching reply' },
          'unknown-run',
        ),
      ],
    });
    render(<ConversationReplies thread={thread} />);
    const [earlier, later] = screen.getAllByRole('article', { name: 'Assistant reply' });
    expect(within(earlier).getByRole('alert', { name: 'Reply error' })).toHaveTextContent(
      'Earlier run failed during inspection',
    );
    expect(within(later).queryByRole('alert')).not.toBeInTheDocument();
    expect(within(later).queryByText(/failed|failure/)).not.toBeInTheDocument();
    const unknown = screen.getByLabelText('History with unknown reply');
    expect(
      within(unknown).getByRole('alert', { name: 'Error with unknown reply' }),
    ).toHaveTextContent('Archived failure without matching reply');
  });

  it('does not manufacture active subagents from prose or tool activity', () => {
    const thread = replyThread({
      messages: [replyMessage('answer', 'assistant', 'I have 12 active agents working now.')],
      events: [
        runEvent(1, 'progress', { kind: 'subagent', label: 'Agent started' }, 'run/one'),
        runEvent(2, 'progress', { kind: 'tool', label: 'spawn_agent' }, 'run/one'),
      ],
    });
    const { container } = render(<WorkingStatus thread={thread} />);
    expect(container).not.toHaveTextContent(/12 active|2 active|1 active/);
  });

  it('keeps files, ZIP downloads and lifecycle activities with their exact reply across multiple turns', () => {
    const artifacts = [
      replyArtifact('one-a', 'first-report.txt', { runId: 'run/one', messageId: 'answer-one' }),
      replyArtifact('one-b', 'first-diagram.svg', { runId: 'run/one', messageId: 'answer-one' }),
      replyArtifact('two-a', 'second-report.txt', { runId: 'run/two', messageId: 'answer-two' }),
    ];
    const thread = replyThread({
      messages: [
        replyMessage('user-one', 'user', 'First request', { runId: 'run/one' }),
        replyMessage('answer-one', 'assistant', 'First answer', {
          runId: 'run/one',
          phase: 'final',
        }),
        replyMessage('user-two', 'user', 'Second request', { runId: 'run/two' }),
        replyMessage('answer-two', 'assistant', 'Second answer', {
          runId: 'run/two',
          phase: 'final',
        }),
      ],
      artifacts,
      activities: [
        replyActivity('tool-1', { runId: 'run/one', command: 'printf first', status: 'completed' }),
        replyActivity('tool-2', {
          runId: 'run/two',
          command: 'printf second',
          status: 'completed',
        }),
      ],
      runs: [
        replyRun('run/one', {
          status: 'completed',
          finalMessageId: 'answer-one',
          artifactIds: ['one-a', 'one-b'],
          zipUrl: '/api/sessions/chat%2Fa/runs/run%2Fone/artifacts.zip',
        }),
        replyRun('run/two', {
          status: 'completed',
          finalMessageId: 'answer-two',
          artifactIds: ['two-a'],
          zipUrl: '/api/sessions/chat%2Fa/runs/run%2Ftwo/artifacts.zip',
        }),
      ],
    });
    render(<ConversationReplies thread={thread} />);
    const [first, second] = screen.getAllByRole('article', { name: 'Assistant reply' });
    expect(within(first).getByText('first-report.txt')).toBeInTheDocument();
    expect(within(first).getByText('first-diagram.svg')).toBeInTheDocument();
    expect(within(first).getByText('printf first')).toBeInTheDocument();
    expect(within(first).queryByText('second-report.txt')).not.toBeInTheDocument();
    expect(within(first).queryByText('printf second')).not.toBeInTheDocument();
    expect(within(first).getByRole('link', { name: 'Download all ZIP' })).toHaveAttribute(
      'href',
      '/api/sessions/chat%2Fa/runs/run%2Fone/artifacts.zip',
    );
    expect(within(second).getByText('second-report.txt')).toBeInTheDocument();
    expect(within(second).getByText('printf second')).toBeInTheDocument();
    expect(
      within(second).queryByRole('link', { name: 'Download all ZIP' }),
    ).not.toBeInTheDocument();
    expect(within(second).queryByText('first-report.txt')).not.toBeInTheDocument();
  });

  it('retains conflicting and unknown file associations visibly without adding them to a reply ZIP', () => {
    const thread = replyThread({
      messages: [
        replyMessage('answer-one', 'assistant', 'First answer', { runId: 'run/one' }),
        replyMessage('answer-two', 'assistant', 'Second answer', { runId: 'run/two' }),
      ],
      artifacts: [
        replyArtifact('conflict', 'conflicting.txt', { runId: 'run/two', messageId: 'answer-one' }),
        replyArtifact('missing', 'unassociated.txt'),
      ],
    });
    render(<ConversationReplies thread={thread} />);
    for (const reply of screen.getAllByRole('article', { name: 'Assistant reply' })) {
      expect(within(reply).queryByText('conflicting.txt')).not.toBeInTheDocument();
      expect(within(reply).queryByText('unassociated.txt')).not.toBeInTheDocument();
    }
    expect(screen.getByText('conflicting.txt')).toBeInTheDocument();
    expect(screen.getByText('unassociated.txt')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Download all ZIP' })).not.toBeInTheDocument();
  });

  it('uses an exact message ID when legacy message run metadata is absent without inventing a ZIP association', () => {
    const thread = replyThread({
      messages: [
        replyMessage('legacy-answer', 'assistant', 'Legacy answer with exact file identity'),
      ],
      artifacts: [
        replyArtifact('exact-one', 'exact-one.txt', {
          messageId: 'legacy-answer',
          runId: 'known-run',
        }),
        replyArtifact('exact-two', 'exact-two.txt', {
          messageId: 'legacy-answer',
          runId: 'known-run',
        }),
      ],
      runs: [
        replyRun('known-run', {
          status: 'completed',
          artifactIds: ['exact-one', 'exact-two'],
          zipUrl: '/api/sessions/chat%2Fa/runs/known-run/artifacts.zip',
        }),
      ],
    });
    render(<ConversationReplies thread={thread} />);
    const reply = screen.getByRole('article', { name: 'Assistant reply' });
    expect(within(reply).getByText('exact-one.txt')).toBeInTheDocument();
    expect(within(reply).getByText('exact-two.txt')).toBeInTheDocument();
    expect(screen.queryByLabelText('History with unknown reply')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Download all ZIP' })).not.toBeInTheDocument();
  });

  it('resolves uploaded names and reviewed downloads only on the corresponding user message', () => {
    const thread = replyThread({
      messages: [
        replyMessage('user-one', 'user', 'Read my notes', { attachmentIds: ['upload/one'] }),
        replyMessage('assistant-one', 'assistant', 'Read complete'),
        replyMessage('user-two', 'user', 'Legacy upload', { attachmentIds: ['missing-id'] }),
      ],
      attachments: [
        {
          id: 'upload/one',
          name: 'research-notes.txt',
          size: 10,
          mimeType: 'text/plain',
          downloadUrl: '/api/attachments/upload%2Fone/download',
        },
      ],
    });
    render(<ConversationReplies thread={thread} />);
    const userMessage = screen.getByText('Read my notes').closest('article')!;
    const attachment = within(userMessage).getByRole('link', { name: /research-notes.txt/ });
    expect(attachment).toHaveAttribute('href', '/api/attachments/upload%2Fone/download');
    expect(attachment).toHaveAttribute('download');
    expect(
      within(screen.getByText('Read complete').closest('article')!).queryByText(
        'research-notes.txt',
      ),
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByText('Legacy upload').closest('article')!).getByText(
        /metadata unavailable/i,
      ),
    ).toBeInTheDocument();
  });

  it('uses only reviewed image URLs, keeps downloads, and handles preview load errors', () => {
    const thread = replyThread({
      messages: [
        replyMessage('answer', 'assistant', 'Generated diagrams', {
          runId: 'run/one',
          phase: 'final',
        }),
      ],
      artifacts: [
        replyArtifact('safe-svg', 'diagram.svg', {
          runId: 'run/one',
          mimeType: 'image/svg+xml',
          previewUrl: '/api/files/safe-svg/preview',
        }),
        replyArtifact('unsafe-svg', 'old.svg', {
          runId: 'run/one',
          mimeType: 'image/svg+xml',
          previewUrl: 'https://tracking.example/pixel.svg',
          downloadUrl: 'javascript:alert(1)',
        }),
      ],
    });
    const { container } = render(<ConversationReplies thread={thread} />);
    const preview = screen.getByRole('img', { name: 'diagram.svg' });
    expect(preview).toHaveAttribute('src', '/api/files/safe-svg/preview');
    expect(screen.queryByRole('img', { name: 'old.svg' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /diagram.svg/ })).toHaveAttribute(
      'href',
      '/api/artifacts/safe-svg/download',
    );
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(container.querySelector('svg script, iframe')).toBeNull();
    fireEvent.error(preview);
    expect(screen.queryByRole('img', { name: 'diagram.svg' })).not.toBeInTheDocument();
    expect(screen.getByText(/preview unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /diagram.svg/ })).toHaveAttribute('download');
  });

  it('shows authoritative subagent snapshots and updates without counting unrelated history', () => {
    let thread = replyThread({
      session: { ...session(), status: 'running' },
      runs: [
        replyRun('old-run', {
          status: 'completed',
          subagents: { known: true, active: 12, completed: 0, failed: 0, cancelled: 0 },
        }),
        replyRun('run/one', {
          subagents: { known: true, active: 2, completed: 1, failed: 0, cancelled: 0 },
        }),
      ],
    });
    const { rerender } = render(<WorkingStatus thread={thread} />);
    expect(screen.getByRole('status', { name: 'Run status' })).toHaveTextContent(/2/);
    expect(screen.getByRole('status', { name: 'Run status' })).not.toHaveTextContent(/12/);
    thread = applyEvent(
      thread,
      runEvent(
        1,
        'subagents',
        {
          runId: 'run/one',
          summary: { known: true, active: 0, completed: 3, failed: 0, cancelled: 0 },
        },
        'run/one',
      ),
    );
    rerender(<WorkingStatus thread={thread} />);
    expect(screen.getByRole('status', { name: 'Run status' })).toHaveTextContent(/0/);
    expect(screen.getByRole('status', { name: 'Run status' })).toHaveTextContent(/running/i);
  });

  it('renders one updated lifecycle item with inert command/detail and emitted duration', async () => {
    const user = userEvent.setup();
    const command = '<img src=x onerror=alert(1)> && printf output';
    let thread = replyThread({
      messages: [replyMessage('answer', 'assistant', 'Tool result', { runId: 'run/one' })],
    });
    thread = applyEvent(
      thread,
      runEvent(
        1,
        'activity',
        {
          activity: replyActivity('opaque/tool/1', {
            status: 'pending',
            command,
            startedAt: '2026-09-22T12:00:00.000Z',
          }),
        },
        'run/one',
      ),
    );
    thread = applyEvent(
      thread,
      runEvent(
        2,
        'activity',
        {
          activity: replyActivity('opaque/tool/1', {
            status: 'in_progress',
            command,
            startedAt: '2026-09-22T12:00:00.000Z',
            url: 'https://example.com/result',
          }),
        },
        'run/one',
      ),
    );
    thread = applyEvent(
      thread,
      runEvent(
        3,
        'activity',
        {
          activity: replyActivity('opaque/tool/1', {
            status: 'completed',
            command,
            startedAt: '2026-09-22T12:00:00.000Z',
            finishedAt: '2026-09-22T12:00:02.500Z',
            url: 'https://example.com/result',
            detail: '<script>window.injected=true</script>',
          }),
        },
        'run/one',
      ),
    );
    const { container } = render(<ConversationReplies thread={thread} />);
    await user.click(screen.getByText('Activity'));
    expect(container.querySelectorAll('.activity > ol > li')).toHaveLength(1);
    expect(screen.getByText(command)).toBeInTheDocument();
    expect(screen.getByLabelText('Tool command')).toHaveAttribute('tabindex', '0');
    expect(screen.getByText(/2.5 s/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'https://example.com/result' })).toHaveAttribute(
      'href',
      'https://example.com/result',
    );
    await user.click(screen.getByText('View detail'));
    expect(screen.getByText('<script>window.injected=true</script>')).toBeInTheDocument();
    expect(container.querySelector('script, img, iframe')).toBeNull();
  });

  it('folds legacy generic rows when canonical lifecycle data exists while preserving every old event on reload', async () => {
    const user = userEvent.setup();
    const messages = [replyMessage('answer', 'assistant', 'Result', { runId: 'run/one' })];
    const typed = replyActivity('tool/one', {
      status: 'completed',
      summary: 'Actual command completed',
      command: 'printf complete',
    });
    const events = [
      runEvent(1, 'progress', { kind: 'tool', label: 'Legacy tool started' }, 'run/one'),
      runEvent(
        2,
        'activity',
        {
          activity: replyActivity('tool/one', {
            status: 'in_progress',
            command: 'printf complete',
          }),
        },
        'run/one',
      ),
      runEvent(3, 'progress', { kind: 'tool', label: 'Legacy tool input' }, 'run/one'),
      runEvent(4, 'activity', { activity: typed }, 'run/one'),
      runEvent(5, 'progress', { kind: 'tool', label: 'Legacy tool completed' }, 'run/one'),
    ];
    let thread = replyThread({ messages });
    for (const event of events) thread = applyEvent(thread, event);
    const { container, unmount } = render(<ConversationReplies thread={thread} />);
    await user.click(screen.getByText('Activity'));
    expect(container.querySelectorAll('.activity > ol > li')).toHaveLength(1);
    const legacy = screen.getByText(/^Legacy events/).closest('details')!;
    expect(legacy).not.toHaveAttribute('open');
    await user.click(screen.getByText(/^Legacy events/));
    expect(legacy).toHaveAttribute('open');
    expect(legacy).toHaveTextContent('Legacy tool started');
    expect(legacy).toHaveTextContent('Legacy tool input');
    expect(legacy).toHaveTextContent('Legacy tool completed');
    unmount();
    const reloaded = replyThread({ messages, events, activities: [typed] });
    const restored = render(<ConversationReplies thread={reloaded} />);
    expect(restored.container.querySelectorAll('.activity > ol > li')).toHaveLength(1);
    expect(screen.getByText(/^Legacy events/).closest('details')).toHaveTextContent(
      'Legacy tool completed',
    );
    expect(screen.getByText('printf complete')).toBeInTheDocument();
  });

  it('keeps the current reply before a queued followup even if its final arrives later', () => {
    const thread = replyThread({
      messages: [
        replyMessage('user-one', 'user', 'Current request', { runId: 'run/one' }),
        replyMessage('user-two', 'user', 'Queued followup', { runId: 'run/two' }),
        replyMessage('answer-one', 'assistant', 'Current final', {
          runId: 'run/one',
          phase: 'final',
          streamState: 'completed',
        }),
      ],
      runs: [
        replyRun('run/one', { status: 'completed' }),
        replyRun('run/two', { status: 'queued' }),
      ],
    });
    const { rerender } = render(<ConversationReplies thread={thread} />);
    const articles = screen.getAllByRole('article');
    expect(articles[0]).toHaveTextContent('Current request');
    expect(articles[1]).toHaveTextContent('Current final');
    expect(articles[2]).toHaveTextContent('Queued followup');
    const updated = applyEvent(
      thread,
      runEvent(
        1,
        'message',
        {
          message: replyMessage('answer-two', 'assistant', 'Followup final', {
            runId: 'run/two',
            phase: 'final',
            streamState: 'completed',
          }),
        },
        'run/two',
      ),
    );
    rerender(<ConversationReplies thread={updated} />);
    expect(screen.getAllByRole('article')[3]).toHaveTextContent('Followup final');
  });

  it('keeps opaque native IDs distinct from legacy event IDs during lifecycle updates', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    let thread = replyThread({
      messages: [replyMessage('answer', 'assistant', 'Result', { runId: 'run/one' })],
      events: [
        runEvent(1, 'progress', { kind: 'shell', label: 'Legacy command event' }, 'run/one'),
      ],
      activities: [replyActivity('event:1', { summary: 'Native command started' })],
    });
    const { container, rerender } = render(<ConversationReplies thread={thread} />);
    thread = applyEvent(
      thread,
      runEvent(
        2,
        'activity',
        {
          activity: replyActivity('event:1', {
            status: 'completed',
            summary: 'Native command finished',
          }),
        },
        'run/one',
      ),
    );
    rerender(<ConversationReplies thread={thread} />);
    expect(container.querySelectorAll('.activity > ol > li')).toHaveLength(2);
    expect(screen.getByText('Legacy command event')).toBeInTheDocument();
    expect(screen.getByText('Native command finished')).toBeInTheDocument();
    expect(screen.queryByText('Native command started')).not.toBeInTheDocument();
    expect(error).not.toHaveBeenCalled();
  });

  it('preserves malformed artifact records as inert unavailable downloads', () => {
    const thread = replyThread({
      messages: [replyMessage('answer', 'assistant', 'Files', { runId: 'run/one' })],
      artifacts: [
        replyArtifact('..', 'invalid-parent.txt', { runId: 'run/one' }),
        replyArtifact('', 'invalid-empty.txt', { runId: 'run/one' }),
        replyArtifact('valid/id', 'valid.txt', { runId: 'run/one' }),
      ],
    });
    render(<ConversationReplies thread={thread} />);
    expect(screen.getByText('invalid-parent.txt').closest('a')).toBeNull();
    expect(screen.getByText('invalid-empty.txt').closest('a')).toBeNull();
    expect(screen.getAllByText(/Download unavailable/)).toHaveLength(2);
    expect(screen.getByRole('link', { name: /valid.txt/ })).toHaveAttribute(
      'href',
      '/api/artifacts/valid%2Fid/download',
    );
  });

  it('preserves interrupted progress and labels reasoning only for the authoritative thinking phase', () => {
    const thread = replyThread({
      session: { ...session(), status: 'interrupted' },
      messages: [
        replyMessage('progress', 'assistant', 'Completed inspection before interruption.', {
          runId: 'run/one',
          phase: 'intermediate',
        }),
        replyMessage('reasoning', 'assistant', 'Actual emitted reasoning text.', {
          runId: 'run/one',
          phase: 'thinking',
        }),
        replyMessage(
          'unclassified',
          'assistant',
          'Analysis: this heading does not classify my phase.',
          { runId: 'run/one', phase: 'unclassified' },
        ),
      ],
    });
    render(<ConversationReplies thread={thread} />);
    const progress = screen.getByText('Progress', { selector: 'summary span' }).closest('details')!;
    expect(progress).toHaveAttribute('open');
    expect(within(progress).getByText('Actual emitted reasoning text.')).toBeInTheDocument();
    expect(within(progress).getByText('Reasoning')).toBeInTheDocument();
    expect(
      within(progress).queryByText('Analysis: this heading does not classify my phase.'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText('Analysis: this heading does not classify my phase.'),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText('Final answer')).not.toBeInTheDocument();
  });

  it('places active work status outside the composer while keeping Stop available', async () => {
    const { transport, streams } = fixtureTransport();
    transport.snapshot.mockImplementation(async () => ({
      ...snapshot(),
      session: { ...session(), status: 'running' },
    }));
    render(<App store={new HarnessStore(transport)} />);
    const working = await screen.findByRole('status', { name: 'Run status' });
    expect(working).toHaveTextContent(/running/i);
    expect(working.closest('.composer-wrap')).toBeNull();
    expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument();
    act(() =>
      streams[0].callbacks.event(runEvent(1, 'state', { status: 'compacting' }, 'run/one')),
    );
    expect(working).toHaveTextContent(/compacting/i);
  });

  it.each(['queued', 'running', 'compacting', 'cancelling'] as const)(
    'announces emitted %s status',
    (status) => {
      const thread = replyThread({ session: { ...session(), status } });
      render(<WorkingStatus thread={thread} />);
      expect(screen.getByRole('status')).toHaveTextContent(new RegExp(status, 'i'));
    },
  );

  it.each(['queued', 'running', 'cancelling'] as const)(
    'keeps real %s work visible when aggregate session state briefly says idle',
    (status) => {
      const thread = replyThread({ runs: [replyRun('current', { status })] });
      const { container } = render(<WorkingStatus thread={thread} />);
      expect(screen.getByRole('status', { name: 'Run status' })).toHaveTextContent(
        new RegExp(status, 'i'),
      );
      expect(screen.getByRole('status', { name: 'Run status' })).not.toHaveTextContent('Ready');
      expect(container.querySelector('.working-spinner')).toBeInTheDocument();
    },
  );

  it.each(['compacting', 'cancelling', 'failed', 'interrupted'] as const)(
    'preserves emitted %s session state while per-run updates catch up',
    (status) => {
      const thread = replyThread({
        session: { ...session(), status },
        runs: [replyRun('current', { status: 'running' })],
      });
      render(<WorkingStatus thread={thread} />);
      expect(screen.getByRole('status', { name: 'Run status' })).toHaveTextContent(
        new RegExp(status, 'i'),
      );
    },
  );

  it('does not reuse a historic completed zero count while a new current run remains unknown', () => {
    const thread = replyThread({
      session: { ...session(), status: 'running' },
      runs: [
        replyRun('old', {
          status: 'completed',
          subagents: { known: true, active: 0, completed: 5, failed: 0, cancelled: 0 },
        }),
      ],
    });
    render(<WorkingStatus thread={thread} />);
    expect(screen.getByRole('status', { name: 'Run status' })).toHaveTextContent(
      'Active subagents: unknown',
    );
  });

  it('retains Stop when typed work is pending despite idle aggregate state', async () => {
    const { transport } = fixtureTransport();
    transport.snapshot.mockImplementation(async () => ({
      ...snapshot(),
      runs: [replyRun('pending', { status: 'queued' })],
    }));
    render(<App store={new HarnessStore(transport)} />);
    expect(await screen.findByRole('status', { name: 'Run status' })).toHaveTextContent(/queued/i);
    expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument();
  });
});

describe('Ljubljana display time', () => {
  it('uses automatic winter and summer offsets while preserving ISO timestamps', () => {
    const winter = '2026-01-15T12:00:00.000Z';
    const summer = '2026-07-15T12:00:00.000Z';
    expect(formatTime(winter)).toBe('13:00');
    expect(formatTime(summer)).toBe('14:00');
    const thread = replyThread({
      messages: [
        replyMessage('winter', 'user', 'Winter timestamp', { createdAt: winter }),
        replyMessage('summer', 'user', 'Summer timestamp', { createdAt: summer }),
      ],
    });
    const { container } = render(<ConversationReplies thread={thread} />);
    expect(container.querySelector(`time[datetime="${winter}"]`)).toHaveTextContent('13:00');
    expect(container.querySelector(`time[datetime="${summer}"]`)).toHaveTextContent('14:00');
    expect(formatTime('not-a-timestamp')).toBe('');
    expect(formatTime(createdAt)).toBe('14:00');
  });
});

describe('tool destination safety', () => {
  it('permits an explicit public HTTP(S) destination', () => {
    expect(safePublicUrl('https://example.com/research?topic=weather')).toBe(
      'https://example.com/research?topic=weather',
    );
  });

  it.each([
    'javascript:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'file:///etc/passwd',
    '//example.com/path',
    'https://user:password@example.com/',
    'https://example.com/\nscript',
    'http://localhost/',
    'http://worker.internal/',
    'http://printer.local/',
    'http://intranet/',
    'http://127.0.0.1/',
    'http://2130706433/',
    'http://10.0.0.1/',
    'http://169.254.169.254/',
    'http://[::1]/',
  ])('does not link unsafe destination %s', (url) => {
    expect(safePublicUrl(url)).toBeUndefined();
  });
});

describe('reviewed file route safety', () => {
  it('accepts only the matching authoritative ID and route', () => {
    expect(artifactDownloadUrl('file/one')).toBe('/api/artifacts/file%2Fone/download');
    expect(previewUrl('file/one', '/api/files/file%2Fone/preview')).toBe(
      '/api/files/file%2Fone/preview',
    );
    expect(attachmentDownloadUrl('upload/one', '/api/attachments/upload%2Fone/download')).toBe(
      '/api/attachments/upload%2Fone/download',
    );
    expect(
      runZipUrl('chat/a', 'run/one', '/api/sessions/chat%2Fa/runs/run%2Fone/artifacts.zip'),
    ).toBe('/api/sessions/chat%2Fa/runs/run%2Fone/artifacts.zip');
    expect(previewUrl('file/one')).toBeUndefined();
    expect(attachmentDownloadUrl('upload/one')).toBeUndefined();
    expect(runZipUrl('chat/a', 'run/one')).toBeUndefined();
  });

  it.each([
    'https://example.com/api/files/file/preview',
    '//example.com/api/files/file/preview',
    '/api/files/other/preview',
    '/api/files/file/download',
    '/api/files/file/preview?redirect=https://example.com',
    '/api/files/file/preview#fragment',
    'data:image/svg+xml,<svg onload=alert(1)>',
    'javascript:alert(1)',
  ])('rejects arbitrary preview URL %s', (supplied) => {
    expect(previewUrl('file', supplied)).toBeUndefined();
  });

  it('rejects traversal IDs, wrong-turn ZIP URLs and malicious upload downloads', () => {
    expect(artifactDownloadUrl('')).toBeUndefined();
    expect(artifactDownloadUrl('.')).toBeUndefined();
    expect(artifactDownloadUrl('..')).toBeUndefined();
    expect(artifactDownloadUrl('file\n')).toBeUndefined();
    expect(previewUrl('..', '/api/files/../preview')).toBeUndefined();
    expect(previewUrl('.', '/api/files/./preview')).toBeUndefined();
    expect(previewUrl('file\n', '/api/files/file%0A/preview')).toBeUndefined();
    expect(
      runZipUrl('chat/a', 'run/one', '/api/sessions/chat%2Fa/runs/run%2Ftwo/artifacts.zip'),
    ).toBeUndefined();
    expect(attachmentDownloadUrl('upload', 'javascript:alert(1)')).toBeUndefined();
    expect(attachmentDownloadUrl('upload', '/api/attachments/other/download')).toBeUndefined();
  });
});
