# Q38VC — safe cache-child failure diagnostics

**PASS: bounded source checks. Native/actual-image/live gate: NOT_TESTED.**

Base `cb2e49c2bea670a3d72f9cce08f8c51c194b6c67`, including reviewed Q38VD.
Branch `milestone/q38vc-cache-diagnostics`. Installer work remains STOPPED.
No VM access, retry, build, download, live request, host setting change or
optional1M work occurred. Root reviews the final source before Worker1 uses it.

## Observed boundary and diagnostic contract

The supplied Q38VR result stopped first131072 at the existing cache-child
returncode/stderr/size gate in 0.667665 seconds. CLI/container exit 2 and exact
owned quiescent removal were recorded; no256K, model load or receipt followed.
The underlying cause was discarded. This patch does not infer or repair it.

The existing cache final handler still returns exit 1. Its one FAIL JSON record
now has exactly:

- `status`: `FAIL`.
- `code`: one of the 25 existing fixed `ProbeError` codes, or the fixed generic
  `q38b_cache_probe_failed`. Only an exact `ProbeError` with one exact string
  argument in the finite allowlist can supply a specific code.
- `failure_origin`: null, or exactly `filename`, `line`, `exception_class`.
  Filename is only `cache_probe.py`; line is an integer 1..100000 (not bool).
  Exception class comes from the finite exact-type list in `FAILURE_TYPES`,
  otherwise `OTHER`. A subclass borrowing an approved name remains unknown.

Origin selection walks at most 64 traceback links without formatting them,
reading source, locals, exception messages, causes or contexts. It selects the
last frame matching a frozen original local function code, module globals and
full executing filename; the generic `require` frame is excluded. Unapproved
frames cannot supply paths or names. Overflow discards structural detail.

The existing child gate remains unchanged: nonzero exit, nonempty stderr, or
stdout above 131072 bytes fails. Only a stderr-empty failure can carry the
optional diagnostic. A separate diagnostic parser admits one whole UTF-8 JSON
document of at most 2048 bytes, exact keys/types/enums, no duplicate keys or
nonfinite values. Unknown/malformed data is omitted, preserving the failure.

The inner final handler revalidates the optional record as `cache_failure` and
still emits `actual_image_fixture_failed`, existing safe origin and exit 2.
The outer existing 4096-byte structured parser revalidates this nested record
under `lifetime.attach_diagnostic.failure_metadata.cache_failure`; outer exit
remains 1. Existing metadata statuses and successful receipt schemas remain
unchanged. No raw logs, exception text, environment, versions, commands or
arbitrary filenames are emitted by these diagnostics.

## Exact changed files

- `tests/lifecycle/sglang38_fixture/cache_probe.py`: diagnostic helpers/enums and
  final handler only; cache operations and success validation unchanged.
- `tests/lifecycle/sglang38_fixture/run_pinned_image.py`: existing cache-module
  loader factored into a helper; failure-only propagation/revalidation.
- `tests/lifecycle/sglang38_fixture/run_fixture.py`: existing structured failure
  metadata parser only.
- `tests/lifecycle/test_qwen38_cache_diagnostics.py`: 11 targeted regressions.
- `tests/lifecycle/test_qwen38_final_source.py`: cache source-byte drift case.
- `tests/lifecycle/sglang38_fixture/provenance.json`: three fixture hashes only,
  refreshed after the executable source freeze.
- `scripts/lifecycle/qwen38.py`: provenance digest only, refreshed last.
- `reports/q38vc-cache-diagnostics.md`: this report.

AST comparison against the exact base confirms all other existing fixture
functions/classes are unchanged. Capture limits, commands, flags, resources,
lifetimes, native/auth/PASS assertions and exact-ID cleanup remain intact. Image,
model, upstream source, launcher and template identities remain unchanged;
OCI raw-manifest/config-image domains remain distinct. No circular hash pins.

## Verification and limits

Working-tree bounded suite: **108 tests PASS**, zero skips/failures:

```sh
python3 -B -m unittest \
  tests.lifecycle.test_qwen38_cache_diagnostics \
  tests.lifecycle.test_qwen38_cache_probe \
  tests.lifecycle.test_qwen38_image_fixture \
  tests.lifecycle.test_qwen38_native_wire \
  tests.lifecycle.test_qwen38_oci \
  tests.lifecycle.test_qwen38_fixture_diagnostics \
  tests.lifecycle.test_qwen38_fixture_lifetime \
  tests.lifecycle.test_qwen38_final_source \
  tests.lifecycle.test_qwen38.AuthEvidence.test_receipt_schema_and_source_fixture_checks_agree -q
```

The new tests execute actual serialization and propagation through cache main,
inner main/run_cache_probe and outer main/run/lifetime, replacing external
process/Docker I/O. They cover known/unknown/spoofed errors, hostile text/path/
class/code/extra fields, duplicate/deep/oversized JSON, strict types, original
nonzero/stderr/size gates, first-context stop, exact quiescent removal and no
receipt. The combined quote/backslash/brace credential-shaped fake sentinel is
absent raw and through repeated JSON escaping. Existing acceptance tests reject
diagnostic fields in otherwise plausible successful evidence.

Independent source review found no concrete issue. Whitespace, grep-based
secret, scope, identity, committed-source and imported-bundle checks are
recorded outside the repository in `../final.md` and adjacent check outputs.
After the final commit, run the existing verifier against that commit and the
bundle-imported head (without regenerating or overriding pins):

```sh
python3 -B tests/lifecycle/verify_qwen38_git_source.py --commit HEAD
```

Only the verifier's existing bounded checks are included; no installer suite or
all-repository suite was run. Source/mock PASS does not establish native cache
success, authentication acceptance, context capacity or live model readiness.
Next action: Root reviews the exact commit and full bundle. No VM retry is
authorized by this source report.
