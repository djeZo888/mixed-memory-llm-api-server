# H019 REPAIR01 — worker1 candidate, not deployed

Native Mac-worker1 session `01a0e5cb-c39b-7e72-a9b1-a52a13b0fe82`, isolated
base`89cc931b69e39a4a2acd95270d3156396d0053d0`. Scope: implementation and focused
tests, source/client preparation and read-only ai-vm diagnostics. No ai-harness
access, subagents, shared deployment, service change or model start/stop.

The owner now accepts a borrowed canonical lease, validates capability provenance,
process/scope/inode and freshness boundaries, and never reacquires a supplied
lease. Startup supplies the already measured same-boot GPU sample and borrowed
lease, with explicit five-second total deadline. No additional GPU sample, TTL
change, positive-fault clearing or storage bypass was introduced. Fresh proof
still avoids acquisition when no lease was supplied. Periodic hardware-policy
write fix remains unchanged at
`cf5581289148f419f7056165e244ade8d696542cbb24c045b7d3533f873c46d1`.

Current H019 short/native17 and direct950K clients, static systemd units,
source-closure builder, authority binder and one-shot dispatcher are in
`scripts/h019`. Held-lease dispatch supplies both the actual fresh same-boot
sample and borrowed lease. Short uses the retained authentic17-tool/read/result
continuation fixture. Final reuses unchanged historical framed transport and
reader, but owns current authority/admission, exactly one948975-input/1024-output
plan and a single QUEUED stage. No64K rung or QUEUED_AFTER_64K_PASS state remains
in the new runner. Both current admission clocks close no later than
2026-09-28T04:10:29Z; token counting and final transmission admission use that
clock separately from execution end. Existing8h total systemd/client cap stays
in force, never exceeding8h from actual dispatch. Actual request-sent timestamps
are separate from preparation timestamps. Historical source and receipts remain
unchanged. Complete HTTP/SSE drain, native settlement and ambiguous-request
ownership are preserved; no automatic replay or GLM rollback.

## Live evidence: baseline only

At02:20:53Z, a45-second read-only observer completed at100ms lock sampling.
Canonical device26/inode1838 was unchanged throughout. The directly captured
holder was nodePID3309508, FD13, cgroup`/system.slice/llm-node.service`, an actual
FLOCK on`/run/llmctl/lifecycle.lock`. Maximum observed continuous busy interval
was1.877966s; maximum observed proof age10,022.206ms. Shorter holds can be missed;
edge intervals are censored. This is **predeploy baseline**, not a post-fix result.
Raw samples and holder fdinfo remain private in the task directory.

Read-only source inventory exactly matched the historical H018 manifest. Both
control and node policy copies still hash to`c779739a...`; actual MiMo/prep import
resolves to control-api's copy. Image imports an independent pinned release
policy`ecd956b3...`; no image restart/deployment is needed. The old external
control-api manifest is historical release provenance and has no hardware-policy
entry. New H019 target/manifest/receipt closure records the changed bytes.

Observed selection remains GLM generation11, prior MiMo SETTLED. Resident GLM
container`2b5e5e386f70`, Qwen0`ae049b4eb723`, Qwen1`3280b5d1cb3f` and
image`15031b926938` were running with their retained identities. GPU temperatures
were35–39C. No production state changed in this session. MiMo native/Sova
acceptance and final950K inference remain **not performed**.

## Validation and next step

- `PYTHONPATH=scripts python3 -m unittest tests.test_mimo_owner scripts.h019.test_clients -v`:49PASS. Includes real fixture canonical leases, invalid/expired/wrong-scope borrowing, same-sample startup/dispatch, current deadline/direct stage, complete one-request path and ambiguous ownership. Offline fixtures only.
- `PYTHONPATH=scripts python3 -m unittest discover -s scripts/h018/last950k -p 'test*.py' -v`:31PASS. Existing real HTTP parser/framing, local-busy, full-drain and settlement regression fixtures; no VM inference.
- Existing59 focused periodic-write policy passes reused; no policy edit or repeat broad suite. `py_compile`, changed-source credential-pattern scan, `git diff --check` and exact target/manifest/client hash-closure checks passed.

[`DEPLOYMENT.md`](../../scripts/h019/DEPLOYMENT.md) supplies backups, exact install
command, required normal control/node restart, postdeploy45-second observation,
contention-holder capture and ordinary exact GLM-release/MiMo-start continuation.
Deployment/authority/staging scripts are prepared source candidates, not executed
live. Root/worker2 exact review and subsequent root GO are still required by the
session's explicit scope. Then measure postdeploy proof freshness/lock behavior
before any expensive load. Stage current clients first. Actual native17 and Sova
acceptance precede the single independent950K dispatch. Leave MiMo selected at
the foreground deadline, stop safely only on actual fault, and keep automation
paused. No main merge or GitHub push was performed here.
