# H016 single production owner — source contract, deployment held

One unit: `llm-frontier-mimo.service`, one Python supervisor, one exact Docker
container and one private proxy child. No independent proxy unit, adoption,
overlap ACK, trial deadline, retry or inference-held lifecycle lease.

Protected registered base `/data/services/mimo-h016-20260927` contains
`manifest.json`, `selection.json`, `state.json`, `guard.json`, `proxy-state.json`, `source/`.
Manifest schema2 fixes owner H016-MIMO-PERSISTENT-20260927, alias
mimo-v2.6-pro-rl, reviewed context (initial131072), output65536, exact image
cdb6efd..., model revision ba4eabb..., runtime7ac59a6..., 13 verified shards,
MXFP4/BF16/F32 inventory, raw/effective template pins, exact source hashes,
launch argv and read-only numactl/libnuma pins. Manifest has no boot/PID:
those are exact observed state of each clean supervised launch.

Selection schema1: selected_frontier GLM or MiMo, monotonically incremented
`generation`, and canonical `manifest_sha256` for MiMo. Explicit GLM selection
is valid and required for rollback; no missing-file fallback. Parent selection
is authoritative. GLM drop-in gates its unchanged original owner/config.

State schema2: manifest/selection generation, current boot, supervisor unit /
PID / invocation, exact native container ID/name/image/PID/start ticks/StartedAt,
proxy child PID/start ticks/parent PID and active/quarantined disposition.
RUNNING only follows exact authenticated props/plain slots validation.
Guard schema2: same identities/selection, monotonic time, cheap mandatory GPU,
host/swap/cgroup observations, and real registered hardware latch proof.
Node uses manifest+state container authority, never a hardcoded trial name.

Guard sampling has a five-second total bound, including writes; no deep mapping
walk. Only exact frontier GPU presence, seven-percent reserve and min(85C, hardware
limits); unrelated card loss is not fatal. Fifteen-percent host reserve; explicit
reviewed memory.limit_bytes, qualified_peak_bytes and startup_cache_bytes with
fresh preflight validation; no implicit650/704GiB cap. No OOM or added swap.
Canonical lease is held only for create/start/stop and selection mutation.
Fatal guard, timeout or proxy death closes proxy, stops the exact owned native,
then proves PID/cgroup/GPU release. Unproven settlement remains held. Request
ambiguity persists until explicit review; no slot-idle or disconnect clearing.
ExecStopPost performs exact recovery settlement, never starts another owner.

Rollback is explicit after settlement and preserves GLM config/release/desired
state; it publishes GLM selection before invoking the original service. There
is no automatic thermal retry/rollback or hardware latch write/clear.

Source: scripts/runtime/mimo/{owner.py,private_proxy.py,launch.json,
llm-frontier-mimo.service,llm-frontier-flash-selection.conf}, node slice and
focused tests. Existing built6641 engine, production7143/9ef and history stay
unchanged. Final report records any unfinished integration gap; no live
qualification is implied. Parent root/W1 must review final source/pins before
any installation or deployment.

Final argv is manifest-bound. Reviewed no_host Boolean permits only optional
--no-host in addition to fixed R3 load-mode none and interleave0-7. Neither
variant is qualified here. Proxy disposition is written at request boundaries
and sampled by the owner, with no independent proxy unit/heartbeat daemon.

Final sample cadence5s; each whole sample bound5s. Native503 while LOADING
returns pending; only exact200 props/slots advances. Stop/NVML timeout writes
HELD with request_hold:true and no settlement proof; no automatic GLM start.
