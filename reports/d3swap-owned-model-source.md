# D3SWAP — owned-model swap acceptance source

Mac-Worker2, 2026-09-15. Branch `milestone/d3swap-owned-model`.
Base `355253af91dde26085b999b0f5fa4c3416fecd95`.
Source commit `15b7ab7f814f5822e103af8021564b8f6b377742`.
Session `01a0a38c-bffe-7ea1-a681-55d5be1d0e7e`.
Author and committer: CodexAIagent <133749519+djeZo888@users.noreply.github.com>.

**Focused source/synthetic verification: PASS. Actual new monitor: NOT_TESTED.**
The latest task-root incoming instruction drains this existing source task and
stops at local handoff. No later trial or new phase is started; feature publication
is pending that stop. Installer and Q38NEXT sources remain outside this task.

## Prospective correction and evidence boundary

Root supplied D3CAP3's stop at host delta1page swap-in/98pages swap-out while
model VmSwap0 and MemAvailable764GiB. CAP2's approximately12MiB shutdown swap
was likewise unattributed. Those historical failures remain unchanged. These
host-wide observations do not establish model causation or accept this monitor.

Both cheap/full schema2 snapshots now require fresh process VmSwap0, owned
Docker cgroup-v2 memory.swap.current0 and MemAvailable>=67,108,864KiB (64GiB).
Full checkpoints retain measured Swap0. The only added JSON field is
`cgroup_swap_current_bytes`: an integer byte count, required and equal to0.
Missing/null/bool/float/string/malformed/nonzero values fail closed. Historical
rows missing this evidence cannot be silently upgraded.

The path is derived only from the exact inspected owned PID's single unified
`0::` entry, using the exact full Docker container ID. Accepted host shapes are
`/system.slice/docker-<id>.scope` and `/docker/<id>`. Root, unrelated, nested,
escaped, missing and symlink paths refuse; there is no caller override.
Protected directory handles anchor traversal below `/sys/fs/cgroup`; whole-root
cgroup2 mount and open-file mount IDs, directory device/inode identity, root
ownership and protected modes are checked. The exact PID must occur in
`cgroup.procs` before/after each byte-counter read. Cgroup identity is checked
at both ends of collection and across samples; Docker/PID identity surrounds
collection. First nonzero cgroup evidence stops before a full memory scan.

Global pswpin/pswpout values and deltas remain actual fresh integer page
telemetry, and host_swap_used_kib remains current SwapTotal-SwapFree in KiB.
Host-only usage/activity may change without an independent abort. Invalid,
inconsistent or regressing telemetry still refuses. OOM delta0 and unchanged
absolute OOM remain mandatory, including the admission-to-request comparison.

## Preserved behavior

Request target1Hz, cheap duration/freshness/gap<=2s, full checkpoint bounds,
GPU>=16GiB/card, root>=4GiB, mount/GPU/runtime/container/native graph identities,
OOM/error/storage checks, accounting/retrieval/tool/cache limits, request/state
locks, deadlines, one dispatch and no automatic redispatch remain in force.
Worker1's separate CAP4 loading gap is not a request-phase cadence change.

Cheap collection performs zero smaps/PSS reads. Full admission and pre/post
checkpoints remain mandatory. Successful complete JSON/SSE response proof must
precede post PSS and PASS; unknown completion remains explicitly UNAVAILABLE,
with original operation evidence retained and no failure-cleanup full scan.
All existing source modes are preserved. No runtime/model/profile/thread,
host swap/sysctl, service, installation or ai-vm operation was performed.

## Focused verification and handoff

110 focused tests PASS on source, committed source and an isolated clone imported
from the complete source bundle, with ResourceWarning treated as errors. Tests
retain the D3MON/D3TC native-accounting, cache, retrieval/tool, deadline,
cancellation and real local OS-lock coverage. Added checks cover both owned
swap gates, exact64GiB boundary, truthful host drift through admission/cheap/post,
strong wrong/missing types, real-shaped cgroup parsing, anchored descriptor IO,
invalid mount/root/path/file identity, symlinks, PID/container mismatch,
membership races, and same-path inode/mount replacement within one sample.
Generated sampler helper definitions execute under controlled synthetic IO.
Temporary filesystem IO is real; Linux proc/cgroup/mount ownership and Docker
observations are synthetic. No live SSH/API/model/GPU test was run.

Independent source review found a same-path cgroup replacement race in the draft;
checks at both ends of collection fixed it, and the original reproducer now
refuses. A new driver assertion initially used the wrong existing raw-evidence
field name; its correction passed the focused suite. Neither event was a live
model operation. Python3.10 grammar, scope, whitespace, existing modes, staged
grep secret scan, exact author/committer and clean-tree checks passed.

Early `../swap-contract.md`, exact source commit, `../D3SWAP.bundle` and
`../source-ready.md` were published before this report formatting. Task-root
`focused-checks.py`, source/committed/imported test logs, original source bundle,
final bundle, session logs and final handoff retain reproducible evidence and
hashes. The initial import precheck ran in the source checkout; it is preserved
separately as `focused-import-precheck.txt`. The actual imported check ran in
`source-import/` and passed independently.

Next action is root review of the exact local artifact. New monitor sampling,
request cadence under load, occupied context, performance and live cgroup
compatibility remain **NOT_TESTED**. No occupied-window claim is advanced.
