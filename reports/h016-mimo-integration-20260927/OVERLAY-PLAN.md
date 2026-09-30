# Root-review-only engine overlay inputs

No build or activation performed. Use the exact retained local base image
sha256:9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c
from release7143c17d73173db9364b77956679c86d7026a4ae. First verify its immutable
image ID and existing labels, registered harness storage/free-space guards and
absence of active owned engine work. Preserve this image/release for rollback.

Native upstream revision: ae65651df5f97ae1085ab4e19964f4b78c769a4e.
Previous patchset: e487935b3d6efce51216b8755cbd712912c30c7d45f6a9e5e293f0f998f89a65.
New patchset: a6dd7df37313edc4ea2f6bc742ffb6ff431a37abacb2facdbbf422a4c9f9d4bd.
Only native application source delta is in
packages/local-runtime-v2/src/service/model-system/resolution/model-token-estimator.ts:
add mimo-v2.6-pro-rl alongside GLM to the existing UTF-8 scheduling selector.
Exact new source SHA256:
649b21e84263c278c1a43d8cc17ab19fdbf08a5a4b95c666d9a914dd81abea68.
`deploy/patches/0010-frontier-model-accounting.patch`, SHA256SUMS, identity.json,
patched.SHA256SUMS, source-patched.SHA256SUMS and source-patches.SHA256SUMS
are synchronized with engine/pins.json, launcher and Containerfile labels.

In a fresh root-reviewed build task, reconstruct an isolated pinned source from
the existing verified source/dependency cache, apply the reviewed patches and
verify source/patched hashes. Reuse the frozen pnpm lock and installed graph.
Compile/package the application through the existing Containerfile build-stage
commands (pnpm typecheck; MCODE_RELEASE_TAG=v0.5.1 pnpm build; existing
package-cli-release.mjs), with existing external mcode-tools/native artifacts
reused and hash-verified. No model runtime or unchanged native tool rebuild is
part of this task. If the retained cache cannot satisfy that constraint, report
the specific missing build input rather than silently fetching/rebuilding it.

The runtime overlay starts FROM the immutable9ef885 base and replaces only the
changed compiled application bundle/chunks and corresponding source/probe
provenance produced by that verified packaging, plus:

- /opt/ai-harness/engine/configure-profile.mjs from this commit;
- /opt/ai-harness/config/active-frontier.json, byte-identical to the host release;
- /usr/local/share/ai-harness-patches source/identity/checksum set;
- the changed patchset label (only AFTER actual compiled estimator replacement).

Compiled output hashes and the exact changed-file allowlist cannot be named
before the future build; derive and review them against the base release.
Do not copy source TS alone into the runtime and call it compiled, and do not
relabel9ef885 as the new patchset. Leave unchanged /opt/minimax/node_modules,
embedded/mcode-tools, native binaries, browser/tools/dependencies untouched and
compare their hashes. Produce a new immutable image ID and frozen overlay
manifest. The host server build and web build are separate release artifacts.

For a MiMo trial, inject the reviewed qualified active-frontier configuration
only after W1 runtime evidence and root review; config hashes must agree between
host and image. The shipped source config remains GLM/default, MiMo disabled.
Verify actual generated managed profile model/context/output, actual compiled
MiMo estimator, native tool roster including browser, and exact custom-conflict
preservation before activation. New compiled engine/image acceptance is pending.
