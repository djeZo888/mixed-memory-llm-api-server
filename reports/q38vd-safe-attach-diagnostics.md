# Q38VD — safe attach-failure diagnostics

## Status and authority

PASS — bounded source correction and targeted source regressions. Actual image,
container, VM, native fixture, model, GPU and real-key execution: NOT_RUN.
No auth receipt was produced. Installer remains paused. Final source requires
root review before any repeated actual fixture.

Base: `f17ec2c37d4c706752dd3fbe1978519983578b71`.
Branch: `milestone/q38vd-safe-attach-diagnostic`.
Root approved the minimal inner final-handler origin helper and diagnostic-only
copy of the already-required pre-stop inspect in `../coordination-input.md`
(section `Root source extension approval 2026-09-15`), after the opacity gap and
exact proposal were published to `../diagnostic-contract.md`.

User-provided prior Q38V result: 131072 returned ATTACH_FAILED with exact-owned
quiescent container removal; 262144 was not started and no auth receipt exists.
The cause remains unknown. This source change makes no cache/import/auth finding.

## Change

The attach failure now retains `lifetime.attach_diagnostic` containing:

- Fixed schema version, known ATTACH phase, operation (start/attach, exit
  verification, or cleanup), and failure kind. Existing outcomes are unchanged.
- Bounded CLI return code and CLI signal, separately from the independently
  observed container exit code. Docker numeric exit values never prove a native
  signal; that field remains null. Exit state is copied from the first existing
  cleanup inspect before any stop. No additional Docker operation is issued.
- Per-stream captured byte length and SHA-256, marked COMPLETE, PREFIX, or
  UNAVAILABLE. Prefix lengths describe retained bytes, not total emitted bytes.
  Interrupted CLI capture/reap metadata cannot imply daemon quiescence.
- Optional whole-document inner FAIL metadata, parsed only from at most 4096
  stdout bytes. Duplicate/unknown fields, invalid types, malformed UTF-8/JSON,
  excessive nesting, truncation, raw logs and paths are rejected. Stderr is
  never parsed or echoed. No message, local, source line, header, body,
  environment, arbitrary output, secret value, or raw path is retained.

Inspection failure after completed attach retains the completed attach streams;
its operation label identifies exit verification. Timeout, overflow, cancellation,
CLI exception/nonzero exit and cleanup failure remain distinguishable. A CLI
reap timeout retains the original redacted capture failure and reports reap
unverified. Failure always raises LifetimeFailure and main returns status FAIL /
exit 1; diagnostic metadata never enters successful receipt acceptance.

### Necessary inner extension and limits

The existing inner final handler discarded the ordinary exception and emitted
only a generic fixed FAIL code. It now appends one safe fixture callsite tuple:
`run_pinned_image.py`, integer line 1..100000, and a fixed allowlisted exception
class (OTHER for unknown classes). It visits at most 64 traceback links, skips
the exact generic `require.__code__` frame, and never formats traceback text or
reads locals/source/messages. Overflow yields no origin. Its FAIL code, exit 2,
redirected output and success behavior are unchanged.

This is the last approved fixture callsite, not proof of the deepest native
cause. The cache subprocess and production launcher still suppress their own
internal causes. Raw output, mixed log/JSON output, hard exits, malformed records
or tracebacks outside the approved boundary can yield only fixed failure or
unavailable origin, with exit/capture evidence retained. No cache or launcher
logic was changed to infer a cause or introduce a fallback.

## Scope and pins

Implementation: `run_fixture.py`, and the approved final-handler helper in
`run_pinned_image.py`. Tests: the focused new diagnostics module, three inner
origin/redaction controls in the existing image fixture tests, and one extra
inner-byte drift case in final-source tests.

`provenance.json` changes only the two changed fixture SHA-256 values.
`scripts/lifecycle/qwen38.py` changes only that provenance file's PROFILE_HASHES
constant. Native source, image, runtime, launcher, model and template pins remain
unchanged. No control/catalog/Storage/Manager/backend/installer/guard changes.

The combined 128 KiB CLI capture limit, command deadlines, CLI drain deadline,
container create/start/inspect/stop/remove commands, ownership checks, isolation,
resources, native success checks, authentication/cache/device/source gates and
receipt provenance predicates are preserved. No retry was added.

## Verification

Run this exact narrow source suite from the working tree, an immutable archive
of the final committed tree, and an archive of the bundle-imported final head:

```sh
python3 -B -m unittest \
  tests.lifecycle.test_qwen38_fixture_lifetime \
  tests.lifecycle.test_qwen38_fixture_diagnostics \
  tests.lifecycle.test_qwen38_image_fixture.Qwen38ImageFixtureTests.test_failure_output_never_relays_synthetic_sentinel \
  tests.lifecycle.test_qwen38_image_fixture.Qwen38ImageFixtureTests.test_origin_selects_concrete_fixture_callsite_after_opaque_cache_failure \
  tests.lifecycle.test_qwen38_image_fixture.Qwen38ImageFixtureTests.test_unknown_exception_class_and_deep_traceback_cannot_disclose \
  tests.lifecycle.test_qwen38_image_fixture.Qwen38ImageFixtureTests.test_repository_hash_binding_matches_source_worker_bytes \
  tests.lifecycle.test_qwen38.AuthEvidence.test_receipt_schema_and_source_fixture_checks_agree \
  tests.lifecycle.test_qwen38_final_source -q
```

Working-tree result: **48 tests PASS**. Independent source review found no
remaining must-fix issue after the post-attach inspection correction. AST
comparisons confirm the command builder, source/runtime/native acceptance,
receipt publication and inner execution functions match the reviewed base.

These use fake Docker state and bounded local Python CLI collaborators only.
Coverage includes synthetic secret/raw stdout/stderr redaction, concrete origin,
malicious/invalid/truncated/overflow metadata, timeout/cancellation/CLI failures,
native-versus-CLI exit, exact-owned stopped/quiescent removal, retained ID on
cleanup failure, no unrelated deletion, no receipt/second context on failure,
and rejection of diagnostics in an otherwise plausible PASS receipt.

Happy provenance and altered outer/inner/support/provenance bytes are checked
without pin overrides. Exact final commit/tree, bundle SHA-256, test counts,
committed/bundle results and author/committer verification are recorded in
`../Q38VD-handoff.md` after final packaging to avoid embedding a self-referential
commit identity here. `git diff --check` and a quiet grep-based secret scan cover
the complete submitted diff, including newly added files. No push is performed.

## Warnings and next action

The source/mock checks establish diagnostic behavior and preserve fail-closed
source gates; they do not establish installed-image/native acceptance. Root
should review this exact commit and diagnostic contract before independently
authorizing any actual fixture retry. All real execution remains outside this
task; VM guard identities were not consumed or executed.
