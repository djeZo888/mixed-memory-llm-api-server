# Activated, settled and window released

**API ready and idle; broker admission restored.** Worker1 released the sole
deployment/inference window to root and root-authorized Worker2 at
**2026-09-23 14:22:36 UTC**. No subsequent host action. This report was packaged
locally afterward. Last VM/harness observations were at 14:20:19 UTC.

Executed the exact reviewed transaction commit `56bf2c7` and helper SHA256
`432bf4ea600299966569dd77d1fd7c01863bdb6a42b6ed2bccce6ccddbb5ffa2` once.
Only app.py, protocol.py and the manifest changed. All seven installed source
hashes match reviewed `9de9ecf` / `f6e69d`. The approved manifest SHA256 is
`9c001640638833950fca3a60363f64e93c71b6b5f0113da792eec0256d99e8b3`.
Exact installed bytes: [qualification.json](qualification.json).

Six original generation records remain unchanged. Accepted edits are exactly
one reference at 1024x1024, one reference at 1536x864, and two references at
1024x1024. Full HD editing remains excluded: C03 visually passed but its measured
4.387464% reserve failed the 5% floor. [Final matrix](FINAL-PROFILE-MATRIX.json).
No interpolated profile or forecast was promoted to qualification.

The canonical lease was released before the sole API start at 14:19:02 UTC.
Its existing recovery owner reset the image backend and completed exactly one
fixed generation warmup: seed 42, 1024x1024, n=1, 40 steps, CFG 1, CPU RNG.
Warm HTTP 200 took 24.305537 s; ready/idle was observed at 14:20:08 UTC.
No extra image request, capacity rerun, startup retry, text restart or harness
restart/build occurred. No rollback was needed.

| Identity | Before | After |
|---|---|---|
| Image container | `ca750f6dca24…` | `4c00e0e2fd10…` |
| Image container init PID | 146684 | 252575 |
| Image model PID | 147055 | 252930 |
| Text Qwen GPU0 container PID/context | 53058 / 480000 | Unchanged |
| Text Qwen GPU1 container PID/context | 32207 / 480000 | Unchanged |
| Text GPU model PIDs | 53583 / 32839 | Unchanged |
| Harness PID / engine | 49895 / `11e764b2f308…` | Unchanged |

Full identities and text settings hashes are in the [live receipt](LIVE-READY-RECEIPT.json).
Both text container IDs, start times, settings, contexts and cgroup event counters
matched before/after. Image PID/container replacement is intentional.

The startup sampler captured 280 image GPU samples and 56 host samples.
Minimum sampled free image GPU reserve was **20.198794%**; host available reserve
was **97.288450%**. Maximum GPU sample interval was 0.200780 s; the host/cgroup
maximum gap was 1.000804 s. Host samples covered 14:19:10.212473–14:20:05.213344 UTC,
ending about 0.745 s before warmup completion; GPU sampling continued through
completion and the final snapshot followed. The receipt's maximum sample interval
field refers to GPU sampling. All devices passed current reserve checks; other GPUs
were checked before/after, not continuously. These are sampled observations,
not an instantaneous peak guarantee.

Actual global swap counters were pswpin 308 / pswpout 5323 before and after the
startup operation: deltas 0/0. The sampled load/warm interval also had deltas 0/0.
New image cgroup swap was 0 in 55 available samples; its first pre-creation sample
was unavailable. Final image/q0/q1 swap.current values were 0/0/155086848 bytes.
The q1 value is retained historical 148 MiB, not new image regression. q1's existing
memory.events max 441 remained unchanged. Old/new image cgroup counters were not
subtracted across identities. Exact current cgroup values are retained in the receipt.

Authenticated capabilities matched all nine exact profiles, pins and geometry.
API ready=true, admitting=true, busy=false; unauthenticated readiness returned 401.
Protected key bytes and loaded root:root 0440 credential matched. API unit,
recovery helper and runtime configuration identities were preserved. Registered
storage/root guards passed before/after and the canonical lease was released.
Published `http://10.156.100.60:30006` returned authenticated HTTP 200 from ai-harness;
its listener remained bound to the existing private interface. Native 30007 remained
loopback-only. PNG/b64_json opaque capability metadata matched. Live public
synchronous response/seed acceptance belongs to Worker2; no extra POST was sent.

Existing harness reconciliation moved the image lane from quarantined to idle.
No queued/active image jobs, active engine runs or running engine container were
observed. Stored table contents were unchanged except the image lane; protected
configuration/proxy identities and the existing search sidecar were preserved.
No chat, data or proxy-secret mutation was performed.

Private predecessor bytes/metadata remain at
`/data/services/h003-image-api-activate-20260923/rollback`; stopped-only restoration
is available through the unchanged reviewed helper. It does not recreate the old
image PID or authorize another warmup. [Protected raw hashes](LIVE-PROTECTED-EVIDENCE.json)
bind local commands, receipts and telemetry; native warmup PNG/evidence remains
outside Git at the recorded VM path. No push or main merge.

Original SIGTERM classification remains ASGI-cleanup-unproven. Original seed 42
edit failure remains preserved; fresh seeds are the accepted orchestration
workaround, not intrinsic model repair. C02 retains creative/non-pixel-exact limits.
The [window release](WINDOW-RELEASE.json) binds the immutable live-ready receipt.
