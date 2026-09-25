# Closed Qwen pair actual-image auth fixture

Source/local control status: **actual image NOT_TESTED**. The separate pair mode
reuses the existing bounded disposable fixture, auth/parser/cache checks and
failure subprocesses. The old `native-pair` still means 131072/262144 and the
existing TP2 defaults remain unchanged; fixture provenance has changed. No model is loaded here;
allocated pool/capacity, GPU placement and real tool continuation require the
separate candidate campaign's model observations.

Only after root source review, current benchmark restoration/ownership release,
a fresh Worker1 dispatch and the current registered storage guards, use:

```bash
python3 -B tests/lifecycle/sglang38_fixture/run_pair_fixture.py \
  --repo "$PWD" \
  --slot gpu0 \
  --output "$EVIDENCE_DIRECTORY/qwen-gpu0-480000.actual-image-auth.json"
```

`EVIDENCE_DIRECTORY` must be an already protected, registered data directory
admitted by the canonical binding; run the current installed guard before and
after. Keep the existing shared lifecycle ownership lease while the fixture
creates its bounded disposable container. Use a new output filename; the
anchored writer refuses existing files and root-filesystem output. Failed or
uncertain fixture cleanup remains a blocker and never produces PASS. Actual
image ID/OCI relationship must be observed, with no pull, GPU assignment,
production secret/model mount or network. The existing 600-second fixture
bound is an upper failure bound, not a promise that the future live session's
load/check budget can accommodate it; root must schedule and arm this separate
gate explicitly. This PREP did not start that clock.

The exact production `sglang38_pair_file_auth.py` pinned-base check and
`bind_variant()` execute with the closed gpu0/gpu1 TP1/480000 backend tuple and unchanged
base launcher. A small fixture facade relocates only the base source path into
the read-only checkout and forwards the existing warmup-timeout fault hook.
One fake discovery GPU and synthetic engine/model startup remain explicit.
This does not attest production CLI execution or actual model serving. Every
`qwen38.AUTH_CHECKS` item must pass against installed pinned native source,
including native auth, alias validation, parser/continuation-template semantics
and bounded failure cleanup. Installed ModelConfig must resolve 480000 with
BF16/YaRN4; that proves configuration resolution, not allocated token pool.

The schema-2 `q38pair_actual_image_auth` receipt requires one context `[480000]`,
one verified exited/removed fixture lifetime, actual host image inspection,
all native results and all legacy provenance hashes. Its `extension_identity`
binds the profile/model/runtime, pair/base wrappers, three adapter source files,
legacy provenance, complete argv and exact fixture adaptations. It retains
`model_execution`, `native_lifespan` and live inference/agent acceptance as
`NOT_TESTED`; it never writes an accepted production receipt.

The candidate arm must bind the raw receipt SHA256, protected registered path
and the same reviewed source map. Import `check_pair_receipt(receipt, repo, slot='gpu0')` from
`run_pair_fixture.py` to validate its exact content. That pure checker does not
authenticate publication and cannot replace the arm's protected-file/source
binding. The required future proof is the actual-image command's successful
receipt and verified cleanup; local tests cannot supply it.

Focused local verification (synthetic, no output receipt published):

```bash
python3 -B -m unittest tests.lifecycle.test_qwen38_pair_fixture -v
```

Run gpu1 separately using `--slot gpu1` and a new protected output filename.
Both receipts bind distinct deployment, alias, port and argv; GPU0 proof cannot
be copied to GPU1. Updated native fixture provenance requires fresh base auth
proof as well; preserved older receipts remain historical. Base production auth
launcher bytes and historical runtime/image/model pins are unchanged. PREP runs no fixture
container, reads no protected inference key and writes no acceptance receipt.

## H005 derived-image mode

The new fixed-pair release requires `--adaptive-overlay` on the command above,
separately for each slot. Omitting that flag selects the preserved historical
parent-image fixture; its receipt cannot admit the H005 derived pair. Production
admission calls `check_pair_receipt(..., adaptive=True)` explicitly.

The derived mode reads the exact source-hashed
`configs/runtimes/h005-runtime-binding.json` through
`scripts/runtime/h005_runtime_binding.py`. Missing completed BUILD identities
fail before Docker execution. It selects the observed immutable text image ID,
preserves the config/manifest identity distinction and parent manifest/config
relationship, merges every final overlay source hash into the legacy source
closure, and independently runs the production installed-overlay verifier before
native imports. The main fixture and its warmup fault children use the same
derived mode. No CLI image/hash overrides or tag fallback exist.

The Uvicorn capture requires exactly the installed native
`GenerationDrainMiddleware`, exactly one outer layer, and exactly the underlying
native `server.app` with the original `server_args` identity. State, auth-layer and
warmup checks use that verified native app; all ASGI requests still traverse the
captured outer wrapper. Subclasses, lookalikes, nested wrappers, substituted apps,
and silently accepting an unwrapped app fail. The dependency fixture also checks
the exact image `DiffusionDrainMiddleware(app)` import and construction from full
pinned patched native source.

Local tests exercise source/receipt controls and dependency fixtures only.
Actual CPU-only built-image imports/msgspec/native auth execution remain
`NOT_TESTED` until the separately authorized native fixture runs. These fixtures
never establish live inference, occupied context, idle CPU, cache residency,
hardware acceptance, or rollout GO.
