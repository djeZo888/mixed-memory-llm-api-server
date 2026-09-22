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
`SHA256SUMS` pins all five patches;
its SHA256 is the image/launcher admission identity:
`00418190e3abae6ef9e44c60dedfda220d2a60fa9d64e364fa650d142362f8b7`.
`source.SHA256SUMS` and `patched.SHA256SUMS` identify all six affected source files.
`identity.json` provides the same mapping and the transport/dependency pins.

For reusable dependency layers, first COPY only `0003` and the `dependency-*`
manifests, verify original hashes, apply `0003`, verify patched hashes, then run
`pnpm install --frozen-lockfile`. COPY generic source patches later; verify
`source-source.SHA256SUMS`, apply `0001`, `0002`, `0004`, `0005` **sequentially** with an
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
