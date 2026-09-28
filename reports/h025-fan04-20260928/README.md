# FAN04 source checkpoint

Native worker session 01a0e99d-2317-7c43-b6f4-b54b0bdc7f3e.
Start 2026-09-28 20:03:15 UTC; hard checkpoint 20:07 UTC.
Base 36092fd1f0db8aec59d064d59a926bf329bd6463.
Candidate source SHA256 029652d9567fb9db8fe927db0544fc1a04b12dc97755f03f6cccea642ea778c2.
Unit remains 04f861f9c59caee51b6fc4f1e48b58cd5516c5705afd1dd230a1d5b788114a3b.

Target-only version2 invariant, explicit legacy migration refusal, unique
PWMNum3/source identity checks, fresh pre-PUT own-duty check, prior status duty
check on restart, full pre/post snapshot receipts, bounded non-target audit.
Fixed payload, transport pin, credentials, unit and ambiguous PUT recovery stay.
The saved 19:59 snapshot supplies the fixture; reconstructing its six prior
CHA_FAN1 fields proves exact configuration edits are allowed without attribution.

Focused module: 62 PASS in 0.029s, worker-local macOS, Linux boot-id read stubbed
only inside fixtures. Initial run had one fixture aliasing assertion failure;
copying the fixture before FakeBMC mutation corrected it. No network/BMC/VM,
model, deployment, or GitHub calls. No broad repo tests. Read-only delegate
review identified uniqueness/CAS/pending safeguards; implementation and tests
were executed by this native worker. Source reviewGO remains required.

Migration is an executable reviewed-plan candidate in
scripts/thermal/H025-FAN04-MIGRATION.md, NOT EXECUTED or live-qualified.
It archives v1 baseline/latch/status/mismatch and pending/uncertain receipts,
requires root-pinned current state digests plus exact original baseline and
historical own40 proof, fresh read-only target40 equality, held flock and CAS,
atomic version2 baseline replacement, with latch clear last. Interrupted
migration requires review. Multi-file update is not a single transaction.

Historical original failures and genuine FAN02 lifecycle PASS remain intact.
Live current state, actual70C crossing and four-model overlap NOT_TESTED here.
