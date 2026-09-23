# Session image MCP adapter

Three stdio MCP tools connect native MiniMax main agents and delegated children
to the host-owned persistent image broker:

- `image_capabilities {}` reads current operation/size/reference-count profiles.
- `image_generate {prompt, size?, seed?, references?}` creates one opaque image;
  the default size is `1920x1080`.
- `image_edit {prompt, references, size?, seed?}` requests a new edited version.
  It leaves size absent by default so the broker preserves source geometry when
  qualified. Unavailable editing never becomes a generation or alternate service.

Each reference is exactly `{fileId}` for a current-session upload/artifact, or
`{workspacePath}` for an anchored relative workspace file. Input schemas reject
URLs, absolute paths, traversal components, identity/auth fields, backend options,
caller request IDs and approval flags. The host validates ownership, symlinks,
regular files and the immutable reference snapshots; MCP cannot grant access.

The fixed origin is `http://10.0.2.2:8081/v1`. The process reads only the existing
`AI_HARNESS_GATEWAY_TOKEN`; optional `AI_HARNESS_GATEWAY_URL` must exactly match
that fixed value. No session ID is needed or accepted. Protected inference keys
remain outside the container. Redirects are rejected. There is no direct ai-vm
client or alternative provider.

## Submission and lifetime

Each tool invocation generates one request ID and sends one POST. It never
resubmits, including after HTTP failures, response parsing failures or ambiguous
disconnects. An uncertain result preserves that request ID and instructs the
assistant to inspect the existing job card. Once a job is accepted, only its GET
route is polled, with delays of 1, 2, 4, 8 and then at most 15 seconds. Transient
GET errors may retry; a non-transient access error stops observation.

The total budget is 50 minutes, including submission. Each HTTP exchange has a
30-second deadline within the remaining total budget. This covers the broker's
30-minute queue plus 15-minute backend budget with bounded cleanup. Native MCP
configuration must use the matching `3000000` millisecond timeout.

`awaiting_approval` returns immediately and directs the assistant to the browser
approval card. The adapter exposes no approval or cancellation tool. Ending the
tool, disconnecting MCP, or ending the engine turn never calls `/cancel` and never
erases a submitted job. Explicit Stop/Delete behavior belongs to the browser and
host broker. `running`/`saving` with `cancelRequested` means cancellation is
draining; no instant GPU cancellation is claimed. Only server-provided elapsed
metadata is forwarded as MCP progress; notification delivery cannot block polling.

Results contain selected job metadata, source names/hashes/dimensions, artifact
IDs, and relative output paths. They exclude session identity, echoed prompts,
unknown properties, image bytes, backend settings and host paths. Error codes and
useful messages are retained with credential/path/data-URI redaction. There is no
raw response or exception logging.

## Wire integration checkpoint

The frozen contract defines ImageJob fields, routes and submission semantics but
leaves capabilities and the completion path envelope unspecified. Pending the
tracked Worker1 answer in the task's `INTERFACE.md`, this adapter and the web
fixtures use this single provisional capability shape:

```json
{
  "model": "Qwen-Image-2.1",
  "operations": {
    "generation": {"available": true, "profiles": [{"referenceCount": 0, "sizes": ["1920x1080"]}]},
    "edit": {"available": false, "profiles": [], "reason": "No qualified edit profile"}
  }
}
```

Optional root metadata: `available`, `opaque`, `defaultSize`, `reason`. This is a
wire-shape example, not a claim about deployed capabilities. Missing/malformed
profiles disable that operation while preserving other valid operation profiles;
an unknown overall schema fails closed. `size`, requested/actual sizes and profile sizes
use `WIDTHxHEIGHT` strings; dimensions in source/adjustment records also accept
`{width,height}`. GET/POST job responses accept the job itself or `{job}`; completed
jobs use the provisional relative `workspacePath` field. No unknown metadata is
passed through. Reconcile these exact fields before server integration/deployment.

## Packaging and focused offline verification

The engine image copies this directory to `/opt/ai-harness/tools/image` and runs
`npm ci --omit=dev --ignore-scripts` against the committed lock. Profile MCP points
to `node /opt/ai-harness/tools/image/image-mcp.mjs` with the existing session bearer
environment. SDK 1.30.0 and Zod 4.6.5 reuse the reviewed search dependency graph.
No native engine/model pins or text lane settings change.

Run `node --test ai-harness/tools/image/test/image.test.mjs` from the repository
root with those dependencies already installed. The fixtures use injected fetch
responses, a virtual clock, official SDK in-memory exchanges and real stdio child
processes. They make no HTTP requests, open no listeners and contact no VM or API.
The two stdio launches verify the same adapter registration for main/child launch
environment; they do not prove a built native engine's role tool roster.

Source/offline evidence is not deployment evidence. Native main/subagent image
calls, live server wire integration, approval processing, queue/load, image
quality, GPU memory, runtime restart and deployment remain **NOT_TESTED** here.
