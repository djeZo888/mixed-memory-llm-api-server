// Explicit contract-v1 fixture only. Never imported by src/ or the shipped app.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
const port = 4193;
const at = '2026-09-22T10:24:00.000Z';
let sessions;
let histories;
let calls;
let counter;
let vision;
const connections = new Map();
function session(id, title) {
  return { id, title, createdAt: at, updatedAt: at, status: 'idle' };
}
function reset() {
  connections.forEach((set) => set.forEach((response) => response.end()));
  connections.clear();
  sessions = [
    session('fixture/chat-a', 'Investigate a streaming pipeline'),
    session('fixture/chat-b', 'Parser edge cases'),
    session('fixture/chat-c', 'Notes on context accounting'),
  ];
  histories = new Map(sessions.map((s) => [s.id, { messages: [], events: [], artifacts: [] }]));
  calls = [];
  counter = 0;
  vision = false;
  sessions[0].context = {
    used: 123456,
    limit: 480000,
    estimated: true,
    stale: false,
    updatedAt: at,
    source: 'fixture estimator',
  };
  const initial = histories.get(sessions[0].id);
  initial.messages = [
    {
      id: 'user/initial',
      role: 'user',
      content: 'Review the streaming pipeline. How should we recover after a connection drops?',
      createdAt: at,
    },
    {
      id: 'assistant/initial',
      role: 'assistant',
      content:
        'Use the persisted conversation as the recovery point, then replay only the events that came after it.\n\n### Three things to keep consistent\n\n1. **A per-session event cursor.** Ignore IDs you have already applied.\n2. **A coherent snapshot.** Messages and the event cutoff must describe the same point in time.\n3. **A subscription that can reconnect.** Closing the page leaves the server task running.\n\n```typescript\nconst unseen = events.filter(event => event.id > cursor);\nfor (const event of unseen) apply(event);\n```\n\nThe original conversation stays available after compression. I captured the review notes in the file below.',
      createdAt: at,
    },
  ];
  emit(sessions[0].id, 'progress', {
    kind: 'shell',
    label: 'Reviewed the event reconciliation checks',
    detail: 'Fixture tool output: 3 checks passed.\n<script>not executable</script>',
  });
  initial.artifacts.push({
    id: 'fixture/review notes',
    name: 'streaming-review.md',
    mimeType: 'text/markdown',
    size: 2048,
    downloadUrl: 'javascript:alert(1)',
  });
}
function emit(id, type, data, named = true) {
  const history = histories.get(id);
  if (!history) return;
  const event = {
    id: (history.events.at(-1)?.id ?? 0) + 1,
    type,
    sessionId: id,
    createdAt: at,
    data,
  };
  history.events.push(event);
  if (type === 'state') {
    const s = sessions.find((s) => s.id === id);
    if (s) s.status = data.status;
  }
  if (type === 'context') sessions.find((s) => s.id === id).context = data.context;
  if (type === 'message') {
    const index = history.messages.findIndex((m) => m.id === data.message.id);
    if (index < 0) history.messages.push(data.message);
    else history.messages[index] = data.message;
  }
  if (type === 'assistant_delta') {
    let message = history.messages.find((m) => m.id === data.messageId);
    if (!message) {
      message = { id: data.messageId, role: 'assistant', content: '', createdAt: at };
      history.messages.push(message);
    }
    message.content += data.text;
  }
  for (const response of connections.get(id) ?? []) response.write(frame(event, named));
  return event;
}
const frame = (event, named = true) =>
  `id: ${event.id}\n${named ? `event: ${event.type}\n` : ''}data: ${JSON.stringify(event)}\n\n`;
const json = (response, status, body) => {
  response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  response.end(JSON.stringify(body));
};
reset();
const server = http.createServer(async (request, response) => {
  try {
    const url = new URL(request.url, `http://127.0.0.1:${port}`);
    let body = '';
    for await (const chunk of request) body += chunk;
    const data = () => JSON.parse(body || '{}');
    if (url.pathname === '/__fixture/reset') {
      reset();
      return json(response, 200, { fixture: true });
    }
    if (url.pathname === '/__fixture/calls') return json(response, 200, { calls });
    if (url.pathname === '/__fixture/vision') {
      vision = data().enabled;
      return json(response, 200, { vision });
    }
    if (url.pathname === '/__fixture/event') {
      const input = data();
      const event = emit(input.sessionId, input.type, input.data, input.named !== false);
      return json(response, 200, { event });
    }
    if (url.pathname === '/__fixture/replay') {
      const input = data();
      const event = histories.get(input.sessionId).events.find((e) => e.id === input.id);
      for (const stream of connections.get(input.sessionId) ?? []) stream.write(frame(event));
      return json(response, 200, { replayed: true });
    }
    if (url.pathname === '/__fixture/disconnect') {
      const id = data().sessionId;
      for (const stream of connections.get(id) ?? []) stream.end();
      return json(response, 200, { disconnected: true });
    }
    if (url.pathname === '/api/health')
      return json(response, 200, { version: '0.0.1', status: 'ok', visionAvailable: vision });
    if (url.pathname === '/api/sessions' && request.method === 'GET')
      return json(response, 200, { sessions });
    if (url.pathname === '/api/sessions' && request.method === 'POST') {
      const s = session(`fixture/new-${++counter}`, 'New fixture conversation');
      sessions.unshift(s);
      histories.set(s.id, { messages: [], events: [], artifacts: [] });
      calls.push({ action: 'create', id: s.id });
      return json(response, 201, { session: s });
    }
    const artifact = /^\/api\/artifacts\/([^/]+)\/download$/.exec(url.pathname);
    if (artifact) {
      calls.push({ action: 'download', id: decodeURIComponent(artifact[1]) });
      response.writeHead(200, {
        'Content-Type': 'text/markdown',
        'Content-Disposition': 'attachment; filename="streaming-review.md"',
      });
      return response.end('# Fixture review\nNot live inference.\n');
    }
    const match =
      /^\/api\/sessions\/([^/]+)(?:\/(messages|events|cancel|handoff|uploads|artifacts))?$/.exec(
        url.pathname,
      );
    if (match) {
      const id = decodeURIComponent(match[1]);
      const operation = match[2];
      const s = sessions.find((s) => s.id === id);
      const history = histories.get(id);
      if (!s || !history)
        return json(response, 404, {
          error: { code: 'not_found', message: 'This fixture session was deleted.' },
        });
      if (operation === 'events') {
        response.writeHead(200, {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          Connection: 'keep-alive',
        });
        response.write('retry: 100\n: fixture stream\n\n');
        const after = Math.max(
          Number(url.searchParams.get('after') ?? 0),
          Number(request.headers['last-event-id'] ?? 0),
        );
        calls.push({ action: 'subscribe', id, after });
        for (const event of history.events.filter((e) => e.id > after))
          response.write(frame(event, event.id % 2 === 0));
        const set = connections.get(id) ?? new Set();
        set.add(response);
        connections.set(id, set);
        response.on('close', () => set.delete(response));
        return;
      }
      if (!operation && request.method === 'DELETE') {
        calls.push({ action: 'delete', id });
        sessions = sessions.filter((s) => s.id !== id);
        return json(response, 202, { status: 'deleting' });
      }
      if (!operation) {
        calls.push({ action: 'snapshot', id });
        return json(response, 200, { session: s, ...history });
      }
      if (operation === 'messages') {
        const input = data();
        calls.push({ action: 'send', id, ...input });
        const runId = `fixture/run-${++counter}`;
        emit(id, 'message', {
          message: {
            id: `user/${counter}`,
            role: 'user',
            content: input.text,
            createdAt: at,
            attachmentIds: input.attachmentIds,
            runId,
          },
        });
        emit(id, 'state', { status: 'running' });
        emit(id, 'progress', {
          kind: 'shell',
          label: 'Fixture task started',
          detail: 'This is a contract fixture, not live inference.',
        });
        emit(
          id,
          'assistant_delta',
          { messageId: `assistant/${counter}`, text: 'Checking the fixture pipeline' },
          false,
        );
        return json(response, 202, { runId });
      }
      if (operation === 'cancel') {
        calls.push({ action: 'cancel', id });
        emit(id, 'state', { status: 'cancelling' });
        json(response, 202, { status: 'cancelling' });
        setTimeout(() => {
          emit(id, 'state', { status: 'interrupted' });
          emit(id, 'done', { runId: `fixture/run-${counter}` });
        }, 100);
        return;
      }
      if (operation === 'handoff') {
        calls.push({ action: 'handoff', id });
        const target = session(`fixture/handoff-${++counter}`, 'Continued: streaming pipeline');
        sessions.unshift(target);
        histories.set(target.id, {
          messages: [
            {
              id: 'handoff-summary',
              role: 'assistant',
              content: 'Fixture handoff summary. The original conversation is retained.',
              createdAt: at,
            },
          ],
          events: [],
          artifacts: [],
        });
        json(response, 202, { runId: `fixture/handoff-run-${counter}` });
        setTimeout(() => emit(id, 'handoff', { newSessionId: target.id }), 80);
        return;
      }
      if (operation === 'uploads') {
        const name = /filename="([^"]+)"/.exec(body)?.[1] ?? 'file.txt';
        calls.push({ action: 'upload', id, field: /name="file"/.test(body), name });
        return json(response, 201, {
          attachment: {
            id: `fixture/attachment-${++counter}`,
            name,
            mimeType: 'text/plain',
            size: body.length,
          },
        });
      }
      if (operation === 'artifacts') return json(response, 200, { artifacts: history.artifacts });
    }
    const path = url.pathname === '/' ? 'index.html' : url.pathname.slice(1);
    const root = resolve('dist');
    const file = resolve(root, path);
    if (!file.startsWith(root + '/'))
      return json(response, 403, { error: { code: 'forbidden', message: 'Forbidden' } });
    const content = await readFile(file);
    response.writeHead(200, {
      'Content-Type':
        { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css' }[
          extname(file)
        ] ?? 'application/octet-stream',
    });
    response.end(content);
  } catch {
    json(response, 500, { error: { code: 'fixture_error', message: 'Fixture request failed' } });
  }
});
server.listen(port, '127.0.0.1', () => console.log(`FIXTURE ONLY http://127.0.0.1:${port}`));
