# H018 LATCH WRITE FIX06 — source-only handoff

Removed only the two recursive root-payload scans from `RegisteredLatchStore.write`
and its now-unneeded `try/finally`. All lease, registered path, mounted identity,
protected JSON, atomic write and recheck calls remain. Initialization still scans
at `hardware_policy.py:88,109`; all other tracked scripts are byte-unchanged.
No TTL, lifecycle/lease architecture, sticky fault, boot/proof/freshness, or
independent memory/swap/OOM/thermal guard changed.

Native ID/deadline: [EARLY.json](EARLY.json). Starting base: `639e72ff6d64bc5840d4201e871d191a8d8b827a`.
Reviewable implementation plus one new test: [SOURCE.patch](SOURCE.patch).
Test commands/results: [CHECKS.json](CHECKS.json). Exact guard chain, boundary
calls, causal limits and pin references: [FINDINGS.json](FINDINGS.json).

## Focused evidence

One new regression uses the real RegisteredLatchStore, HardwarePolicy, canonical
borrowed lease, role-aware registered binding, MountedStorageGuard and anchored
writer. Only local path/UID, Linux discovery/mountinfo and time are fixture seams;
spies invoke the real implementations. Four new GPU proofs cause four writes.
The original source fails only the final root-scan assertion: **8 != 0**. The
corrected source passes with **0 recursive scans**, preserving 12 lease checks
(policy plus pre/post store), 12 path checks (protected read plus write), four
mounted guards, four bounded reads, eight old/new state validations, four atomic
writes and their explicit rechecks. Files remain private, single-link and valid;
all guard/anchor descriptors close. This is a call-count regression, not latency
measurement or hardware acceptance.

**59 targeted tests passed; zero failures/errors/skips.** Existing tests cover
initialization full-scan refusal, missing/corrupt state, sticky faults, failed
persistence, boot/freshness, registry/mount/path/mode changes, private bounded
JSON, and invalid/stale/replaced canonical leases. No broad suite was run.
Legacy `test_hardware_policy.py:21` and `test_boot_hardware_readiness.py:34` still
unpack three GPU values from four; the former also expects the deliberately
removed periodic scan. These preexisting modules were not run or rewritten.

## Exact deployment consequences for the next window

Old shared source SHA-256: `c779739a1776ea919f491a60a34811639e2df934a94ea909053710e4864e7229`.
New shared source SHA-256: `cf5581289148f419f7056165e244ade8d696542cbb24c045b7d3533f873c46d1`.

The candidate manifest pins both installed control-api and node-api copies at
`scripts/h018/manifest.candidate.json:306,350`. LIVE04 `deploy.py:52` and
`start02.py:37` pin the actual imported module to the old hash. MiMo
`source_preflight` checks declared hashes (`owner.py:347-359`); preserve both
explicit entries in any fresh reviewed manifest. Control/node filename closures
already include this file; concurrent acceptance binds its hash within the
complete source map (`concurrent_profiles.py:222-249,282`). The image owner also
binds its release copy in protected `release_source_sha256`
(`image_runtime/service.py:43-51,318-331`); that copy needs matching reviewed
configuration if updated. A future deployment
needs explicit reviewed source-hash closure across affected installed/imported
copies and dependent receipts. **No old pin, manifest, receipt or evidence was
rewritten, and nothing was deployed.**

## Ownership and limits

User-supplied W1 evidence identifies the CURRENT 01:10:54 UTC holder as
`node_serve.py`, `llm-node.service`, PID 3309508, FD 7, lifecycle inode 1838,
device 00:1a. This task did not query that host. The 01:00:16 historical holder
remains **UNPROVEN**; neither its exact cause nor scan latency is established.
The source mechanism is eight recursive scans under a lease for four changed
proofs; removing these scans does not prove that every remaining check fits the
collector's two-second budget or eliminates every contention source.

Independent source review corroborated the guard chain and deployment pin
impacts; final focused diff review is recorded in CHECKS.json. All existing
staged application/history artifacts remain intact. No VM/harness contact,
build, deployment, model load, request, application acceptance, or LAST action.
Root/W1 own recovery. Wrapper records actual CLI exit; no paid waiting.
