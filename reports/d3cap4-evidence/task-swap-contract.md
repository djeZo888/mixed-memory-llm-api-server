# D3CAP4 task-local swap seam

Frozen `swap-contract.md` consumed. No production source or D3MON changes.
Schema 2 snapshots require integer `cgroup_swap_current_bytes` in bytes, exactly
zero. Exact owned Docker PID is freshly derived from Docker, with stable ID,
image, start timestamp, start ticks and membership before and after each sample.
Only `/system.slice/docker-ID.scope` or `/docker/ID` with the full owned 64-byte
lowercase hex ID is accepted. Anchored no-follow opens below the protected
whole-root cgroup2 mount `/sys/fs/cgroup`; memory controller and PID membership
are mandatory. Missing, malformed, moved, unprotected or symlinked state refuses.
Unexpected actual host form is reported to coordinator; no broadened fallback.
Read timestamps/raw value and path/inode identity are separate evidence fields.

Every cheap and full boundary requires VmSwap 0, cgroup swap 0, MemAvailable
at least 67,108,864 KiB, GPU free at least 16 GiB each, unchanged owned identity
and storage, and no OOM/runtime/CUDA/storage/kernel errors. Full idle boundaries
also require measured smaps Swap 0, with fresh cheap proof before/after PSS.
Fresh host swap counters/deltas and used KiB remain diagnostic; OOM delta and
counter validity/monotonicity remain gates. No counter reset or host swap change.

Loading uses target 1 Hz, a shared remaining 10-second deadline and freshness
ceiling; above 2 seconds is slow sampling. Tiny request retains its existing
2-second cheap duration/gap/freshness bound and 600-second request deadline.
PSS runs only at accepted idle boundaries. Native Manager owns readiness.
One unchanged allocation and one conditional tiny request; no retry or fallback.

Offline checks: `python3 -B ../verify-swap.py`. The checks cover canonical paths,
identity changes, anchored zero/nonzero reads, missing controllers/files,
symlinks, membership, strict integer fields, full Swap zero and host-only movement.
