# D3SWAP early source contract — 2026-09-15

Base 355253af91dde26085b999b0f5fa4c3416fecd95; Worker2 source only.

Schema2 cheap AND full snapshots add exactly one required top-level field:
`"cgroup_swap_current_bytes": 0` — JSON integer, bytes, freshly read from the
owned Docker cgroup-v2 `memory.swap.current`. Bool/string/float/null/missing,
malformed file or any nonzero value refuses. No schema version change.

Derive only from the exact inspected owned model PID's `/proc/PID/cgroup`,
requiring one unified `0::/…` entry and the full exact Docker container ID.
Accepted canonical host paths: `/system.slice/docker-<64 lowercase hex ID>.scope`
or `/docker/<64 lowercase hex ID>`. No override, root `/`, relative/dot-dot,
empty segment, namespace escape, unrelated cgroup, symlink or arbitrary host path.
Anchor traversal below protected `/sys/fs/cgroup`; verify whole-root cgroup2
mount identity, root ownership/protected ancestry, and membership of the exact
owned PID. Bind cgroup identity, PID start ticks and exact inspected container
before/after sampling; missing/malformed/moved identity fails closed.

Required gates in both kinds: fresh process_kib.VmSwap == 0;
cgroup_swap_current_bytes == 0; host_kib.MemAvailable >= 67108864 KiB (64GiB).
Full checkpoints also retain measured process_kib.Swap == 0.
`vmstat.pswpin/pswpout` and `vmstat_delta.pswpin/pswpout` remain actual fresh
nonnegative integer PAGE counters/deltas; `host_swap_used_kib` remains actual
fresh KiB from SwapTotal-SwapFree. Host-only movement/usage is diagnostic and
has no inferred causal attribution or independent swap abort. Missing/invalid
telemetry still refuses. OOM checks and all other existing limits remain.

Cheap: fresh VmRSS/VmSwap; zero smaps/PSS reads. Full: existing admission/pre/post
Rss/Pss/Swap; post only after successful complete response, otherwise UNAVAILABLE.
Request target1Hz and existing <=2s cheap duration/freshness/gap remain unchanged.
CAP4 loading10s gaps belong to Worker1's separate run, not this request contract.
Source implementation/tests pending; actual new monitor NOT_TESTED.
