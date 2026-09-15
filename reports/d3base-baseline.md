# D3BASE — unchanged D1 short baseline

## Outcome: STOP at first cold-cache check

One authorized cold request completed; the shipped probe rejected it because the backend reported **50 cached tokens**, while the cold baseline requires exactly **0**. Native accounting and response usage agree at **1,370 input tokens**, all three retrieval checks passed, and the response ended with `finish_reason=stop`. This is a cold-cache qualification failure. It does not establish a model failure or a completed matched comparison.

No warm, streamed-tool or nonstream-continuation request ran. No retry, candidate binding, native/occupancy phase or model switch occurred. The durable checkpoint remains `PENDING_RECONCILIATION / cold_cache_NOT_TESTED`; `highest_proven_window=null` and `native_configured_capacity=null`. Baseline PASS is absent.

Operational completion is reconciled: the native container recorded slot release/stop-processing at **2026-09-15T03:54:24.963157913Z**, the complete response was parsed, native API established socket rows were zero, and owned workers/samplers/SSH children were quiescent. The request lease was released at **2026-09-15T03:58:45.033307+00:00**. The checkpoint's cache qualification remains unresolved; no state file was edited to manufacture success.

## Exact source and unchanged host

- Worker: `mac-worker1.local`, ordinary `agent` account. All client execution occurred on Worker1. ai-vm access used SSH alias `ai-vm` for read-only identity, protected-key transfer, native accounting and telemetry.
- Source: integration `1e65e17534ae6be3a23ec54bda800ad64fcee7d8`, containing D3T `ab881aa` and D3TR `155078c`. Source review confirmed the exact old D1 image is admitted at32K and exempted from patched native graph diagnostics. No source edit, installation or general test suite was performed.
- Container: `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`.
- Image: `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`.
- PID149976; started `2026-09-15T00:48:45.235739944Z`; alias `glm-5.3`; actual context32768; one slot; all-CPU MoE;112 threads; native `127.0.0.1:30002`.
- Canonical D3 guards and installed registered guard/dependency hashes and protected ancestry passed before/after. Both ext4 UUIDs matched registration: `/data` `8daf56f1-5649-4163-9d87-919c2d271875`, `/data/models-large` `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`. Registered guard was authoritative; no fallback or override.
- Root free preflight5,208,993,792 bytes; final telemetry5,208,915,968 bytes. **Warning:** below6GiB; remained above the4GiB STOP threshold. Guards passed and no VM report files were written by this task.
- State/instance/registration/control files remained byte-, inode-, mode-, owner- and timestamp-identical. Desired running, observed ready, boot manual; control inactive/disabled. Native key root0600 metadata unchanged; the preserved local key matched remote exact bytes in subprocess memory after execution. No key hash/value was published.
- Installer STOPPED. No runtime flags, cache controls, profile, container lifecycle, registry, mount, network or firewall mutation occurred. Only normal shipped inference could affect cache.

## Actual request evidence

| Field | Measured value |
| --- | --- |
| Dispatch UTC | 2026-09-15T03:52:10.149903+00:00 |
| Request deadline UTC | 2026-09-15T04:02:09.163336+00:00 |
| Settings | glm-5.3; low reasoning; temperature0; max_tokens256; nonstream |
| Native / response prompt tokens | 1370 / 1370 |
| Cached tokens | 50 from usage.prompt_tokens_details.cached_tokens; cold required0 |
| Evaluated prompt tokens / time | 1320 / 22135.537ms |
| Completion / decode tokens | 64 / 64 |
| Decode time | 112294.399ms |
| Total response tokens | 1434 |
| Worker elapsed | 137.055960s; includes worker setup and sampled completion observation |
| Derived backend prompt rate | 59.632617 tokens/s =1320/(22135.537/1000) |
| Derived backend decode rate | 0.569930 tokens/s =64/(112294.399/1000) |
| TTFT / previous token prefix | null / null |
| Body SHA256 | 6682c1aaae6491aaa900da3297c05e17a63bc35adbceaef310bc8ded47b1f89d |
| Native token IDs SHA256 | 469dd72637c5825cf9cd3b936e7c7033ab0d99ed1dfb14ca94ce4db92bbe455c |
| Native rendered prompt SHA256 | 9bcde19e00224e1f7d5892196e079ea3c4951f7c99760f52337f06a216742d5d |
| Raw response SHA256 | 6291a2bb8814c37018862ec0a580c0c078a7921e896d2db6519cacf1e1cca445 |

Rates use exposed counters only. These tiny outputs support no sustained-throughput claim. No missing count was inferred by subtraction. The shipped `generation_seconds_32k` remains0 because it accumulates successful results only; actual failed-request elapsed is137.055960s, not zero. The request respected its600s cap and the baseline2400s stage cap. Only one generation was attempted.

The112 retained telemetry rows all passed. Maximum observed sample interval1.512857s. Sampled minima: GPU0 free84,300,267,520 bytes; GPU1 free88,377,131,008 bytes; MemAvailable469,281,404KiB. Sampled maxima: RSS433,538,784KiB; PSS433,538,780KiB; process Swap/VmSwap0/0. Host historical swap usage is separately retained in admission; pswpin/pswpout/oom_kill stayed unchanged since admission, and checked error counts remained zero. These are sampled values, not instantaneous peaks.

## Ownership and checkpoint sequence

Root's coordination input granted sole generation ownership from launch; it was reread before bind/preparation/dispatch. Initial `prepare` returned transient `PREPARATION_UNKNOWN` before its detached child acquired request.lock; advancement paused, then shipped `status` showed the original child completed PREPARED. Frozen bytes/counts and free request.lock were checked. `start` similarly returned transient `IN_FLIGHT_UNKNOWN`; the original owned worker PID31442 was observed, and subsequent shipped status was IN_FLIGHT. Neither apparent launch interval was retried. Status was monitored within60s while in flight. The first durable blocking result stopped all advancement.

Shipped PASS/failure publication can precede final cleanup. Release therefore used the free request lock, absence of owned preparation/request/sampler children, complete response and native slot-release evidence, zero native API connections, and then exact owned-tunnel cleanup. Only tunnel PID31379 was exited via its own ControlPath; its PID and port listener were independently absent afterward. No arbitrary PID or shared tunnel was signaled.

D3B2 build and its one enumeration were already completed at launch according to root's handoff; before/after GPU memory delta0 is sampled evidence only. Q38VR2's independent noGPU/no-generation fixture had failed early and was packaging. Their exact execution timestamps were not provided in this task and remain null in evidence; no inference concurrency was authorized or observed through the sole lease. Any later old-D1 versus patched-N76 comparison concerns complete configurations and cannot isolate expert-placement effects.

## Preserved continuation boundary

Private trial: `/Users/agent/CodexProjects/llm-orchestration/tasks/D3BASE-20260915/trial` (0700).
Checkpoint: `/Users/agent/CodexProjects/llm-orchestration/tasks/D3BASE-20260915/trial/run` (0700).
Key reference: `/Users/agent/CodexProjects/llm-orchestration/tasks/D3BASE-20260915/trial/api-key` (0600).
Frozen bodies, token IDs, settings, parsed/raw result and sample bytes are private; public evidence contains pointers/hashes and safe metadata only. Warm/tool/continuation files do not exist because those steps were not prepared.

Endpoint frozen in config: `http://127.0.0.1:54597/v1`; its original tunnel PID31379 has been cleaned up. For a separately authorized continuation, verify port54597 is free and recreate a new owned SSH local forward `127.0.0.1:54597:127.0.0.1:30002` using a new isolated ControlPath, `ControlPersist=no`, `ExitOnForwardFailure=yes`, BatchMode and bounded connection settings. Record its new PID. Keep the existing protected key and endpoint configuration; do not regenerate the key or hijack a listener.

**Next required action:** root reviews the cold-cache failure and defines a reviewed resolution. There is no shipped reset/reconcile command. `bind candidate`, `prepare` and `start` cannot advance this stopped checkpoint, and changing its state or clearing cache is not authorized. A baseline PASS is required before candidate binding. Preserve this failed evidence and its exact frozen inputs while determining the separately authorized continuation; do not blindly retry or bind the completed D3B2 image. Once a qualifying baseline exists under a reviewed resolution, the shipped candidate contract requires exact cold/warm/tool bodies and continuation equality after only native tool-call-ID normalization. No model switch is performed by this task.

## Verification and artifacts

PASS: source ancestry/hashes; exact baseline admission; canonical and registered guards before/after; actual native template/token accounting; native/usage agreement; retrieval checks;112 sampled safety checks; unchanged host/state/key verification; completion/quiescence reconciliation; owned tunnel cleanup. **STOP:** cold cache50 versus required0. All later requests and phases remain NOT_TESTED.

No general tests were run; validation was the authorized live probe plus read-only source, accounting, storage, identity and evidence checks. Source hashes are in [source.json](d3base-evidence/source.json). Safe counters/settings/resources are in [summary.json](d3base-evidence/summary.json); immutable private artifact pointers/hashes are in [private-artifact-pointers.json](d3base-evidence/private-artifact-pointers.json). See [baseline status](d3base-evidence/baseline-status.md), [storage/state checks](d3base-evidence/storage-state-checks.json), [first result](d3base-evidence/first-result.json), [final telemetry](d3base-evidence/final-telemetry.json), and [lease release](d3base-evidence/lease-release.md).

Publication checks, commit identity and bundle verification are recorded in the external task handoff. Commit scope is sanitized reports/evidence only. No push.
