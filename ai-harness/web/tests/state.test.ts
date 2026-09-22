import { describe, expect, it } from 'vitest';
import { applyEvent, reconcileSnapshot, DETAIL_LIMIT } from '../src/state';
import { createdAt, event, snapshot } from './fixtures';
describe('snapshot and stream reconciliation', () => {
  it('deduplicates replay and final message transitions, ignoring wrong sessions', () => {
    let thread = reconcileSnapshot(snapshot());
    const delta = event(1, 'assistant_delta', { messageId: 'm', text: 'Hello' });
    thread = applyEvent(thread, delta);
    thread = applyEvent(thread, delta);
    thread = applyEvent(
      thread,
      event(2, 'message', {
        message: { id: 'm', role: 'assistant', content: 'Hello world', createdAt },
      }),
    );
    thread = applyEvent(thread, event(3, 'assistant_delta', { messageId: 'm', text: '!' }));
    thread = applyEvent(
      thread,
      event(4, 'assistant_delta', { messageId: 'm', text: ' WRONG' }, 'other'),
    );
    expect(thread.messages.map((m) => m.content)).toEqual(['Hello world!']);
  });
  it('uses snapshot cutoff and replays only newer buffered deltas, without truncating', () => {
    const snap = snapshot();
    snap.messages = [{ id: 'm', role: 'assistant', content: 'Alpha', createdAt }];
    snap.events = [event(1, 'assistant_delta', { messageId: 'm', text: 'Alpha' })];
    const pending = [
      snap.events[0],
      event(2, 'assistant_delta', { messageId: 'm', text: ' beta' }),
    ];
    expect(reconcileSnapshot(snap, pending).messages[0].content).toBe('Alpha beta');
    const final = {
      ...snap,
      messages: [{ ...snap.messages[0], content: 'Alpha beta' }],
      events: pending,
    };
    expect(reconcileSnapshot(final, pending).messages[0].content).toBe('Alpha beta');
  });
  it('preserves original history and actual errors; bounds activity detail only', () => {
    const snap = snapshot();
    snap.messages = [{ id: 'old', role: 'user', content: 'Original history', createdAt }];
    snap.events = [event(1, 'error', { code: 'engine_failed', message: 'Compression failed' })];
    let thread = reconcileSnapshot(snap);
    thread = applyEvent(
      thread,
      event(2, 'progress', {
        kind: 'compression',
        label: 'Compressing',
        detail: '<script>' + 'x'.repeat(10_000),
      }),
    );
    expect(thread.messages[0].content).toBe('Original history');
    expect(thread.error).toBe('Compression failed');
    expect(thread.activity[1].detail).toHaveLength(DETAIL_LIMIT);
  });
});
