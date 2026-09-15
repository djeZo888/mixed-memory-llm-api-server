# D3T — GLM N76/native-context source and bounded probes

2026-09-15 · Mac-Worker1 · base `6cffccb` · branch
`milestone/d3t-native-context-source`.

**Source preparation and focused CPU/native accounting verification: PASS.**
**N76 load, native1048576 load, generation, occupied-context correctness, cache
reuse and performance: NOT_TESTED.** No installer source/test, VM build, model
reload, GPU allocation, profiler, deployment instance, service or key mutation.
No push. Final roster GLM5.3 + Qwen3.8; D3T owns GLM only.

## Delivered source

- `scripts/d3t/profiles.py`: exact immutable NOT_TESTED source generation from
  pinned current model/runtime/all-CPU32K profile bytes. Produces only N7632K,
  N76 native1048576, and separately reviewed all-CPU native fallback proposals.
  Runtime/image remain unbound until reviewed measured D3P/D3PD build. No active
  configs or instances changed; existing all-CPU32K rollback is byte-for-byte intact.
- `scripts/lifecycle/manager.py`: only reserved llama validation and launch bodies.
  N76 is accepted only for this GLM at32768/1048576; dual/bool/other placement
  values refuse. Old all-CPU context bounds remain; selected native branch needs
  retained1,1 split/ngl999 and a non-D1 runtime/measured image match. Imports,
  Q38/SGLang dispatch, control/U1 and installer code are unchanged.
- `scripts/d3t/probe.py`: concrete private worker phase CLI. `prepare` token-fits
  a deterministic append-only corpus with actual native endpoints in a detached
  worker; `start` detaches exactly one bounded generation request only in the
  later live task. `status` reconnects to checkpoints without dispatch. No retry,
  reload, fallback, tunnel creation or arbitrary PID kill. Cooperative cancel
  closes only the owned socket; ambiguous server completion requires root
  reconciliation and later stages remain pending.
- `scripts/d3t/accounting.py`: actual native `/props`, `/apply-template`,
  `/tokenize` adapter; exact wire/token/render hashes, prefix comparison,
  installed A1 stream/nonstream parsing and one real local A1 read_file(calc.py).
- `scripts/d3t/guards.py`: concrete existing-VM SSH observation, bounded1Hz
  resource samples and exact `D3T_NATIVE_V1` diagnostic consumer. No external
  receipt/observer/authorization framework.
- `scripts/d3t/README.md`: exact later-owner phases, caps, privacy, interpretation
  and verification commands. `tests/d3t/` exercises shipped helpers.

## Coordination and ownership

The early task-root probe contract was published before implementation.
Revision2 confirmed Q38B nonoverlap; the exact Manager diff was published
**before editing** in [the seam plan](d3t-evidence/manager-seam-plan.diff).
Revision3 expressly authorized bounded read-only SSH/native non-generation
inspection on the unchanged32K container. Revision4 replaced the initial
receipt-oriented design with direct task-specific adapters. Revisions5–6 approved the end delimiter and
native accounting and the one-function startup diagnostic plan and assigned the
producer to D3PD. D3T only implements its consumer. Current
[probe contract](d3t-evidence/probe-contract.md) and
[diagnostic consumer ACK](d3t-evidence/diagnostic-consumer-ack.md) record the boundary.

## Native accounting proof

[Detailed exact source/count/hash evidence](d3t-evidence/native-accounting.md)
records **13 tiny non-generation native route calls**, zero generation. The
installed same parser backs `/apply-template` and chat. Generation's tokenizer
semantics require explicit `add_special:true,parse_special:true`; tokenize's
implicit add_special default would undercount. Ordinary/tool/continuation fixtures
counted15/184/226 actual tokens; actual tool→continuation common prefix184.
The shipped adapter independently reproduced the ordinary15-token result.

The unchanged D1 container is
`bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`, PID149976,
image `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`.
Loaded template SHA256 `347dc716e1e8a9917eb124503836943107686ace6a3848d16bf23ae50964bb49`
differs from embedded SHA256 `15d2a7176beb599de0a59af8314b4869011e416cff7f65748b314940d3379b0e`
only because the installed lexer strips one trailing LF: the exact appended-LF
hash matches. The runner compares actual loaded hashes across phases.
No large tokenization request or model weight read occurred in this task.

## Runtime and resource evidence

[Bounded source/log inspection](d3t-evidence/native-diagnostic-plan.md) found one
32768 slot/112 threads, but old logs do not expose selected fusion/FA/workspace.
D3PD owns one GLM-only `sched_reserve()` diagnostic patch, combined with D3P's
reviewed strict-alias source in ONE later build. The
[producer contract](d3t-evidence/d3pd-diagnostic-contract.md) uses graph, compute,
cache and end records. Consumer invalidates a prior group when another begins,
requires end before acceptance, rejects malformed/order/duplicate required-device
records, and requires real allocations plus the selected native graph.
This proves reserved graph selection and allocated bytes, not profiled executed
kernels or instantaneous peaks. Unfused indexer64GiB score path is excluded.

A direct shipped telemetry collection passed current32K resource/context/argv
checks: root available5,219,123,200B, GPU free84,300,267,520/88,377,131,008B,
target Swap/VmSwap0; measured collection0.768s. These are observations of the
old baseline only. Historical host swap use was14,080KiB; one pswpout increment
occurred between separate early observations. The runner reports existing usage,
requires target swap0, carries admission counters across request start, and stops
on any new host swapping/OOM count. It never claims the host has never swapped.
Exact historical-D3 ext4 UUIDs are pinned in this task adapter; they are not
fresh-host defaults. Live owner still runs existing common guards before/after
lifecycle changes. No storage/registration/installer mutation occurred.

## Acceptance semantics prepared for the later owner

Matched32K comparison uses cold/warm256, tool/continuation512,600s/request and
2400s combined conservative client elapsed budget. Baseline/candidate cold,
warm and tool bodies match exactly; continuation comparison allows only native
call-ID differences. All exact body hashes and exposed counters are retained.
Because baseline and candidate use different D1/patched images, this compares
complete configurations; timing changes cannot be attributed solely to N76.

One native-capacity container remains bound through64K/128K/256K/512K/near1M
occupied stages, with2/4/8/12/24h elapsed caps, three requests each and8192
output/tool/continuation reserve. Actual input must be within256 tokens of each
initial ceiling. Corpus fitting is a bounded input-construction algorithm, not
a runtime sweep. Native counts come directly from real endpoints, never
imported receipts or estimates. Body/template/context/token identity checks precede use;
actual prompt usage must agree afterward. Real early/middle/late retrieval,
worker-local read and ID-preserving continuation must pass. Comparison uses
nonstream continuation; native stages use streamed continuation. Explicit
cached counts must establish useful stable-prefix reuse; missing counters remain
null, with no arithmetic reconstruction.

Private0700 run directories outside Git contain0600 bodies/raw/token/response
files and atomic fsynced checkpoints. Key values never appear on argv or in
logs/Git; A1 protected-file loading is reused. Parsed credential echoes are
redacted/refused before output persistence. Sampler shutdown owns only its own
SSH Popen. Existing root-coordinated exclusive client ownership remains required;
local run locks do not provide a global VM lease. A fresh CLI session reads status at<=60s intervals while preparation,
transfer and1Hz sampling are durable. Results distinguish configured capacity
from highest proven functional occupied window and label sampled extrema honestly.

## Checks and next action

Final exact test count, source/diff/secret/attribution and bundle checks are
recorded below after the final-source verification pass. Source-only status is
not native acceptance. Next: root reviews this source and D3PD's combined patch,
then separately authorizes ONE measured image build/profile binding and the
bounded live32K/native trial. The live owner selects the highest proven functional
context and reconciles/rolls back through the lifecycle owner; D3T stops here.

### Final source verification

- `python3 -B -W error::ResourceWarning -m unittest discover -s tests/d3t -p 'test_*.py' -v`: **PASS,48 tests** on macOS/Python3.14.7. Includes actual loopback HTTP JSON/SSE/byte caps/socket cancellation; no VM generation. Accounting12, telemetry14, driver12, profiles/Manager10.
- Shipped native accounting: **PASS**,13 tiny non-generation routes, exact15/184/226-token results; native generation/load **NOT_TESTED**.
- Shipped telemetry: **PASS**,3 bounded read-only samples in one SSH process,0.996221/1.004223s gaps and0.754–0.758s collection times, exact same runtime; normal sampler close exit0. This is bounded1Hz evidence only. Final observed root5,219,065,856B; same GPU free values; target swap0; pswpin19045/pswpout35822/oom0 unchanged within these3samples. Counter changes between earlier separate observations remain explicitly reported above.
- One preliminary clock-freshness check refused a sample24ms ahead of worker clock. Measured minor skew is now bounded to250ms future tolerance; age>2s and gaps>2s still refuse, with focused tests.
- Both CLIs `--help`, Python3.10 grammar compatibility parse, immutable profile generation, `git diff --check`, staged whitespace and local grep-based secret scan: checked during final handoff; exact results in `../handoff.md`.
- No broader/installer tests, Linux deployment test or inference test were run. Correct source attribution and incremental bundle are independently verified in handoff.
