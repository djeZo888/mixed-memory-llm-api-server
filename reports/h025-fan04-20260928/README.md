# FAN04 final result

PASS: target-only version2 correction, 62 focused fixtures, explicit migration,
and one live idle80-to-40 proof after exact root reviewGO. No GitHub push.

Native session01a0e99d-2317-7c43-b6f4-b54b0bdc7f3e started20:03:15UTC.
Source checkpoint20:07; source ready and tests passed before checkpoint;
commit followed at20:07 after missing local author identity was resolved using
the existing author. Root extended this native session through20:12.
Base36092fd1f0db8aec59d064d59a926bf329bd6463; source commit eb80c9a42f3115cf8d965a1aea7669de1fb535ae.
Source029652d9567fb9db8fe927db0544fc1a04b12dc97755f03f6cccea642ea778c2.
Unit04f861f9c59caee51b6fc4f1e48b58cd5516c5705afd1dd230a1d5b788114a3b unchanged.

The invariant now contains only global FanMode and the exact unique target
PWM4 row/source/last source, normalizing only our four duties. Fresh pre-PUT
readback checks own duty, and full pre/post snapshots plus a bounded32-row
non-target audit replace fixed private receipts. Exact40/80 payload, transport
pin, credentials, ambiguity guards and historical evidence remain. Existing
v1/unversioned state refuses baseline_migration_required. Source Option/Visible
remain pinned as explicitly directed by root; shared-catalog sensitivity remains.

Focused62 PASS worker-local macOS; inert Linux boot-id fixture read stubbed.
First run had one aliasing assertion failure in the new fixture; copying it
before FakeBMC mutation corrected that fixture. No broad repo tests. A read-only
delegate reviewed safeguards; all implementation/tests were this native worker.

Root INBOX conditional20:07 and exact20:09 GO authorized migration/deployment.
The documented procedure ran under existing Store lock and CAS, pinned original
raw baseline b9ceeb03..., prior healthy own40 receipt and canonical45069284...,
verified two fresh target40 snapshots against original-derived schema2, archived
all original state, replaced baseline atomically and cleared latch last. Migration
made ZERO PUTs. Manifest digests derive retained task input; absent entries use
digest(null), clarified before execution. Archive prefix:
/var/lib/sova-cha-fan3/migration-v1-. An interruption would require review;
multi-file replacement is not a single transaction.

New invariant ba1a1788472328c23053180eef4b29f4dcd9ffcd9c7c15d1ab9ecffe5e1b529c.
PID72409 started20:09:21.007316UTC. At20:09:40 independent target80/raw5040;
at20:09:59 target40 but tach still5040 immediately after transition. One settled
final proof20:10:26 confirmed40/raw3600, healthy status, GPU34C, source000/mode4.
Exactly two controller PUTs:80 then40; independent proof made ZERO PUTs.
Final deployed source/unit pins matched. See results.json and exact proof files.

CHA_FAN1 raw3720 in both high and settled low readings; units absent. User says
this stronger120mm fan cools BOTH motherboard-slot Blackwells: stockQwen GPU88058
and frontierGPU69ac. Its user-authorized settings were preserved. Prior6000+
figure is historical/user context, not the measured final value.

Original failure and genuine FAN02 lifecycle PASS are preserved. No new model
load, actual70C crossing, overlap, stop/restart test, or thermal sweep performed.
W2/root receive exact new source/invariant/PID and own overlap admission.
