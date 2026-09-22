# ai-harness web 0.0.1

React/Vite frontend for Web/server contract v1 in the H001 coordination handoff.
Single shared workspace, no login, same-origin `/api`. Production contains no
fixture data, credential, model selector or inference budget setting.

## Build and integration

Use Node 24 or newer. From this directory:

```sh
npm ci
npm test
npm run typecheck
npm run build
```

The backend serves `dist/`. Build assets use absolute root paths. No proxy,
backend address or host credential is embedded. `npm run dev` binds only
`127.0.0.1:5193`; `npm run preview` binds `127.0.0.1:4193`. Both ports are strict.
These commands do not supply an API: production requires the reviewed backend
on the same origin. No changes to server/deploy are included here.

## Fixture browser verification

```sh
npm run build
PLAYWRIGHT_CHANNEL=chrome npm run test:browser
```

This uses installed Google Chrome. Alternatively install Playwright Chromium
with `npx playwright install chromium` and omit `PLAYWRIGHT_CHANNEL`.
The browser test starts its own explicit HTTP/SSE contract fixture on
`127.0.0.1:4193`, serves the production build and shuts it down afterward. It
refuses to reuse an existing server. The fixture is under `tests/`, never
imported by application code. Screenshots include a fixture label and default
to `../../../evidence/` outside Git; set `H001_WEB_EVIDENCE` to another evidence
directory when integrating. Screenshots and tests are not live inference,
vision, ACP, deployment or engine acceptance.

## State, replay and safety

- The server persists sessions and full visible messages. Local storage holds
  only the last selected opaque session ID. Drafts are local to the composer;
  switching conversations discards unsent text. Completed uploads remain
  associated with their original session in the current browser instance.
- Native EventSource handles reconnection and Last-Event-ID. The initial URL
  includes `after=N`. Both named frames and ordinary `message` envelopes carry
  the complete Event object. IDs deduplicate events within one session.
- GET snapshots are canonical. Their messages and maximum retained event ID
  must describe one consistent cutoff; deltas buffered during GET are applied
  only after that cutoff. Retain the latest event in snapshots even when older
  events expire. This requirement was relayed for server integration. An older
  snapshot cannot rewind a newer rendered stream. GET resync runs on stream
  open/reconnect and `done`; stale session responses/subscriptions are ignored.
- Browser cleanup aborts only GETs and closes EventSource. It never calls the
  cancellation endpoint. POST actions are not automatically retried. Explicit
  Stop uses `/cancel`; both deletion responses (200/202) remove the chat locally.
- Context uses only reported Context fields and a fixed 480,000-token window.
  Unknown used is not zero. Estimated/measured/stale values are distinguished;
  input and output share the window. The UI imposes no inference token limits.
- Activity contains real progress/error events only. The latest 100 activity
  entries are displayed; detail is capped at 6,000 characters, labels at 300.
  This display bound never truncates conversation messages or server history.
- Markdown uses `react-markdown` without raw HTML plugins. Only explicit HTTP(S)
  links with no embedded credentials are navigable; Markdown images are rendered
  as text to avoid remote image fetches. Code/tool text is escaped. Artifact
  links are always constructed from encoded IDs under `/api/artifacts/…/download`,
  ignoring untrusted `downloadUrl` navigation targets. The
  [react-markdown security guidance](https://github.com/remarkjs/react-markdown#security)
  and [EventSource interface](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
  informed those implementation choices.
- PDF and source/text attachments are supported. Images require health to
  explicitly report `visionAvailable: true`; the backend remains responsible
  for MIME/content validation and upload limits.

First-party source is MIT licensed. Third-party packages retain their licenses.
