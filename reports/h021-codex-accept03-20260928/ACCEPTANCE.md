# ACCEPT03 acceptance procedure

This is a prepared procedure, not live acceptance. Use the reviewed candidate,
current W1 production profile, native Linux0.158.0, Qwen0 through shared Sova
admission, context480000, output cap1024, no inference retries. MiniMax remains
default. MiMo/H019 and independent MiniMax/MiMo HTTP400 remain outside scope.

## Matched batch

`ai-harness/deploy/tests/h021-matched-acceptance.mjs --prepare OUT [OWNED_PDF]`
copies only buggy implementations and unchanged independent tests. For PDF,
supply an independently authored fixture PDF. The prompt has no expected numeric
answers or generator instructions. Keep PLAN.json, CASES.json, reference repairs
and answer keys outside model workspaces. Image is excluded and remains W1-owned.

One reviewed `h021-matched-batch-go-v1` grant contains exact candidate/image/profile,
Sova origin, central lane owner, expiry, Qwen0/context/output policy, deployed
readback path/hash and a finite schedule of at most10 unique engine/case pairs.
Order each Python/C++/Node/research/PDF case MiniMax then Codex. Run with:

```
node ai-harness/deploy/tests/h021-matched-acceptance.mjs \
  --run GO.json PREPARED_INPUTS NEW_EVIDENCE_DIR W1_EXISTING_HOST_HOOK.mjs
```

The host hook is a thin adapter to W1's existing authority, not a new observer.
`confirmSettlement({sessionId,runId,exactSource,pilotId})` must return
`{sessionId,settled:true,evidence}` only after existing gateway request/usage
ledgers, native container/children and image ownership prove no accepted/queued/
draining/uncertain work. Its exact deployed path is pending W1. Missing/false/
failed hook halts the batch. No per-case root permission is required. Public
`idle`, final output or Stop ACK never supplies settlement proof.

Each case uses one prompt POST with a durable prior dispatch marker, verifies
upload bytes, saves snapshot/events and downloaded artifacts, and reconnects via
readback without submitting again. POST failure is never retried. The runner
never invokes a model port, executes downloaded code on the Mac host, changes
services or deletes chats. A crash/timeout requires ownership review, not rerun.

A terminal run is only PENDING_INDEPENDENT_CHECK. Run the original language tests
against the downloaded implementation in the existing owned rootless workspace,
with unchanged test checksums. Stop C++ execution if compilation fails. Confirm
actual research search/open tool calls and final link to the page actually read.
For PDF, independently inspect extracted text, rendered page1 and created summary
artifact; expected3.3V and250mA=0.25A stay in operator material. Preserve initial
failures. One diagnosed repair/repeat requires the existing batch owner to account
for it explicitly; this runner does not retry. Null token fields mean unavailable;
occupied context is not input/output usage. Attach W1 provider usage/retry evidence.

## Actual desktop/mobile and lifecycle readback

Reuse selectors/flow in web/tests/h021-codex-smoke.mjs and app.browser.ts at
1440x1000 and390x844 on the actual candidate. Use owned acceptance chats. Capture
fresh deployed health/version/profile readback first; fixture UI PASS is not live.

- MiniMax default; Codex preview option available only under qualified deployment.
  Existing chat's engine stays visible and immutable through refresh/follow-up.
- Attach a small owned file; verify uploaded/downloaded SHA256. Follow-up references
  that same file, receives a distinct run and retains original messages/artifacts.
- Show actual commentary/tool progress in Activity and final answer separately.
  Unknown native phase remains unclassified; no inferred reasoning. Context shows
 480K Qwen; MiMo950K remains gated. Check mobile overflow and accessible controls.
- Disconnect/reconnect and refresh during owned work; original event/run IDs remain
  and W1 gateway counters show no extra inference submission. Do not use fixture
 `/__fixture/*` endpoints on a real application.
- Stop only after a real request is accepted. Reuse `api.cancel`/Stop all, then verify
  parent/container/children/queued and accepted requests/image ownership settled
  using W1's authority before next case. Record uncertain outcome honestly.
- For engine-aware preview disable, W1 uses current engine-aware release and keeps
  data/release backup. Existing Codex chats remain readable/downloadable, follow-up
  rejects without MiniMax resume, new MiniMax chat works. Re-enable only under
  existing root rollout scope. Never roll back to a pre-H021 engine-unaware release.

## Rootless direct tools window (separate exact GO)

Use W1's exact pinned rootless image/profile and ordinary task launcher. No model
is needed: a stdio MCP client lists/calls `browser_open` on an approved public
primary page, records final loaded URL/title/text/screenshot; `browser_download`
uses a reviewed public PDF URL, records bytes/SHA256, preserves source and tests
private URL rejection. Do not use loopback on the public browser tool or change
its policy to accommodate a fixture. Verify sandbox/cleanup from the owned scope.

PDF is a shell helper, not an advertised standalone PDF MCP. Invoke the installed
`pdf_tools.py --help`, then extract source.pdf page1, render page1, create a static
summary.md to artifacts/summary.pdf, re-extract and render it. Inspect actual page
images. Never replace helper failures with reportlab or direct browser calls and
claim helper acceptance. Mac extraction/PDFium results do not qualify Linux.
