// Explicit contract-v1 fixture only. Never imported by src/ or the shipped app.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import { deflateSync } from 'node:zlib';
const port = 4193;
const at = '2026-09-22T10:24:00.000Z';
const initialRunId = 'fixture/initial-run';
const svg =
  '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="200" viewBox="0 0 600 200"><rect width="600" height="200" rx="14" fill="#eef1e9"/><g fill="#425a4b" font-family="sans-serif" font-size="20" text-anchor="middle"><rect x="30" y="68" width="150" height="64" rx="9" fill="#dbe3d5"/><rect x="225" y="68" width="150" height="64" rx="9" fill="#dbe3d5"/><rect x="420" y="68" width="150" height="64" rx="9" fill="#dbe3d5"/><text x="105" y="108">Snapshot</text><text x="300" y="108">Replay</text><text x="495" y="108">Resume</text><text x="201" y="108">→</text><text x="397" y="108">→</text><text x="300" y="36" font-size="15">FIXTURE — NOT LIVE INFERENCE</text></g></svg>';
// A solid opaque 1920x1080 PNG is only a browser download/preview specimen.
// No image model, inference service or user image is involved.
function pngChunk(type, data) {
  const content = Buffer.concat([Buffer.from(type), data]);
  let crc = 0xffffffff;
  for (const byte of content) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  const length = Buffer.alloc(4),
    checksum = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  checksum.writeUInt32BE((crc ^ 0xffffffff) >>> 0);
  return Buffer.concat([length, content, checksum]);
}
const pngHeader = Buffer.alloc(13);
pngHeader.writeUInt32BE(1920, 0);
pngHeader.writeUInt32BE(1080, 4);
pngHeader[8] = 8;
pngHeader[9] = 2;
const pngRows = Buffer.alloc((1920 * 3 + 1) * 1080, 225);
for (let row = 0; row < 1080; row++) pngRows[row * (1920 * 3 + 1)] = 0;
const imagePng = Buffer.concat([
  Buffer.from('89504e470d0a1a0a', 'hex'),
  pngChunk('IHDR', pngHeader),
  pngChunk('IDAT', deflateSync(pngRows)),
  pngChunk('IEND', Buffer.alloc(0)),
]);
// Distinct procedural raster specimens make loaded inline images obvious in QA.
// Colored bands and a diagonal white motif are fixture bytes, never model output.
const h004Images = [
  [
    [35, 82, 116],
    [58, 148, 160],
    [219, 232, 167],
  ],
  [
    [184, 74, 55],
    [231, 168, 65],
    [64, 57, 101],
  ],
].map((colors) => {
  const rows = Buffer.alloc((1920 * 3 + 1) * 1080);
  for (let y = 0; y < 1080; y++) {
    for (let x = 0; x < 1920; x++) {
      const color = Math.abs(x - y * 1.7) < 50 ? [250, 250, 245] : colors[Math.floor(x / 640)];
      const offset = y * (1920 * 3 + 1) + x * 3 + 1;
      rows[offset] = color[0];
      rows[offset + 1] = color[1];
      rows[offset + 2] = color[2];
    }
  }
  return Buffer.concat([
    Buffer.from('89504e470d0a1a0a', 'hex'),
    pngChunk('IHDR', pngHeader),
    pngChunk('IDAT', deflateSync(rows)),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
});
const imageBody = (file) =>
  file?.id.startsWith('h004-file-') ? h004Images[Number(file.id.split('-').at(-1)) % 2] : imagePng;
const summary = (active = 0) => ({
  known: true,
  active,
  completed: 1,
  failed: 0,
  cancelled: 0,
  updatedAt: at,
});
const freshHistory = () => ({
  messages: [],
  events: [],
  artifacts: [],
  activities: [],
  runs: [],
  attachments: [],
  imageJobs: [],
});
const environment = {
  timeZone: 'Europe/Ljubljana',
  location: { city: 'Ljubljana', country: 'Slovenia' },
  now: at,
};
let sessions;
let histories;
let calls;
let counter;
let vision;
let imageDecisions;
let imageCapabilities;
let approvalTokens;
let approvalFailures;
let approvalCounter;
let imageGetOverrides;
let omitImageEvents;
const connections = new Map();
function session(id, title) {
  return {
    id,
    title,
    createdAt: at,
    updatedAt: at,
    status: 'idle',
    context: {
      used: 0,
      limit: 480000,
      estimated: true,
      stale: false,
      updatedAt: at,
      source: 'empty',
    },
  };
}
function reset() {
  connections.forEach((set) => set.forEach((response) => response.end()));
  connections.clear();
  sessions = [
    session('fixture/chat-a', 'Investigate a streaming pipeline'),
    session('fixture/chat-b', 'Parser edge cases'),
    session('fixture/chat-c', 'Notes on context accounting'),
  ];
  histories = new Map(sessions.map((s) => [s.id, freshHistory()]));
  calls = [];
  counter = 0;
  vision = false;
  imageDecisions = new Map();
  approvalTokens = new Map();
  approvalFailures = new Map();
  approvalCounter = 0;
  imageGetOverrides = new Map();
  omitImageEvents = new Set();
  imageCapabilities = {
    ready: true,
    admitting: true,
    busy: false,
    state: 'ready',
    model: 'Qwen-Image-2.1',
    runtime_revision: 'fixture-runtime',
    runtime_image_digest: `sha256:${'b'.repeat(64)}`,
    model_id: 'Qwen/Qwen-Image-2.1',
    model_revision: 'fixture-model',
    profiles: [
      {
        operation: 'generation',
        size: '1920x1080',
        references: 0,
        transparent: false,
        evidence_sha256: 'a'.repeat(64),
        native_size: '1920x1088',
        crop_bottom: 8,
      },
      {
        operation: 'edit',
        size: '1024x1024',
        references: 1,
        transparent: false,
        evidence_sha256: 'b'.repeat(64),
        native_size: '1024x1024',
        crop_bottom: 0,
      },
      {
        operation: 'edit',
        size: '1920x1080',
        references: 1,
        transparent: false,
        evidence_sha256: 'c'.repeat(64),
        native_size: '1920x1088',
        crop_bottom: 8,
      },
    ],
    limits: { n: 1 },
    defaults: { size: '1024x1024' },
    masks: false,
    response_format: 'b64_json',
    output_format: 'png',
  };
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
      runId: initialRunId,
      attachmentIds: ['fixture/initial-upload'],
    },
    {
      id: 'assistant/progress-initial',
      role: 'assistant',
      phase: 'intermediate',
      streamState: 'completed',
      content: 'I’m checking the persisted event cursor and replay behavior.',
      createdAt: at,
      runId: initialRunId,
    },
    {
      id: 'assistant/initial',
      role: 'assistant',
      content:
        'Use the persisted conversation as the recovery point, then replay only the events that came after it.\n\n### Three things to keep consistent\n\n1. **A per-session event cursor.** Ignore IDs you have already applied.\n2. **A coherent snapshot.** Messages and the event cutoff must describe the same point in time.\n3. **A subscription that can reconnect.** Closing the page leaves the server task running.\n\n```typescript\nconst unseen = events.filter(event => event.id > cursor);\nfor (const event of unseen) apply(event);\n```\n\nThe original conversation stays available after compression. I captured the review notes in the file below.',
      createdAt: at,
      runId: initialRunId,
      phase: 'final',
      streamState: 'completed',
    },
  ];
  initial.attachments.push({
    id: 'fixture/initial-upload',
    name: 'sample-log.txt',
    mimeType: 'text/plain',
    size: 64,
    downloadUrl: '/api/attachments/fixture%2Finitial-upload/download',
  });
  emit(
    sessions[0].id,
    'activity',
    {
      activity: {
        id: 'tool/review',
        runId: initialRunId,
        kind: 'tool',
        name: 'shell',
        status: 'completed',
        summary: 'Reviewed the event reconciliation checks',
        command: 'npm test -- reconciliation',
        url: 'https://example.com/streaming',
        detail: 'Fixture tool output: 3 checks passed.\n<script>not executable</script>',
        startedAt: at,
        updatedAt: '2026-09-22T10:24:02.400Z',
        finishedAt: '2026-09-22T10:24:02.400Z',
      },
    },
    true,
    initialRunId,
  );
  initial.artifacts.push({
    id: 'fixture/review notes',
    name: 'streaming-review.md',
    mimeType: 'text/markdown',
    size: 2048,
    downloadUrl: 'javascript:alert(1)',
    runId: initialRunId,
    messageId: 'assistant/initial',
  });
  initial.artifacts.push({
    id: 'fixture/pipeline-svg',
    name: 'pipeline.svg',
    mimeType: 'image/svg+xml',
    size: svg.length,
    downloadUrl: '/api/artifacts/fixture%2Fpipeline-svg/download',
    previewUrl: '/api/files/fixture%2Fpipeline-svg/preview',
    runId: initialRunId,
    messageId: 'assistant/initial',
  });
  emit(
    sessions[0].id,
    'run',
    {
      run: {
        id: initialRunId,
        kind: 'message',
        status: 'completed',
        createdAt: at,
        updatedAt: at,
        finalMessageId: 'assistant/initial',
        artifactIds: initial.artifacts.map((file) => file.id),
        zipUrl: '/api/sessions/fixture%2Fchat-a/runs/fixture%2Finitial-run/artifacts.zip',
        subagents: summary(),
      },
    },
    true,
    initialRunId,
  );
}
function emit(id, type, data, named = true, runId) {
  const history = histories.get(id);
  if (!history) return;
  const event = {
    id: (history.events.at(-1)?.id ?? 0) + 1,
    type,
    sessionId: id,
    createdAt: at,
    data,
    ...(runId ? { runId } : {}),
  };
  history.events.push(event);
  if (type === 'state') {
    const s = sessions.find((s) => s.id === id);
    if (s) s.status = data.status;
  }
  if (type === 'context') sessions.find((s) => s.id === id).context = data.context;
  if (type === 'run') {
    const index = history.runs.findIndex((run) => run.id === data.run.id);
    if (index < 0) history.runs.push(data.run);
    else history.runs[index] = { ...history.runs[index], ...data.run };
  }
  if (type === 'activity') {
    const index = history.activities.findIndex(
      (item) => item.id === data.activity.id && item.runId === data.activity.runId,
    );
    if (index < 0) history.activities.push(data.activity);
    else history.activities[index] = { ...history.activities[index], ...data.activity };
  }
  if (type === 'subagents') {
    const index = history.runs.findIndex((run) => run.id === data.runId);
    if (index >= 0) history.runs[index] = { ...history.runs[index], subagents: data.summary };
  }
  if (type === 'artifact') {
    const index = history.artifacts.findIndex((file) => file.id === data.artifact.id);
    const artifact = { ...data.artifact, ...(runId ? { runId } : {}) };
    if (index < 0) history.artifacts.push(artifact);
    else history.artifacts[index] = artifact;
  }
  if (type === 'image_job') {
    const index = history.imageJobs.findIndex((job) => job.id === data.job.id);
    if (index < 0) history.imageJobs.push(data.job);
    else if (data.job.revision > history.imageJobs[index].revision)
      history.imageJobs[index] = data.job;
  }
  if (type === 'message') {
    const index = history.messages.findIndex((m) => m.id === data.message.id);
    if (index < 0) history.messages.push(data.message);
    else history.messages[index] = data.message;
  }
  if (type === 'assistant_delta') {
    let message = history.messages.find((m) => m.id === data.messageId);
    if (!message) {
      message = {
        id: data.messageId,
        role: 'assistant',
        content: '',
        createdAt: at,
        runId,
        phase: data.phase ?? 'unclassified',
        streamState: 'streaming',
      };
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
    if (url.pathname === '/__fixture/images') {
      // Snapshot-only changes deliberately have no SSE frame: reconnect must load GET.
      const input = data();
      const history = histories.get(input.sessionId);
      if (!history)
        return json(response, 404, {
          error: { code: 'not_found', message: 'Unknown fixture session.' },
        });
      if (input.jobs) history.imageJobs = input.jobs;
      if (input.artifacts) history.artifacts.push(...input.artifacts);
      if (input.capabilities) imageCapabilities = input.capabilities;
      if (input.getJobs) imageGetOverrides.set(input.sessionId, input.getJobs);
      if (input.omitImageEvents) omitImageEvents.add(input.sessionId);
      if (input.approvalFailures)
        for (const [jobId, failure] of Object.entries(input.approvalFailures))
          approvalFailures.set(jobId, failure);
      return json(response, 200, { fixture: true });
    }
    if (url.pathname === '/__fixture/h004') {
      const history = histories.get(sessions[0].id);
      const runId = initialRunId;
      history.attachments = ['upload-one', 'upload-two'].map((id) => ({
        id,
        name: `${id}.txt`,
        size: 18,
        mimeType: 'text/plain',
        downloadUrl: `/api/attachments/${id}/download`,
      }));
      history.artifacts = Array.from({ length: 20 }, (_, index) => ({
        id: `h004-file-${index}`,
        name: index === 19 ? 'report.txt' : `illustration-${index}.png`,
        mimeType: index === 19 ? 'text/plain' : 'image/png',
        size: index === 19 ? 20 : h004Images[index % 2].length,
        downloadUrl: `/api/artifacts/h004-file-${index}/download`,
        ...(index < 19
          ? {
              previewUrl: `/api/files/h004-file-${index}/preview`,
              referencePaths: [`/fixture/workspace/illustration-${index}.png`],
            }
          : {}),
        runId,
        messageId: 'h004-final',
      }));
      history.messages = [
        {
          id: 'h004-user',
          role: 'user',
          content: 'Fixture: inspect these files and illustrate the comparison.',
          createdAt: at,
          runId,
          attachmentIds: history.attachments.map((file) => file.id),
          zipUrl: '/api/sessions/fixture%2Fchat-a/messages/h004-user/files.zip',
        },
        {
          id: 'h004-final',
          role: 'assistant',
          phase: 'final',
          streamState: 'completed',
          createdAt: at,
          runId,
          content: [
            'First illustration belongs here.\n\n![First illustration](/fixture/workspace/illustration-0.png)\n\nThe second illustration follows this explanation.\n\n![Second illustration][second]\n\n[second]: /api/files/h004-file-1/preview\n\n[Download first original](/api/artifacts/h004-file-0/download)',
            ...Array.from({ length: 8 }, (_, offset) => {
              const index = offset + 2;
              return `Selected illustration ${index + 1} belongs after this explanation.\n\n![Selected illustration ${index + 1}](/fixture/workspace/illustration-${index}.png)`;
            }),
            '| Comparison criterion with meaningful words | First outcome | Second outcome | Notes |\n| --- | --- | --- | --- |\n| Long criteria remain readable without one-letter lines | An explanation with enough words to wrap across normal lines in its own cell. | Another outcome with a deliberately long unbroken token abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz | Supporting notes remain readable. |',
            'Ten selected illustrations belong in this narrative; nine drafts remain downloadable with optional previews.',
          ].join('\n\n'),
        },
      ];
      history.runs = [
        {
          id: runId,
          kind: 'message',
          status: 'completed',
          createdAt: at,
          updatedAt: at,
          artifactIds: history.artifacts.map((file) => file.id),
          attachmentIds: history.attachments.map((file) => file.id),
          finalMessageId: 'h004-final',
          zipUrl: '/api/sessions/fixture%2Fchat-a/runs/fixture%2Finitial-run/artifacts.zip',
          filesZipUrl: '/api/sessions/fixture%2Fchat-a/runs/fixture%2Finitial-run/files.zip',
          subagents: summary(),
        },
      ];
      history.activities = [];
      history.events = [];
      return json(response, 200, { fixture: true });
    }
    if (url.pathname === '/__fixture/vision') {
      vision = data().enabled;
      return json(response, 200, { vision });
    }
    if (url.pathname === '/__fixture/event') {
      const input = data();
      const event = emit(
        input.sessionId,
        input.type,
        input.data,
        input.named !== false,
        input.runId,
      );
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
      return json(response, 200, { version: '0.0.2', status: 'ok', visionAvailable: vision });
    if (url.pathname === '/api/image-capabilities') {
      calls.push({ action: 'image-capabilities' });
      return json(response, 200, imageCapabilities);
    }
    if (url.pathname === '/api/sessions' && request.method === 'GET')
      return json(response, 200, { sessions });
    if (url.pathname === '/api/sessions' && request.method === 'POST') {
      const s = session(`fixture/new-${++counter}`, 'New fixture conversation');
      sessions.unshift(s);
      histories.set(s.id, freshHistory());
      calls.push({ action: 'create', id: s.id });
      return json(response, 201, { session: s });
    }
    const imageRoute =
      /^\/api\/sessions\/([^/]+)\/image-jobs(?:\/([^/]+)\/(approval|approval-token|cancel))?$/.exec(
        url.pathname,
      );
    if (imageRoute) {
      const id = decodeURIComponent(imageRoute[1]);
      const history = histories.get(id);
      if (!history)
        return json(response, 404, {
          error: { code: 'not_found', message: 'Unknown fixture session.' },
        });
      if (!imageRoute[2] && request.method === 'GET') {
        calls.push({ action: 'image-jobs', id });
        const jobs = imageGetOverrides.get(id) ?? history.imageJobs;
        imageGetOverrides.delete(id);
        return json(response, 200, { jobs });
      }
      const jobId = decodeURIComponent(imageRoute[2] ?? '');
      const job = history.imageJobs.find((item) => item.id === jobId);
      if (!job || job.sessionId !== id)
        return json(response, 404, {
          error: { code: 'not_found', message: 'Unknown fixture image job.' },
        });
      if (imageRoute[3] === 'approval-token' && request.method === 'GET') {
        // UI sequencing fixture only. Proxy-secret/origin enforcement is owned
        // by the real server and requires separate deployment security acceptance.
        calls.push({ action: 'image-approval-token', id, jobId });
        if (approvalFailures.get(jobId) === 'denied') {
          approvalFailures.delete(jobId);
          return json(response, 403, {
            error: {
              code: 'approval_forbidden',
              message: 'Image approval is unavailable from this browser origin.',
            },
          });
        }
        const approvalToken = `fixture-approval-token-${++approvalCounter}`;
        approvalTokens.set(jobId, approvalToken);
        return json(response, 200, { approvalToken });
      }
      if (request.method !== 'POST')
        return json(response, 405, {
          error: { code: 'method_not_allowed', message: 'POST required.' },
        });
      if (imageRoute[3] === 'approval') {
        const input = data();
        if (
          Object.keys(input).length !== 2 ||
          !['approve', 'reject'].includes(input.decision) ||
          typeof input.approvalToken !== 'string'
        ) {
          return json(response, 400, {
            error: {
              code: 'invalid_request',
              message: 'Only decision and approvalToken are accepted.',
            },
          });
        }
        calls.push({ action: 'image-approval', id, jobId, body: input });
        if (approvalFailures.get(jobId) === 'expired') {
          approvalFailures.delete(jobId);
          approvalTokens.delete(jobId);
          return json(response, 403, {
            error: {
              code: 'approval_token_expired',
              message: 'The image approval token expired. Click again to retry.',
            },
          });
        }
        if (approvalTokens.get(jobId) !== input.approvalToken)
          return json(response, 403, {
            error: {
              code: 'approval_token_invalid',
              message: 'A fresh browser approval token is required.',
            },
          });
        const previous = imageDecisions.get(`${id}:${jobId}`);
        if (previous === input.decision) return json(response, 200, { job });
        if (job.state !== 'awaiting_approval' || !job.adjustment) {
          return json(response, 409, {
            error: {
              code: 'invalid_state',
              message: 'The image job is no longer awaiting approval.',
            },
          });
        }
        const updated = {
          ...job,
          revision: job.revision + 1,
          state: input.decision === 'approve' ? 'queued' : 'cancelled',
          cancelRequested: input.decision === 'reject',
        };
        imageDecisions.set(`${id}:${jobId}`, input.decision);
        if (input.decision === 'approve') updated.queuePosition = 1;
        else updated.finishedAt = at;
        emit(id, 'image_job', { job: updated }, true, job.runId);
        emit(
          id,
          'activity',
          {
            activity: {
              id: `approval/${jobId}`,
              runId: job.runId,
              kind: 'tool',
              name: 'image_approval',
              status: 'completed',
              summary:
                input.decision === 'approve'
                  ? 'User approved the saved image adjustment.'
                  : 'User rejected the saved image adjustment.',
              startedAt: at,
              updatedAt: at,
              finishedAt: at,
            },
          },
          true,
          job.runId,
        );
        return json(response, 200, { job: updated });
      }
      calls.push({ action: 'image-cancel', id, jobId, body: data() });
      const active = ['running', 'saving'].includes(job.state);
      const updated = {
        ...job,
        revision: job.revision + 1,
        state: active ? job.state : 'cancelled',
        cancelRequested: true,
      };
      if (!active) updated.finishedAt = at;
      emit(id, 'image_job', { job: updated }, true, job.runId);
      return json(response, 200, { job: updated });
    }
    const filesZip = /^\/api\/sessions\/([^/]+)\/(runs|messages)\/([^/]+)\/files\.zip$/.exec(
      url.pathname,
    );
    if (filesZip) {
      if (url.search) return json(response, 400, { error: { code: 'invalid_query' } });
      const sessionId = decodeURIComponent(filesZip[1]),
        owner = decodeURIComponent(filesZip[3]);
      const history = histories.get(sessionId);
      const record =
        filesZip[2] === 'runs'
          ? history?.runs.find((run) => run.id === owner)
          : history?.messages.find((message) => message.id === owner && message.role === 'user');
      if (!record) return json(response, 404, { error: { code: 'not_found' } });
      const files = [
        ...(filesZip[2] === 'runs'
          ? history.artifacts.filter((file) => record.artifactIds.includes(file.id))
          : []),
        ...history.attachments.filter((file) => record.attachmentIds?.includes(file.id)),
      ];
      if (files.length < 2) return json(response, 400, { error: { code: 'not_multiple_files' } });
      calls.push({ action: 'files-zip', id: sessionId, owner });
      response.writeHead(200, {
        'Content-Type': 'application/zip',
        'Content-Disposition': 'attachment; filename="fixture-reply-files.zip"',
        'X-Fixture-Only': 'synthetic-stored-zip',
      });
      return response.end(
        fixtureZip(
          files.map((file) => ({
            name: file.name,
            content:
              file.mimeType === 'image/png' ? imageBody(file) : Buffer.from(`FIXTURE ${file.name}`),
          })),
        ),
      );
    }
    const zip = /^\/api\/sessions\/([^/]+)\/runs\/([^/]+)\/artifacts\.zip$/.exec(url.pathname);
    if (zip) {
      const sessionId = decodeURIComponent(zip[1]),
        runId = decodeURIComponent(zip[2]);
      const run = histories.get(sessionId)?.runs.find((run) => run.id === runId);
      if (!run)
        return json(response, 404, {
          error: { code: 'not_found', message: 'Unknown fixture run.' },
        });
      calls.push({ action: 'zip', id: sessionId, runId });
      // Routing specimen only: the fixture does not claim server ZIP-content validation.
      response.writeHead(200, {
        'Content-Type': 'application/zip',
        'Content-Disposition': 'attachment; filename="fixture-reply.zip"',
        'X-Fixture-Only': 'route-only-empty-zip',
      });
      return response.end(Buffer.from('504b0506000000000000000000000000000000000000', 'hex'));
    }
    const preview = /^\/api\/files\/([^/]+)\/preview$/.exec(url.pathname);
    if (preview) {
      const id = decodeURIComponent(preview[1]);
      const file = [...histories.values()]
        .flatMap((history) => history.artifacts)
        .find((file) => file.id === id);
      const png = file?.mimeType === 'image/png';
      if (id !== 'fixture/pipeline-svg' && !png)
        return json(response, 404, {
          error: { code: 'not_found', message: 'Unknown fixture preview.' },
        });
      calls.push({ action: 'preview', id });
      response.writeHead(200, {
        'Content-Type': png ? 'image/png' : 'image/svg+xml',
        'Content-Security-Policy': "sandbox; default-src 'none'; style-src 'unsafe-inline'",
        'X-Content-Type-Options': 'nosniff',
      });
      return response.end(png ? imageBody(file) : svg);
    }
    const attachment = /^\/api\/attachments\/([^/]+)\/download$/.exec(url.pathname);
    if (attachment) {
      const id = decodeURIComponent(attachment[1]);
      const file = [...histories.values()]
        .flatMap((history) => history.attachments)
        .find((file) => file.id === id);
      if (!file)
        return json(response, 404, {
          error: { code: 'not_found', message: 'Unknown fixture attachment.' },
        });
      calls.push({ action: 'attachment-download', id });
      response.writeHead(200, {
        'Content-Type': 'text/plain',
        'Content-Disposition': `attachment; filename="${file.name.replaceAll('"', '_')}"`,
      });
      return response.end('FIXTURE upload download — not original user data.');
    }
    const artifact = /^\/api\/artifacts\/([^/]+)\/download$/.exec(url.pathname);
    if (artifact) {
      const id = decodeURIComponent(artifact[1]);
      const file = [...histories.values()]
        .flatMap((history) => history.artifacts)
        .find((file) => file.id === id);
      const png = file?.mimeType === 'image/png';
      calls.push({ action: 'download', id });
      response.writeHead(200, {
        'Content-Type': png
          ? 'image/png'
          : id === 'fixture/pipeline-svg'
            ? 'image/svg+xml'
            : 'text/markdown',
        'Content-Disposition': `attachment; filename="${png ? file.name.replaceAll('"', '_') : id === 'fixture/pipeline-svg' ? 'pipeline.svg' : 'streaming-review.md'}"`,
      });
      return response.end(
        png
          ? imageBody(file)
          : id === 'fixture/pipeline-svg'
            ? svg
            : '# Fixture review\nNot live inference.\n',
      );
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
        // Jobs come from the dedicated list. A bounded text snapshot may have
        // no image events, so stale list responses must not erase newer cards.
        return json(response, 200, {
          session: s,
          ...history,
          imageJobs: undefined,
          events: omitImageEvents.has(id)
            ? history.events.filter((event) => event.type !== 'image_job')
            : history.events,
          environment,
        });
      }
      if (operation === 'messages') {
        const input = data();
        if (
          input.imageReferences !== undefined &&
          (!Array.isArray(input.imageReferences) ||
            input.imageReferences.some(
              (fileId) =>
                !history.artifacts.some(
                  (file) => file.id === fileId && file.mimeType.startsWith('image/'),
                ),
            ))
        ) {
          return json(response, 400, {
            error: {
              code: 'invalid_image_reference',
              message: 'Image references must identify owned artifacts.',
            },
          });
        }
        calls.push({ action: 'send', id, ...input });
        const runId = `fixture/run-${++counter}`;
        const queued = ['queued', 'running', 'compacting', 'cancelling'].includes(s.status);
        emit(
          id,
          'run',
          {
            run: {
              id: runId,
              kind: 'message',
              status: queued ? 'queued' : 'running',
              createdAt: at,
              updatedAt: at,
              finalMessageId: null,
              artifactIds: [],
              subagents: summary(queued ? 0 : 1),
            },
          },
          true,
          runId,
        );
        emit(
          id,
          'message',
          {
            message: {
              id: `user/${counter}`,
              role: 'user',
              content: input.text,
              createdAt: at,
              attachmentIds: input.attachmentIds,
              imageReferences: input.imageReferences,
              runId,
            },
          },
          true,
          runId,
        );
        if (!queued) {
          emit(id, 'state', { status: 'running' }, true, runId);
          emit(
            id,
            'activity',
            {
              activity: {
                id: `tool/${counter}`,
                runId,
                kind: 'tool',
                name: 'shell',
                status: 'in_progress',
                summary: 'Fixture task started',
                command: 'npm test -- fixture',
                detail: 'This is a contract fixture, not live inference.',
                startedAt: at,
                updatedAt: at,
              },
            },
            true,
            runId,
          );
          emit(
            id,
            'assistant_delta',
            {
              messageId: `assistant/${counter}`,
              text: 'Checking the fixture pipeline',
              phase: 'intermediate',
            },
            false,
            runId,
          );
        }
        return json(response, 202, { runId });
      }
      if (operation === 'cancel') {
        calls.push({ action: 'cancel', id });
        emit(id, 'state', { status: 'cancelling' });
        json(response, 202, { status: 'cancelling' });
        setTimeout(() => {
          for (const run of [...history.runs]) {
            if (['queued', 'running', 'cancelling'].includes(run.status)) {
              emit(
                id,
                'run',
                { run: { ...run, status: 'cancelled', subagents: { ...summary(), cancelled: 1 } } },
                true,
                run.id,
              );
              emit(id, 'done', { runId: run.id }, true, run.id);
            }
          }
          emit(id, 'state', { status: 'interrupted' });
        }, 100);
        return;
      }
      if (operation === 'handoff') {
        calls.push({ action: 'handoff', id });
        const target = session(`fixture/handoff-${++counter}`, 'Continued: streaming pipeline');
        target.context = {
          used: null,
          limit: 480000,
          estimated: true,
          stale: true,
          updatedAt: at,
          source: 'fixture handoff not measured',
        };
        sessions.unshift(target);
        histories.set(target.id, {
          ...freshHistory(),
          messages: [
            {
              id: 'handoff-summary',
              role: 'assistant',
              content: 'Fixture handoff summary. The original conversation is retained.',
              createdAt: at,
            },
          ],
        });
        json(response, 202, { runId: `fixture/handoff-run-${counter}` });
        setTimeout(() => emit(id, 'handoff', { newSessionId: target.id }), 80);
        return;
      }
      if (operation === 'uploads') {
        const name = /filename="([^"]+)"/.exec(body)?.[1] ?? 'file.txt';
        calls.push({ action: 'upload', id, field: /name="file"/.test(body), name });
        const attachmentId = `fixture/attachment-${++counter}`;
        const attachment = {
          id: attachmentId,
          name,
          mimeType: 'text/plain',
          size: body.length,
          downloadUrl: `/api/attachments/${encodeURIComponent(attachmentId)}/download`,
        };
        history.attachments.push(attachment);
        return json(response, 201, { attachment });
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

function fixtureZip(files) {
  const entries = [],
    central = [];
  let offset = 0;
  for (const file of files) {
    const name = Buffer.from(file.name),
      data = file.content;
    let crc = 0xffffffff;
    for (const byte of data) {
      crc ^= byte;
      for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
    crc = (crc ^ 0xffffffff) >>> 0;
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50);
    local.writeUInt16LE(20, 4);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(name.length, 26);
    const directory = Buffer.alloc(46);
    directory.writeUInt32LE(0x02014b50);
    directory.writeUInt16LE(20, 4);
    directory.writeUInt16LE(20, 6);
    directory.writeUInt32LE(crc, 16);
    directory.writeUInt32LE(data.length, 20);
    directory.writeUInt32LE(data.length, 24);
    directory.writeUInt16LE(name.length, 28);
    directory.writeUInt32LE(offset, 42);
    entries.push(local, name, data);
    central.push(directory, name);
    offset += local.length + name.length + data.length;
  }
  const directory = Buffer.concat(central),
    end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50);
  end.writeUInt16LE(files.length, 8);
  end.writeUInt16LE(files.length, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...entries, directory, end]);
}
