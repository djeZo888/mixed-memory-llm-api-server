import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ConversationReplies } from '../src/Replies';
import { groupReplies, type Reply } from '../src/reply-groups';
import type { Thread } from '../src/types';
import {
  replyActivity,
  replyArtifact,
  replyMessage,
  replyRun,
  replyThread,
  runEvent,
} from './reply-fixtures';

function replyFor(thread: Thread, runId: string): Reply {
  const reply = groupReplies(thread).items.find(
    (item) => item.kind === 'reply' && item.reply.runId === runId,
  );
  expect(reply?.kind).toBe('reply');
  if (!reply || reply.kind !== 'reply') throw new Error(`Missing reply for ${runId}`);
  return reply.reply;
}

const twoTurns = () => [
  replyMessage('user-one', 'user', 'First request', { runId: 'run/one' }),
  replyMessage('answer-one', 'assistant', 'First answer', {
    runId: 'run/one',
    phase: 'final',
    streamState: 'completed',
  }),
  replyMessage('user-two', 'user', 'Second request', { runId: 'run/two' }),
  replyMessage('answer-two', 'assistant', 'Second answer', {
    runId: 'run/two',
    phase: 'final',
    streamState: 'completed',
  }),
];

describe('authoritative run artifact memberships', () => {
  it('shows one immutable artifact once in every proven run and keeps each run ZIP separate', () => {
    const shared = replyArtifact('shared/blob', 'shared-report.txt', {
      runId: 'run/one',
      messageId: 'answer-one',
    });
    const thread = replyThread({
      messages: twoTurns(),
      artifacts: [
        shared,
        replyArtifact('first-only', 'first-only.txt'),
        replyArtifact('second-only', 'second-only.txt'),
      ],
      runs: [
        replyRun('run/one', {
          status: 'completed',
          artifactIds: ['shared/blob', 'shared/blob', 'first-only'],
          zipUrl: '/api/sessions/chat%2Fa/runs/run%2Fone/artifacts.zip',
        }),
        replyRun('run/two', {
          status: 'completed',
          artifactIds: ['second-only', 'shared/blob', 'shared/blob'],
          zipUrl: '/api/sessions/chat%2Fa/runs/run%2Ftwo/artifacts.zip',
        }),
      ],
    });
    const original = JSON.stringify(thread);
    Object.freeze(thread.artifacts[0]);
    const grouped = groupReplies(thread);
    const replies = grouped.items.flatMap((item) => (item.kind === 'reply' ? [item.reply] : []));
    const firstReply = replies.find((reply) => reply.runId === 'run/one')!;
    const secondReply = replies.find((reply) => reply.runId === 'run/two')!;
    expect(firstReply.artifacts.map((file) => file.id)).toEqual(['shared/blob', 'first-only']);
    expect(secondReply.artifacts.map((file) => file.id)).toEqual(['shared/blob', 'second-only']);
    expect(firstReply.artifacts[0]).toBe(thread.artifacts[0]);
    expect(secondReply.artifacts[0]).toBe(firstReply.artifacts[0]);
    expect(JSON.stringify(thread)).toBe(original);
    expect(grouped.unassociated.artifacts).toHaveLength(0);
    render(<ConversationReplies thread={thread} />);
    const [first, second] = screen.getAllByRole('article', { name: 'Assistant reply' });
    for (const reply of [first, second]) {
      expect(within(reply).getAllByText('shared-report.txt')).toHaveLength(1);
      expect(within(reply).getByRole('link', { name: /shared-report.txt/ })).toHaveAttribute(
        'href',
        '/api/artifacts/shared%2Fblob/download',
      );
    }
    expect(within(first).getByRole('link', { name: 'Download all ZIP' })).toHaveAttribute(
      'href',
      '/api/sessions/chat%2Fa/runs/run%2Fone/artifacts.zip',
    );
    expect(within(second).getByRole('link', { name: 'Download all ZIP' })).toHaveAttribute(
      'href',
      '/api/sessions/chat%2Fa/runs/run%2Ftwo/artifacts.zip',
    );
    expect(within(first).queryByText('second-only.txt')).not.toBeInTheDocument();
    expect(within(second).queryByText('first-only.txt')).not.toBeInTheDocument();
  });

  it('uses run membership when both scalar artifact association fields are null', () => {
    const thread = replyThread({
      messages: twoTurns(),
      artifacts: [replyArtifact('member', 'member.txt', { runId: null, messageId: null })],
      runs: [replyRun('run/two', { artifactIds: ['member'] })],
    });
    expect(replyFor(thread, 'run/one').artifacts).toHaveLength(0);
    expect(replyFor(thread, 'run/two').artifacts.map((file) => file.id)).toEqual(['member']);
    expect(groupReplies(thread).unassociated.artifacts).toHaveLength(0);
    render(<ConversationReplies thread={thread} />);
    const [first, second] = screen.getAllByRole('article', { name: 'Assistant reply' });
    expect(within(first).queryByText('member.txt')).not.toBeInTheDocument();
    expect(within(second).getByText('member.txt')).toBeInTheDocument();
  });

  it('preserves contradictory scalar claims visibly while attaching only to proven memberships', () => {
    const thread = replyThread({
      messages: twoTurns(),
      artifacts: [
        replyArtifact('conflict', 'conflicted-file.txt', {
          runId: 'run/two',
          messageId: 'answer-two',
        }),
      ],
      runs: [replyRun('run/one', { artifactIds: ['conflict'] }), replyRun('run/two')],
    });
    expect(replyFor(thread, 'run/one').artifacts.map((file) => file.id)).toEqual(['conflict']);
    expect(replyFor(thread, 'run/two').artifacts).toHaveLength(0);
    expect(groupReplies(thread).unassociated.artifacts.map((file) => file.id)).toEqual([
      'conflict',
    ]);
    render(<ConversationReplies thread={thread} />);
    const [first, second] = screen.getAllByRole('article', { name: 'Assistant reply' });
    expect(within(first).getByText('conflicted-file.txt')).toBeInTheDocument();
    expect(within(second).queryByText('conflicted-file.txt')).not.toBeInTheDocument();
    expect(
      within(screen.getByLabelText('History with unknown reply')).getByText('conflicted-file.txt'),
    ).toBeInTheDocument();
  });

  it('retains unresolved message claims alongside a proven membership without choosing another reply', () => {
    const thread = replyThread({
      messages: twoTurns(),
      artifacts: [
        replyArtifact('missing-message', 'missing-message.txt', {
          runId: 'run/one',
          messageId: 'unknown-message',
        }),
      ],
      runs: [replyRun('run/one', { artifactIds: ['missing-message'] })],
    });
    expect(replyFor(thread, 'run/one').artifacts.map((file) => file.id)).toEqual([
      'missing-message',
    ]);
    expect(replyFor(thread, 'run/two').artifacts).toHaveLength(0);
    expect(groupReplies(thread).unassociated.artifacts.map((file) => file.id)).toEqual([
      'missing-message',
    ]);
  });

  it('uses scalar and exact-message fallback only without memberships and retains unproven conflicts', () => {
    const thread = replyThread({
      messages: twoTurns(),
      artifacts: [
        replyArtifact('scalar', 'scalar.txt', { runId: 'run/one' }),
        replyArtifact('message', 'message.txt', { messageId: 'answer-two' }),
        replyArtifact('conflict', 'conflict.txt', { runId: 'run/one', messageId: 'answer-two' }),
        replyArtifact('unproven', 'unproven.txt', { runId: 'missing-run' }),
        replyArtifact('no-proof', 'no-proof.txt', { runId: null, messageId: null }),
      ],
      runs: [replyRun('run/one'), replyRun('run/two')],
    });
    expect(replyFor(thread, 'run/one').artifacts.map((file) => file.id)).toEqual(['scalar']);
    expect(replyFor(thread, 'run/two').artifacts.map((file) => file.id)).toEqual(['message']);
    expect(groupReplies(thread).unassociated.artifacts.map((file) => file.id)).toEqual([
      'conflict',
      'unproven',
      'no-proof',
    ]);
    render(<ConversationReplies thread={thread} />);
    const unknown = screen.getByLabelText('History with unknown reply');
    expect(within(unknown).getByText('conflict.txt')).toBeInTheDocument();
    expect(within(unknown).getByText('unproven.txt')).toBeInTheDocument();
    expect(within(unknown).getByText('no-proof.txt')).toBeInTheDocument();
  });
});

describe('typed runs without messages', () => {
  it('assigns a failed handoff its exact activity, error and membership files without inventing a message', () => {
    const thread = replyThread({
      runs: [
        replyRun('handoff/failed', {
          kind: 'handoff',
          status: 'failed',
          artifactIds: ['handoff-report'],
        }),
      ],
      activities: [
        replyActivity('handoff-tool', {
          runId: 'handoff/failed',
          summary: 'Handoff preparation failed',
          status: 'failed',
        }),
      ],
      events: [
        runEvent(
          1,
          'error',
          { code: 'handoff_failed', message: 'Handoff failed before producing assistant text' },
          'handoff/failed',
        ),
      ],
      artifacts: [
        replyArtifact('handoff-report', 'handoff-report.txt', { runId: null, messageId: null }),
      ],
    });
    const reply = replyFor(thread, 'handoff/failed');
    expect(reply.messages).toEqual([]);
    expect(reply.activity).toHaveLength(2);
    expect(reply.artifacts.map((file) => file.id)).toEqual(['handoff-report']);
    expect(groupReplies(thread).unassociated.activity).toHaveLength(0);
    expect(groupReplies(thread).unassociated.artifacts).toHaveLength(0);
    render(<ConversationReplies thread={thread} />);
    const article = screen.getByRole('article', { name: 'Assistant reply' });
    expect(article).toHaveAttribute('data-run-id', 'handoff/failed');
    expect(within(article).getByText('Handoff preparation failed')).toBeInTheDocument();
    expect(within(article).getByRole('alert', { name: 'Reply error' })).toHaveTextContent(
      'Handoff failed before producing assistant text',
    );
    expect(within(article).getByText('handoff-report.txt')).toBeInTheDocument();
    expect(screen.queryByLabelText('Final answer')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('History with unknown reply')).not.toBeInTheDocument();
  });

  it('inserts message-less runs chronologically around intact user/reply pairs despite queued users and late finals', () => {
    const timestamp = (minute: string) => `2026-09-22T10:${minute}:00.000Z`;
    const thread = replyThread({
      messages: [
        replyMessage('user-one', 'user', 'Current request', {
          runId: 'run/one',
          createdAt: timestamp('00'),
        }),
        replyMessage('user-two', 'user', 'Queued followup', {
          runId: 'run/two',
          createdAt: timestamp('10'),
        }),
        replyMessage('answer-one', 'assistant', 'Late current final', {
          runId: 'run/one',
          createdAt: timestamp('30'),
          phase: 'final',
          streamState: 'completed',
        }),
        replyMessage('answer-two', 'assistant', 'Later followup final', {
          runId: 'run/two',
          createdAt: timestamp('31'),
          phase: 'final',
          streamState: 'completed',
        }),
      ],
      runs: [
        replyRun('orphan-after', { createdAt: timestamp('40') }),
        replyRun('run/two', { createdAt: timestamp('10') }),
        replyRun('orphan-between', { kind: 'handoff', createdAt: timestamp('05') }),
        replyRun('run/one', { createdAt: timestamp('00') }),
        replyRun('orphan-before', { createdAt: '2026-09-22T09:59:00.000Z' }),
      ],
      activities: [
        replyActivity('before', { runId: 'orphan-before', summary: 'Before first request' }),
        replyActivity('between', {
          runId: 'orphan-between',
          summary: 'Between both request turns',
        }),
        replyActivity('after', { runId: 'orphan-after', summary: 'After both request turns' }),
      ],
    });
    const expected = [
      'orphan-before',
      'user-one',
      'run/one',
      'orphan-between',
      'user-two',
      'run/two',
      'orphan-after',
    ];
    expect(
      groupReplies(thread).items.map((item) =>
        item.kind === 'user' ? item.message.id : item.reply.runId,
      ),
    ).toEqual(expected);
    render(<ConversationReplies thread={thread} />);
    const articles = screen.getAllByRole('article');
    expect(articles).toHaveLength(7);
    expect(articles[0]).toHaveTextContent('Before first request');
    expect(articles[1]).toHaveTextContent('Current request');
    expect(articles[2]).toHaveTextContent('Late current final');
    expect(articles[3]).toHaveTextContent('Between both request turns');
    expect(articles[4]).toHaveTextContent('Queued followup');
    expect(articles[5]).toHaveTextContent('Later followup final');
    expect(articles[6]).toHaveTextContent('After both request turns');
  });
});
