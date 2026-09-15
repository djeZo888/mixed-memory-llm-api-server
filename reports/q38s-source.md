# Q38S bounded Qwen3.8 source adapter

2026-09-15 · Mac-Worker2 · session `01a0a280-009e-79d1-8520-f45a738f6a49`.
Base `2def0df81f4195659de380444f05c903c14aeb03`;
branch `milestone/q38s-qwen38-adapter`.

**PASS — bounded source implementation and local tests.**
**NOT_TESTED — actual image, model acquisition/load, live inference, client
continuation, occupied context and throughput.** Final L1/Manager integration is
explicitly deferred to coordinator handoff after L1 freeze.

## Delivered scope

- Separate `scripts/lifecycle/qwen38.py` and
  `scripts/runtime/sglang38_file_auth.py`; existing Manager/runtime_io/CoderNext
  0.5.14 sources remain unchanged.
- Model `qwen38-27b-fp8`, runtime `sglang-qwen38-0.5.19`, native deployment variants
  `qwen38-27b-128k` / `qwen38-27b-256k`. Served alias remains `qwen3.8-27b` at
  localhost port30004; TP1/GPU0, one request, explicit bounded cache/graph/prefill
  settings and no-thinking client preset.
- Lossless normalized immutable acquisition inventory and public OCI/source
  provenance. Both variants share exactly 81 artifacts/66 weights,
  30,890,049,597 bytes total / 30,866,866,928 weight bytes. No weight was acquired.
- Separate runnable native actual-image sentinel fixture, its pinned source/hash
  manifest, small pinned template and dedicated source tests. Actual execution is
  reserved for worker1 before any real key/model.
- [Runtime and acceptance contract](../docs/qwen38-runtime.md) and
  [generic I1c acquisition mapping](q38s-i1c-mapping.md).

Incoming Revision2 was consumed: simple model/deployment IDs replace initial
dotted suggestions; runtime version dots already pass existing ID rules. No
discovery-regex change is required. The requested `docs/orchestration/status.md`
was absent; `docs/orchestration/2026-09-15-status.md`, F1S source/handoff, Q38R
report/immutable manifest and taskroot Q38S/L1 plans were read instead/as applicable.
Historical installation STOP text was not treated as an approval blocker for this
explicit source task. No installation/live action was attempted.

## Exact source and image identity

Model revision: `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a`.
SGLang source: `0bcd822377da7b5718e674eaf9c870d349424dd1`.
OCI run reference:
`lmsysorg/sglang@sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`.
Expected Docker config-image ID:
`sha256:e6238090791a938ab86dd21a9a6394192dad15237e815df557cf83524d54b813`.
Public manifest/config byte hashing established that distinction, Linux/amd64
platform, source label and exact inherited environment. It did not inspect layers
or prove installed runtime contents. [Public provenance](q38s-provenance.json).

Q38R source manifest SHA256:
`3df6f2a0a46a33b2b48f62609235ff209e50403d679bd8ee120b941445a87ed0`.
New normalized acquisition manifest SHA256:
`726012378a40f648a104230d3f5ed5d6bc505cbd09b32918fc29aa81c0f075f2`.
Every original artifact row roundtrips. `git_blob_sha1` denotes an actual Git
payload hash only; the 67 LFS pointer identities are retained separately as
`lfs_pointer_git_blob_sha1`. Publisher weight hashes remain metadata, not acquired
byte checks. Unknown, missing, duplicate or altered metadata/receipts fail closed.

## Authentication and continuation findings

Pinned 0.5.19 prepares raw ServerArgs separately from resolution. The launcher
checks both before key read and keeps both key fields empty in raw/resolved
records, worker serialization, logs and `/server_info`. Native middleware is
installed on the retained app; warmup is bounded and authenticated. WebSockets
are denied. Native `/health*`, `/metrics*` and OPTIONS exemptions are documented,
ordinary routes require authentication, and admin-force routes stay denied.
Exact argv/environment checks prohibit unreviewed modes/plugins and keep caches
under `/cache`; HOME is unchanged.

The source registers `qwen3_coder` structured tools and `qwen3` reasoning. The
explicit fast request is `reasoning_effort:none` with
`chat_template_kwargs.enable_thinking:false`. The server default alone can be
overridden by a client's xhigh/low effort. A1 remains unchanged; actual request
preset and tool-result continuation require independent live verification.
Thinking replay support, if later needed, is an explicitly bounded separate A1
followup. Source registration and synthetic template/parser tests are not live
continuation proof.

## Verification executed on this source worker

| Check | Result / boundary |
| --- | --- |
| New Q38 tests | **81 PASS**: 34 adapter, 30 launcher, 17 fixture controls |
| Complete lifecycle suite | **282 PASS**, including all existing lifecycle tests |
| Independent artifact/provenance checks | **PASS**, exact 81-row normalization, counts/totals, public OCI hashes, source hashes and flag/cache agreement |
| Launcher and both fixture CLI `--help` | **PASS**, no native import, image or key required |
| New JSON parsing | **PASS** |
| Independent source review | **PASS** after malformed inspect-list checks and LFS pointer-hash correction |
| Actual-image fixture | **NOT_TESTED**; shipped callable and protected receipt contract only |
| L1 final integrated mounted filesystem / Manager switch | **NOT_TESTED**, coordinator-owned seam |
| Runtime pull / weights / VM mutation / live model | **NOT_PERFORMED / NOT_TESTED** |

Reproduction commands from this checkout:

```sh
python3 -m unittest tests.lifecycle.test_qwen38 tests.lifecycle.test_qwen38_image_fixture tests.lifecycle.test_sglang38_file_auth -q
python3 -m unittest discover -s tests/lifecycle -p 'test_*.py' -q
python3 scripts/runtime/sglang38_file_auth.py --help
python3 tests/lifecycle/sglang38_fixture/run_fixture.py --help
python3 tests/lifecycle/sglang38_fixture/run_pinned_image.py --help
git diff --check
```

Tests use explicit synthetic bindings/receipts/native-ASGI collaborators on macOS;
they cannot attest Linux mount behavior, Docker/native dependency imports or GPU
inference. The shipped actual-image fixture imports actual pinned source and app
setup, stubs engine/model work and captures Uvicorn. Native serving lifespan stays
NOT_TESTED even after that auth fixture passes. No fake production PASS receipt or
real instance was created.

## Warnings, interfaces and next action

1. Coordinator must wire the exact new backend into Manager validation, commands,
   completion/evidence, launcher mount, image environment and reuse checks under
   the same canonical L1 lease. It must create by digest reference and inspect the
   distinct config-image ID. All target preflight precedes a backend switch. The
   adapter consumes final L1 path/verify/validate_path/read_json; it does not mint a
   lease, register mounts, write persistent state or perform a switch.
2. I1c's generic registry/downloader needs safe leading-dot and zero-byte artifact
   support. It must seal the generic acquisition receipt into the exact protected
   lifecycle receipt after verifying all computed hashes. No artifacts are dropped,
   unknown hashes invented, or per-model installer paths hardcoded.
3. Worker1 runs the exact-image fixture before a real key/model. After GLM priority,
   actual load/generation, generic tool loop and OpenCode read/edit/requested-test
   tasks require independent final tests. Then run occupied-context validation
   near each native cap with at least8192 tokens reserved and actual tokenizer
   counts/allocation/TTFT/prefill/decode/latency. A short prompt at256K or memory
   arithmetic supports no throughput or quality claim.

Publication gates and exact commit/bundle/author/committer/remote results are
recorded outside the checkout in taskroot `final.md`. Scope is all-new Q38 files;
no main push, global install, Docker pull, model download, live service or VM action.
