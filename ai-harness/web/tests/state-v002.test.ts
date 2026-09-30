import { describe, expect, it } from 'vitest';
import { ACTIVITY_LIMIT, applyEvent, reconcileSnapshot } from '../src/state';
import { createdAt, event, snapshot } from './fixtures';

describe('v0.0.2 history preservation', () => {
  it('keeps known metadata when a legacy canonical message omits additive fields', () => {
    const snap = snapshot();
    snap.messages = [
      {
        id: 'message-1',
        role: 'assistant',
        content: 'Streaming',
        createdAt,
        runId: 'run-1',
        attachmentIds: ['upload-1'],
      },
    ];
    const thread = applyEvent(
      reconcileSnapshot(snap),
      event(1, 'message', {
        message: { id: 'message-1', role: 'assistant', content: 'Final text', createdAt },
      }),
    );
    expect(thread.messages).toEqual([
      {
        ...snap.messages[0],
        content: 'Final text',
      },
    ]);
  });

  it('uses the authoritative message envelope run rather than guessing from nearby turns', () => {
    const messageEvent = event(1, 'message', {
      message: { id: 'message-1', role: 'assistant', content: 'Reply', createdAt },
    });
    messageEvent.runId = 'run-1';
    const thread = applyEvent(reconcileSnapshot(snapshot()), messageEvent);
    expect(thread.messages[0].runId).toBe('run-1');
    const unassociated = applyEvent(
      thread,
      event(2, 'message', {
        message: { id: 'legacy', role: 'assistant', content: 'Old reply', createdAt },
      }),
    );
    expect(unassociated.messages[1].runId).toBeUndefined();
  });

  it('retains old activity history beyond the presentation page size on reload and streaming', () => {
    const snap = snapshot();
    snap.events = Array.from({ length: ACTIVITY_LIMIT + 5 }, (_, index) =>
      event(index + 1, 'progress', { kind: 'tool', label: `Activity ${index + 1}` }),
    );
    let thread = reconcileSnapshot(snap);
    expect(thread.activity).toHaveLength(ACTIVITY_LIMIT + 5);
    thread = applyEvent(
      thread,
      event(ACTIVITY_LIMIT + 6, 'progress', {
        kind: 'tool',
        label: 'Newest activity',
      }),
    );
    expect(thread.activity).toHaveLength(ACTIVITY_LIMIT + 6);
    expect(thread.activity[0].label).toBe('Activity 1');
  });
});

describe('snapshot metadata reconciliation', () => {
  it('recovers run IDs only from events for that exact message without replaying text', () => {
    const snap = snapshot();
    snap.messages = [
      { id: 'message-1', role: 'assistant', content: 'Canonical final', createdAt },
      { id: 'unknown', role: 'assistant', content: 'Unknown history', createdAt },
    ];
    const delta = event(1, 'assistant_delta', { messageId: 'message-1', text: 'Not appended' });
    delta.runId = 'run-1';
    snap.events = [delta];
    const thread = reconcileSnapshot(snap);
    expect(thread.messages[0]).toMatchObject({ content: 'Canonical final', runId: 'run-1' });
    expect(thread.messages[1].runId).toBeUndefined();
  });

  it('enriches an existing streamed message with its exact delta run ID', () => {
    const snap = snapshot();
    snap.messages = [{ id: 'm', role: 'assistant', content: 'First', createdAt }];
    const delta = event(1, 'assistant_delta', { messageId: 'm', text: ' second' });
    delta.runId = 'run-1';
    const thread = applyEvent(reconcileSnapshot(snap), delta);
    expect(thread.messages[0]).toMatchObject({ content: 'First second', runId: 'run-1' });
  });

  it('does not duplicate an activity when a snapshot contains repeated replay IDs', () => {
    const snap = snapshot();
    const progress = event(1, 'progress', { kind: 'tool', label: 'A tool call' });
    snap.events = [progress, progress];
    expect(reconcileSnapshot(snap, [progress]).activity).toHaveLength(1);
  });
});

const summary = (active: number | null = null) => ({
  known: active !== null,
  active,
  completed: active === null ? null : 0,
  failed: active === null ? null : 0,
  cancelled: active === null ? null : 0,
});
const run = (
  id: string,
  status: import('../src/types').RunStatus = 'running',
): import('../src/types').RunSnapshot => ({
  id,
  kind: 'message',
  status,
  createdAt,
  updatedAt: createdAt,
  artifactIds: [],
  subagents: summary(),
});
const activity = (
  overrides: Partial<import('../src/types').Activity> = {},
): import('../src/types').Activity => ({
  id: 'native-tool-1',
  runId: 'run-1',
  kind: 'tool',
  name: 'Shell',
  status: 'pending',
  updatedAt: createdAt,
  ...overrides,
});

describe('authoritative native lifecycle contract', () => {
  it('updates one stable tool lifecycle, preserving earlier details and explicit time bounds', () => {
    let thread = reconcileSnapshot(snapshot());
    thread = applyEvent(
      thread,
      event(1, 'activity', {
        activity: activity({
          command: 'printf "<script>inert</script>"',
          detail: 'Input detail',
          toolCallId: 'tool-call-1',
          startedAt: createdAt,
        }),
      }),
    );
    thread = applyEvent(
      thread,
      event(2, 'activity', {
        activity: activity({
          status: 'in_progress',
          updatedAt: '2026-09-22T12:00:01.000Z',
        }),
      }),
    );
    const completed = event(3, 'activity', {
      activity: activity({
        status: 'completed',
        summary: 'Command completed',
        updatedAt: '2026-09-22T12:00:02.000Z',
        finishedAt: '2026-09-22T12:00:02.000Z',
      }),
    });
    thread = applyEvent(thread, completed);
    thread = applyEvent(thread, completed);
    expect(thread.activity).toHaveLength(1);
    expect(thread.activity[0]).toMatchObject({
      id: 'native-tool-1',
      runId: 'run-1',
      status: 'completed',
      command: 'printf "<script>inert</script>"',
      detail: 'Input detail',
      toolCallId: 'tool-call-1',
      startedAt: createdAt,
      createdAt,
      finishedAt: '2026-09-22T12:00:02.000Z',
      label: 'Command completed',
      legacy: false,
    });
  });

  it('keeps identical opaque activity IDs separate across runs and preserves legacy unknown rows', () => {
    const snap = snapshot();
    snap.events = [event(1, 'progress', { kind: 'tool', label: 'Unknown old tool' })];
    snap.activities = [activity(), activity({ runId: 'run-2', status: 'completed' })];
    const thread = reconcileSnapshot(snap);
    expect(thread.activity).toHaveLength(3);
    expect(thread.activity[0]).toMatchObject({
      id: 'event:1',
      label: 'Unknown old tool',
      legacy: true,
    });
    expect(thread.activity[0].runId).toBeUndefined();
    expect(
      thread.activity.filter((item) => item.id === 'native-tool-1').map((item) => item.runId),
    ).toEqual(['run-1', 'run-2']);
  });

  it('hydrates lifecycle once on reload and prefers canonical completion over historic start', () => {
    const snap = snapshot();
    const start = event(1, 'activity', {
      activity: activity({ command: 'pwd', startedAt: createdAt }),
    });
    snap.events = [start, start];
    snap.activities = [activity({ status: 'completed', finishedAt: '2026-09-22T12:00:02.000Z' })];
    const thread = reconcileSnapshot(snap, [start]);
    expect(thread.activity).toHaveLength(1);
    expect(thread.activity[0]).toMatchObject({
      status: 'completed',
      command: 'pwd',
      startedAt: createdAt,
    });
  });

  it('accepts only typed subagent summaries and preserves unknown historical counts', () => {
    const snap = snapshot();
    snap.runs = [run('run-1')];
    let thread = reconcileSnapshot(snap);
    thread = applyEvent(
      thread,
      event(1, 'progress', {
        kind: 'subagent',
        label: 'Started 99 agents',
        taskId: 'claimed-child',
      }),
    );
    thread = applyEvent(
      thread,
      event(2, 'message', {
        message: {
          id: 'prose',
          role: 'assistant',
          content: 'I have 500 active agents',
          createdAt,
        },
      }),
    );
    thread = applyEvent(
      thread,
      event(3, 'activity', {
        activity: activity({
          kind: 'subagent',
          childSessionId: 'child-1',
          status: 'in_progress',
        }),
      }),
    );
    expect(thread.runs[0].subagents).toEqual(summary());
    expect(thread.subagentsByRun['run-1'].active).toBeNull();
    thread = applyEvent(thread, event(4, 'subagents', { runId: 'run-1', summary: summary(2) }));
    expect(thread.runs[0].subagents.active).toBe(2);
    expect(thread.subagentsByRun['run-1'].active).toBe(2);
    thread = applyEvent(thread, event(5, 'subagents', { runId: 'run-1', summary: summary(0) }));
    expect(thread.runs[0].subagents.active).toBe(0);
    expect(thread.runs[0].status).toBe('running');
    thread = applyEvent(thread, event(6, 'subagents', { runId: 'run-1', summary: summary() }));
    expect(thread.runs[0].subagents).toEqual(summary());
  });

  it('retains a typed count received before run metadata without fabricating a run', () => {
    const thread = applyEvent(
      reconcileSnapshot(snapshot()),
      event(1, 'subagents', {
        runId: 'not-yet-snapshotted',
        summary: summary(3),
      }),
    );
    expect(thread.runs).toEqual([]);
    expect(thread.subagentsByRun['not-yet-snapshotted'].active).toBe(3);
  });

  it('reconciles multiple queued/current/terminal runs without clearing unrelated turns', () => {
    const snap = snapshot();
    snap.runs = [run('run-1'), run('run-2', 'queued'), run('run-3', 'queued')];
    let thread = reconcileSnapshot(snap);
    thread = applyEvent(thread, event(1, 'run', { run: run('run-1', 'completed') }));
    thread = applyEvent(thread, event(2, 'run', { run: run('run-2', 'running') }));
    expect(thread.runs.map((item) => [item.id, item.status])).toEqual([
      ['run-1', 'completed'],
      ['run-2', 'running'],
      ['run-3', 'queued'],
    ]);
    thread = applyEvent(thread, event(3, 'run', { run: run('run-2', 'cancelled') }));
    thread = applyEvent(thread, event(4, 'run', { run: run('run-3', 'cancelled') }));
    expect(thread.runs.map((item) => item.status)).toEqual(['completed', 'cancelled', 'cancelled']);
  });

  it('retains generic compatibility progress alongside authoritative lifecycle without merging identities', () => {
    const snap = snapshot();
    const legacy = event(1, 'progress', { kind: 'tool', label: 'Shell started' });
    legacy.runId = 'run-1';
    snap.events = [legacy, event(2, 'activity', { activity: activity() })];
    const thread = reconcileSnapshot(snap, snap.events);
    expect(thread.activity).toHaveLength(2);
    expect(thread.activity.map((item) => [item.runId, item.legacy])).toEqual([
      ['run-1', true],
      ['run-1', false],
    ]);
  });
});

describe('phase, files, and context contract', () => {
  it('preserves native segmented progress and final text through streaming, classification, and reload', () => {
    const intermediateDelta = event(1, 'assistant_delta', {
      messageId: 'progress-1',
      text: 'Checking the files.',
      phase: 'unclassified',
      nativeMessageId: 'native-1',
      nativeTurnId: 'turn-1',
    });
    intermediateDelta.runId = 'run-1';
    let thread = applyEvent(reconcileSnapshot(snapshot()), intermediateDelta);
    expect(thread.messages[0]).toMatchObject({ phase: 'unclassified', streamState: 'streaming' });
    const intermediate = event(2, 'message', {
      message: {
        ...thread.messages[0],
        phase: 'intermediate',
        streamState: 'completed',
      },
    });
    thread = applyEvent(thread, intermediate);
    const finalDelta = event(3, 'assistant_delta', {
      messageId: 'final-1',
      text: 'The result.',
      phase: 'unclassified',
      nativeMessageId: 'native-2',
      nativeTurnId: 'turn-1',
    });
    finalDelta.runId = 'run-1';
    thread = applyEvent(thread, finalDelta);
    const final = event(4, 'message', {
      message: {
        ...thread.messages[1],
        phase: 'final',
        streamState: 'completed',
      },
    });
    thread = applyEvent(thread, final);
    const snap = {
      ...snapshot(),
      messages: thread.messages,
      events: [intermediateDelta, intermediate, finalDelta, final],
    };
    const reloaded = reconcileSnapshot(snap, snap.events);
    expect(reloaded.messages).toEqual(thread.messages);
    expect(
      reloaded.messages.map((item) => [item.content, item.phase, item.nativeMessageId]),
    ).toEqual([
      ['Checking the files.', 'intermediate', 'native-1'],
      ['The result.', 'final', 'native-2'],
    ]);
  });

  it('does not infer phases or discard incomplete and legacy responses', () => {
    const snap = snapshot();
    snap.messages = [
      { id: 'legacy', role: 'assistant', content: '# Final answer\nThinking deeply', createdAt },
    ];
    let thread = reconcileSnapshot(snap);
    expect(thread.messages[0].phase).toBeUndefined();
    thread = applyEvent(
      thread,
      event(1, 'assistant_delta', {
        messageId: 'partial',
        text: 'Partial output',
        phase: 'unclassified',
      }),
    );
    thread = applyEvent(thread, event(2, 'state', { status: 'interrupted' }));
    expect(thread.messages.map((item) => item.content)).toEqual([
      '# Final answer\nThinking deeply',
      'Partial output',
    ]);
    expect(thread.messages[1].phase).toBe('unclassified');
  });

  it('recovers artifact turn association only from its exact event and retains attachment metadata', () => {
    const snap = snapshot();
    const file = {
      id: 'file-1',
      name: 'chart.svg',
      mimeType: 'image/svg+xml',
      size: 42,
      downloadUrl: '/api/artifacts/file-1/download',
    };
    snap.artifacts = [
      { ...file, runId: null },
      { ...file, id: 'unknown', runId: null },
    ];
    const fileEvent = event(1, 'artifact', {
      artifact: { ...file, previewUrl: '/api/files/file-1/preview' },
    });
    fileEvent.runId = 'run-1';
    snap.events = [fileEvent];
    snap.attachments = [
      {
        id: 'upload-1',
        name: '<script>.txt',
        mimeType: 'text/plain',
        size: 3,
        downloadUrl: '/api/attachments/upload-1/download',
      },
    ];
    snap.messages = [
      {
        id: 'user-1',
        role: 'user',
        content: 'Use this',
        attachmentIds: ['upload-1', 'legacy-missing'],
        createdAt,
        runId: 'run-1',
      },
    ];
    const thread = reconcileSnapshot(snap);
    expect(thread.artifacts[0]).toMatchObject({
      runId: 'run-1',
      previewUrl: '/api/files/file-1/preview',
    });
    expect(thread.artifacts[1].runId).toBeNull();
    expect(thread.messages[0].attachmentIds).toEqual(['upload-1', 'legacy-missing']);
    expect(thread.attachments).toEqual(snap.attachments);
  });

  it('preserves authoritative zero fresh context and leaves unknown old context untouched', () => {
    const fresh = snapshot();
    fresh.session.context = {
      used: 0,
      limit: 480000,
      estimated: false,
      stale: false,
      updatedAt: createdAt,
      source: 'empty',
    };
    expect(reconcileSnapshot(fresh).session.context).toEqual(fresh.session.context);
    const old = snapshot();
    old.session.status = 'interrupted';
    old.session.context = {
      used: null,
      limit: 480000,
      estimated: false,
      stale: true,
      updatedAt: createdAt,
    };
    old.messages = [{ id: 'old', role: 'assistant', content: 'Restored', createdAt }];
    expect(reconcileSnapshot(old).session.context).toEqual(old.session.context);
    expect(reconcileSnapshot(snapshot()).session.context).toBeUndefined();
  });
});

describe('queued followup interleaving', () => {
  it('keeps late first-run final, activity, and artifact identities after the next user message', () => {
    let thread = reconcileSnapshot(snapshot());
    thread = applyEvent(
      thread,
      event(1, 'message', {
        message: {
          id: 'user-1',
          role: 'user',
          content: 'First task',
          createdAt,
          runId: 'run-1',
        },
      }),
    );
    thread = applyEvent(thread, event(2, 'run', { run: run('run-1') }));
    thread = applyEvent(
      thread,
      event(3, 'message', {
        message: {
          id: 'user-2',
          role: 'user',
          content: 'Next task',
          createdAt,
          runId: 'run-2',
        },
      }),
    );
    thread = applyEvent(thread, event(4, 'run', { run: run('run-2', 'queued') }));
    thread = applyEvent(
      thread,
      event(5, 'message', {
        message: {
          id: 'final-1',
          role: 'assistant',
          content: 'First result',
          createdAt,
          runId: 'run-1',
          phase: 'final',
          streamState: 'completed',
        },
      }),
    );
    thread = applyEvent(
      thread,
      event(6, 'activity', { activity: activity({ status: 'completed' }) }),
    );
    const lateFile = event(7, 'artifact', {
      artifact: {
        id: 'artifact-1',
        name: 'first.txt',
        size: 10,
        mimeType: 'text/plain',
        downloadUrl: '/api/artifacts/artifact-1/download',
      },
    });
    lateFile.runId = 'run-1';
    thread = applyEvent(thread, lateFile);
    expect(thread.messages.map((message) => [message.id, message.runId])).toEqual([
      ['user-1', 'run-1'],
      ['user-2', 'run-2'],
      ['final-1', 'run-1'],
    ]);
    expect(thread.activity[0].runId).toBe('run-1');
    expect(thread.artifacts[0].runId).toBe('run-1');
    expect(thread.runs.find((item) => item.id === 'run-2')?.status).toBe('queued');
  });
});

describe('opaque lifecycle identities and snapshot freshness', () => {
  it('treats prototype-like run IDs as ordinary keys across snapshot and stream updates', () => {
    const snap = snapshot();
    snap.runs = [
      { ...run('__proto__'), subagents: summary(1) },
      { ...run('toString'), subagents: summary(2) },
    ];
    snap.events = [event(1, 'subagents', { runId: 'constructor', summary: summary(3) })];
    let thread = reconcileSnapshot(snap);
    expect(Object.getPrototypeOf(thread.subagentsByRun)).toBeNull();
    expect(Object.hasOwn(thread.subagentsByRun, '__proto__')).toBe(true);
    expect(thread.subagentsByRun.__proto__.active).toBe(1);
    expect(thread.subagentsByRun['toString' as string].active).toBe(2);
    expect(thread.subagentsByRun['constructor' as string].active).toBe(3);
    expect(thread.subagentsByRun.valueOf).toBeUndefined();
    thread = applyEvent(thread, event(2, 'subagents', { runId: '__proto__', summary: summary(0) }));
    thread = applyEvent(
      thread,
      event(3, 'run', { run: { ...run('toString'), subagents: summary(4) } }),
    );
    expect(Object.getPrototypeOf(thread.subagentsByRun)).toBeNull();
    expect(thread.subagentsByRun.__proto__.active).toBe(0);
    expect(thread.subagentsByRun['toString' as string].active).toBe(4);
    expect(thread.subagentsByRun['constructor' as string].active).toBe(3);
    expect(Object.keys(thread.subagentsByRun).sort()).toEqual([
      '__proto__',
      'constructor',
      'toString',
    ]);
  });

  it('keeps newer activity completion when an older snapshot projection arrives after event history', () => {
    const snap = snapshot();
    snap.events = [
      event(1, 'activity', {
        activity: activity({
          status: 'completed',
          summary: 'Finished',
          updatedAt: '2026-09-22T12:00:02.000Z',
          finishedAt: '2026-09-22T12:00:02.000Z',
        }),
      }),
    ];
    snap.activities = [activity({ status: 'pending', command: 'pwd', startedAt: createdAt })];
    const thread = reconcileSnapshot(snap);
    expect(thread.activity).toHaveLength(1);
    expect(thread.activity[0]).toMatchObject({
      status: 'completed',
      label: 'Finished',
      updatedAt: '2026-09-22T12:00:02.000Z',
      finishedAt: '2026-09-22T12:00:02.000Z',
      command: 'pwd',
      startedAt: createdAt,
    });
  });

  it('allows a newer authoritative lifecycle state regardless of status ordering', () => {
    const snap = snapshot();
    snap.activities = [activity({ status: 'completed' })];
    const thread = applyEvent(
      reconcileSnapshot(snap),
      event(1, 'activity', {
        activity: activity({
          status: 'in_progress',
          updatedAt: '2026-09-22T12:00:02.000Z',
        }),
      }),
    );
    expect(thread.activity[0].status).toBe('in_progress');
  });
});
