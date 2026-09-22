# Reviewed MiniMax patch set

Apply only to `ae65651df5f97ae1085ab4e19964f4b78c769a4e`.
`0001` aligns the main request default and common OpenAI-compatible adapter
fallback to 151 minutes. Explicit native title timeouts remain 10,000/15,000 ms,
with unchanged 1,000/1,024-token budgets; title failure remains nonfatal and
cancels queued requests. The portal names chats. `agentStop.maxActiveSpanMs=0`
remains the profile setting.
`0002` reports native ACP compaction start/completed/failed without changing
compression or occupied-context calculation. See `compaction-notes.md` and
`../engine/README.md` for source evidence and exact test boundaries.

`0003` pins the common adapter's direct Undici dependency to **7.29.1**, matching
Node 24.21.0's built-in Undici major/API. It changes only that importer's package
manifest and the frozen workspace lock, including npm's exact SHA512 integrity.
Other upstream importers retain their existing Undici 8.10.2 dependency. Version 8
cannot supply a dispatcher to this Node version's built-in fetch: a real local
HTTP fixture reproduced `InvalidArgumentError: invalid onRequestStart method`.
`0004` supplies the common adapter with a gateway-only fetch wrapper and a shared
Undici dispatcher. It overwrites fetch-supplied header/body dispatch limits to
9,060,000 ms for **http://10.0.2.2:8081 only**. Agent defaults alone are insufficient
when fetch supplies its own 300-second request options. The wrapper preserves
explicit AbortSignal, body, headers and other fetch options, and retains custom
fetch implementations. Other provider and request origins keep their original
fetch. Redirect dispatches outside the gateway do not receive extended limits.
No global dispatcher, retry algorithm, model capacity or auxiliary output budget
changes are introduced. The common adapter covers main, direct and fallback
compaction requests; short title SDK/AbortSignal limits still win.

`0005` adds only an `unknown` type bridge for the fetch options assertion. The
full Linux typecheck exposed a structural mismatch between the pinned runtime
dispatcher and the ambient `undici-types` declarations. Node 24 transport
fixtures validate that runtime dispatch contract. With comments removed, the
entire provider transpiles to byte-identical JavaScript before/after `0005`
(TypeScript 5.9.3); no runtime behavior or dependency changes are introduced.
The full Linux typecheck/build remains the acceptance gate.

`0001` and `0002` remain byte-identical to PREP. `0001` through `0004` and all
dependency-phase identities remain byte-identical after `0005` was added.
`SHA256SUMS` pins all seven patches;
its SHA256 is the image/launcher admission identity:
`8d3575bc32df22794dea977a4daad75406f617f1a3a4787a739b0fbd651bb034`.
`source.SHA256SUMS` and `patched.SHA256SUMS` identify all 42 affected source files.
`identity.json` provides the same mapping and the transport/dependency pins.

For reusable dependency layers, first COPY only `0003` and the `dependency-*`
manifests, verify original hashes, apply `0003`, verify patched hashes, then run
`pnpm install --frozen-lockfile`. COPY generic source patches later; verify
`source-source.SHA256SUMS`, apply `0001`, `0002`, `0004`, `0005`, `0006`, `0007` **sequentially** with an
individual `git apply --check` before each, then verify
`source-patched.SHA256SUMS`. `0004` is based on the result of `0001`; `0005` follows `0004`. The complete
set may also be applied sequentially before installation. Verify the complete
`SHA256SUMS` admission identity and `patched.SHA256SUMS` before compilation.

The upstream tree is not vendored here. The final image retains these small
review artifacts and carries the patchset label. The pinned release packager
requires clean committed source; a deterministic local build commit can record
the already hash-verified modifications while preserving the original pin in
image metadata. It is not an upstream commit or a publication.

## Local transport fixture

After installing exact `undici@7.29.1` into an isolated fixture directory, run:

```sh
AI_HARNESS_MINIMAX_SOURCE=/absolute/pristine-pinned-source \
AI_HARNESS_UNDICI_MODULE=/absolute/fixture/node_modules/undici/index.js \
node --test ai-harness/deploy/tests/test-provider-patch.mjs \
  ai-harness/deploy/tests/test-gateway-transport.mjs
```

The transport fixture checks all original/patch/final hashes, applies the exact
patches to a temporary copy, and executes the actual extracted adapter helper
using Node fetch and the pinned Undici. A fixture-only connector maps the
reviewed gateway address to an ephemeral local loopback HTTP server; no gateway,
model or internet endpoint is contacted. Injected 20 ms transport limits fail on
delayed headers and delayed body chunks; the exact patched dispatcher survives
both 1.6-second delays. Existing AbortSignal cancels while waiting for headers
and after body streaming starts. Additional checks cover exact origin matching,
URL/Request inputs, custom fetch preservation and unchanged main/title budgets.
These accelerated cases validate timeout behavior without waiting 300 seconds.

Node 24.21.0 source fixtures passed 7/7. The exact helper also passed a TypeScript
5.9.3 check and esbuild 0.28.2 Node ESM bundle/import. `pnpm@9.12.0 install
--lockfile-only --frozen-lockfile --ignore-scripts` accepted all 32 workspace
importers and left the patched lock byte-identical. These are local source and
transport checks; they do not establish Linux image, ACP, full TypeScript,
live model, 151-minute occupied duration or real compaction acceptance.

## Native browser download patch

`0006` sets the native headless provider download root to canonical
`process.cwd()/downloads/browser/<safeSessionId>`, validates each path component
and destination against symlink/nonregular/hardlink escapes, and uses Chromium
GUID filenames via `Browser.setDownloadBehavior(allowAndName)`. The compact native
browser output exposes only completed, checked workspace-relative artifact paths.
Session disposal retains workspace downloads. The sandbox flags are unchanged.
Static containment tests do not claim atomic protection against concurrent
same-user filesystem mutation; native browser and sandbox fixtures supply the
Linux execution evidence separately. No browser MCP or extra mount is added.

## Reviewed native completion bridge

`0007` integrates root-reviewed native commit
`4a70b28e9d038747ff130302c844ccb06367d03f` (original patch SHA256
`e3cdb67ea41ef7e8ef6ee3bc014b79f83da3f5c23a7af25b0deccf96a1bbe10d`).
Integration preserves the `0002` compaction notification in overlapping extension
context and adds that preexisting notification to one initialize test expectation.
No completion runtime behavior is invented or changed from the reviewed patch.
The integrated patch and final source hashes are authoritative in `identity.json`.
Five added paths have `originalSha256:null`; pristine SHA manifests omit those paths,
and the sequential `git apply --check` requires that the new files do not exist.

ACP advertises `mcode/session/settlement/get` only with the native bridge. Its
schema1 receipt distinguishes running/settled/cancelled/unknown using process/run
identities and native tree ownership. A new session with no run must remain
unknown; initialize/session-new/receipt inspection is inference-free validation.
Normal completion, continuation, cancellation, clean restart/rearm, and interrupted
unknown behavior are tested by the reviewed synthetic native suites. Those tests
are not live model inference or full end-to-end application acceptance.
