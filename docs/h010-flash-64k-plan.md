# H010 — Flash 64K occupancy and CPU-only feasibility

Authorized by the user's 27 September request. Mac-Orchestrator coordinates and
reviews; implementation and live work use fresh remote Codex CLI sessions on
Mac-Worker1 and Mac-Worker2 in isolated copies of `6772a77`.

Target execution window: 26 September 23:16:45–27 September 01:16:45 UTC.
Stop new experiments early enough to restore services and publish results.

## Worker1: 64K benchmark and memory estimate

- Preserve official FP8 weights, pinned KT/SGLang runtime, FP8 cache, 64 expert
  threads across eight guest NUMA nodes, current GPU UUIDs and ECC policy.
- Keep production context/cache configured to 480000 and output ceiling65536.
  Only the task request uses a256-token output budget, with current reasoning
  settings. Reserve at least7% GPU memory and15% host available RAM.
- Coordinate an idle Flash lane with Worker2. Do not interrupt real user work.
- Warm with a representative, varied technical prompt of4K–16K tokens, then
  measure a fresh prompt of65536 actual native tokens. Include verifiable facts
  near the beginning, middle and end and a bounded technical check. Retain the
  first-use/warm timing separately; do not extrapolate repetitive-text results.
- Warm request cap20minutes, primary measured request cap70minutes. No automatic
  retry or larger request. Preserve partial evidence on timeout or failure.
- Drain streaming responses promptly. Keep heavyweight guards at request
  boundaries and telemetry separate; no synchronous per-fragment fsync/receipts.
- Record native tokens, TTFT, prompt/decode timing boundaries, elapsed duration,
  semantic result, loaded/warm/peak memory, GPU allocation/reservation where
  available, process RSS, cgroup anonymous/file cache, host availability/swap,
  CPU utilization and temperature. Retain raw traces outside Git.
- Distinguish occupancy from configured capacity: the existing480K cache may
  already be allocated. Use pinned cache/state formulas and measured workspace
  behavior to estimate capacity, not a straight-line fit through4K/16K/64K VRAM.
  Bound estimates by the published model limit and runtime support, with reserves
  and explicit uncertainty. No production context increase in this task.

## Worker2: CPU-only feasibility and Sova readiness

- Inspect the actual installed runtime and primary upstream sources for a true
  CPU-only path. Zero GPU experts is not CPU-only if attention or other kernels
  remain CUDA dependent. Limit initial investigation to20minutes.
- A CPU-only comparison is conditional on a supported, small configuration
  change using existing weights. Report any precision/runtime change as a
  confound. Do not rewrite kernels, download another model, convert hundreds of
  GiB of weights or start a new serving-stack migration within this task.
- If a minor supported path exists, give root the concrete change and expected
  memory/runtime before coordinating an isolated bounded trial with Worker1.
  Otherwise report the specific blocker and approximate scope needed.
- Inspect current Sova/Flash availability and preserve history/credentials.
  Close application admission temporarily only after confirming no active user
  work, coordinate the benchmark lane, then restore the existing qualified
  application. The H009 native delegation test is already passed; do not repeat it.

## Final verification and delivery

Keep the two Qwens, Flash and image model resident. If time permits after the
uncontended measurement, perform one short, separately labelled four-instance
overlap smoke using bounded text requests and one small image. Record actual
request overlap and each result; do not call readiness alone simultaneous
execution or mix this smoke into the primary speed result.

Publish compact settings, benchmark code, machine-readable results, CPU-only
feasibility evidence and the reviewed report in the existing feature branch/PR.
Update current status without erasing prior failures. Finish with Sova ready,
or report precisely any unresolved failure. No installer, driver, Proxmox,
unrequested model or general routing redesign.
