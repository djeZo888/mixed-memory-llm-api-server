# H017 SOURCE-PREP01 — source ready; runtime held

Base **d09620402007046881606dfbdc74c9ee3fde09b2**, isolated branch
`worker2/h017-source-prep01`. Native session
`01a0e446-c537-7e72-ae62-7b3c9ff4ddae` started
2026-09-27T19:10:37.552010Z; unchanged hard cap19:35:37.552010Z.
User global window19:07:11–21:07:11Z supersedes historical H016 deadlines.
Root's same-task review confirms decimal950000 and20:50 hard settlement.
No subagents, live contacts, runtime probes, builds, downloads, dependency changes,
service actions, inference, installer work or push occurred. Original Sova is
UP per root/user handback; this worker did not reobserve or pause it.

## Owner review, frozen base only

[Native replay](NATIVE-READY-REPLAY.json) ran **actual `native_ready`**, changing
only `get()` to supply retained raw R9 HTTP status/value pairs. Both exact
DEPLOY17 failed and repaired manifests return True. Props/slot context1000000,
3866-byte template/hash, absent tool-template key, build/model identity and
modalities all satisfy the predicate. Slot processing=true makes this an identity
replay, not idle/current-production acceptance. No deterministic incompatibility
exists in this retained ready snapshot. No950000 or1000192 actual capacity is
inferred. Raw R9 and diagnostic files remain outside Git; only hashes/field
results are public. Reproduce with `python3 replay-native-ready.py PRIVATE_R9_JSON`
from this directory.

- `scripts/runtime/mimo/owner.py:610-612,666-671`: finally settlement can replace
  an earlier startup/guard/identity exception; CLI emits only the final error.
  Printed LeaseBusy does not identify the primary cause. Original live cause
  remains **UNKNOWN**, including the later corrected launch. A subsequently
  observed node lock holder does not identify the original holder.
- `owner.py:96-113,568-582`: current five-second whole mandatory sample uses
  MandatoryGuardTimeout and remains fatal. Socket readiness TimeoutError is now
  loading-tolerant. The historical first-owner socket-timeout defect is already
  reproduced in DEPLOY17/REPAIR-REGRESSION.json; that reproduction never proved
  the first live cause. No duplicate protocol or broad owner suite was run.
- `owner.py:236-244`: status writes no longer acquire the lifecycle lease;
  registered/anchored storage and root-disk checks remain. They can still fail
  or exhaust the five-second sample. Preserve primary phase/code before cleanup,
  separately preserve cleanup errors, and never let diagnostic failure skip stop.
- `owner.py:426-448,475-499`: stop_exact uses a nonblocking canonical lease;
  contention has no bounded wait. Exact container labels, manifest, launch,
  container ID/start time/PID ticks, cgroup and frontier GPU absence must remain
  mandatory. Do not hide identity refusal behind generic successful settlement,
  replace the lock inode, kill its holder, or reacquire a lease already held by
  the same operation. Use the established borrowable capability when nested.
- `owner.py:490-498,658-660`: any physical-stop failure sets sticky request_hold,
  even without a proxy. A repeated ExecStopPost settlement can also encounter
  contention after supervise settled. Successful reentry retains the sticky hold.
  Distinguish physical failure from real request ambiguity; retain historical
  reconciliation evidence and genuine active/quarantined uncertainty. Unit
  TimeoutStopSec45 must bound the whole cleanup; SIGTERM reentrance must not
  interrupt mandatory exact settlement. This is a recommendation, not a W2 fix.
- **Proxy-started race warning:** `owner.py:479-486` reads disposition before
  terminating the proxy. `active_requests=0` at that instant cannot prove no
  ambiguous request: admission may race before termination. Require final
  exact-generation/admission-closed proof; otherwise preserve uncertainty.
  A stale/nonmatching proxy receipt also cannot establish a clean disposition.

The first-launch diagnostic was captured after settlement: source preflight,
sample and latch passed, PID/cgroup/GPU were absent, no proxy started. Those
post-stop facts do not reconstruct the original sample. The later retained
readiness record has last guard18:04:40.386166Z, LeaseBusy18:04:45, then
ExecStopPost TimeoutExpired18:04:53 and HELD/no-proxy state. It does not retain
the hidden primary error. Evidence hashes are in [source proof](SOURCE-PROOF.json).
W1 exclusively owns owner/node changes; these files are unchanged here.

## Minimal support and prepared closure

The only product change adds **950000** to
`ai-harness/deploy/engine/configure-profile.mjs`'s exact managed migration list.
Its existing matrix fixture includes the sixth tuple. Prior profiles, custom
content refusals, arbitrary valid numeric selection range, Qwen default/coding,
MiMo frontier policy and GLM rollback remain unchanged. Both canonical registry
identities, engine pins, compiled payload and native source are unchanged.

The new H017 copies reuse Task18's driver/workflow. Capacity checks add950000;
profile pin is now1767aec74793b161b07feeee9e8dc97c3a4ffc9970c5c8f532bbf443b9f8ea1c.
Namespace is `/home/user/ai-harness-build/H017-SOURCE-PREP01-20260927`, release
suffix `-h017-prep01`, units `h017-prep01-app-*`. The same direct root manifest
and gate fields are retained; only its authorization marker is namespaced H017.
No new gate/schema/framework was added. No live GO manifest was created.

After actual W1 props/slots950000, reserve proof and protected receipt, prepare:

1. `stage-qualified-config.mjs`: use the existing protected receipt validator
   and root-reviewed digest to derive config. Historical R9 remains immutable
   1000000 provenance, occupiedTested16384; never relabel it as950000 qualified.
2. `assemble-final.py`: verify exact retained compile14 archive SHA
   0d34ca656248d8293ee4098ef1ba0202fc02353ac35a515870220e8fcc805d17 and all44
   payload mappings. Its accepted archive has53 regular files; the9 known extra
   files pass safe-member/archive checks and are never copied into the image.
3. One COPY layer over **46feffff8fe00e5993a8e0d35f5a7932f82ee43ef91d87759f568c3a6029dc1e**.
   Only image `opt/ai-harness/engine/configure-profile.mjs` and
   `opt/ai-harness/config/active-frontier.json` change. New files0644 and payload
   ancestors0755; inherited executable modes remain. No compiled/native/dependency
   rebuild. The retained final18 host release is copied to a new immutable path,
   overlaying only profile, active-frontier.json and mimo-candidate.json.
4. `build-and-stage.sh`/`verify-built.sh`/`verify-image.py` are **prepared, not
   executed**. Verify against Task18's accepted **final46** inventory SHA
   7846eb5f9befb44e55cc4c62cfe15e114bb21c7ef7f10a9cdb410491da2d9fcf, never the
   old6641 inventory. Compare every non-overlay entry and inherited executable
   mode, layer parent, native/patchset labels and full retained host closure.
   Proposed unit changes only point to the new release. Source and image/host
   closures must be recorded by the later build; no new image ID exists yet.
5. `activate-pair.sh` and `launch-app-acceptance.sh` stay held until root's direct
   coordinated GO and W1 current clean production readiness. Original Sova
   remains up until root coordinates its pause. No automatic retry or rollback.

Keep8decode/64batch/GOMP0/ordinary host with --no-host/F16/interleave0–7 on W1's
native side. W2 made no native launch or guard changes. Intended primary MiMo
requires actual Sova PASS before activation is accepted.

## Confirmed acceptance envelope

Hard stop20:49:30UTC, 30-second service stop grace inside hard settlement20:50UTC;
17min11s remain before global end21:07:11. Last theoretical admission20:34:30;
actual measured preflight must leave **720s work plus180s cleanup**. The second
preflight inside live.mjs is charged too; insufficient remaining work refuses
before inference. Work<=1200s, supervisor<=1380s, outer service cap<=1470s and
calendar stop cannot extend the fixed end. Five existing clock fixtures pass.

Linux systemd owns both preflights and the live client; no foreground CLI owns
HTTP. Exclusive dispatch intent, full streams, same-invocation readback,
Restart=no and no replay remain. The full17 exact schemas/tool hash and65536
request ceiling, Qwen parent→MiMo child→bash read/edit/check→native tool result
continuation→independent parent verification are retained byte-for-byte in
live/guards/prompts/check/edge. The historical H016_VERIFIED fixture token is
intentionally unchanged. **No claim that all17 tools executed** or strict:true
constrained generation passed. This app acceptance is NOT_RUN.

The final independent8h64K→near-max job belongs to W1 only after actual PASS;
then paid workers close and automation pauses. No completed benchmark repeats.

## Focused offline validation

- Five managed profile/migration tests PASS, including950000, prior profiles,
  custom refusals, general numeric range and preserved Qwen/history.
- Four existing driver/capacity/roster tests PASS; five clock tests PASS.
- Six-profile rollback fixture PASS (temporary local files only).
- [Package fixture](PACKAGE-CHECKS.json) PASS against the actual retained archive
  and accepted26025-entry final46 inventory. It verifies44 payload identities,
  exactly2 image/3 host outputs, permissions, inherited CLI executable and sums.
  It uses explicitly disabled/unqualified fixture config; no qualification or
  production config is synthesized. Reproduce with `python3 package-fixture.py
  RETAINED_ARCHIVE FINAL46_INVENTORY` from this directory.
- Six Python AST,11 Node syntax and4 bash syntax checks PASS. No full suites,
  runtime probes or builds. Raw private inputs and retained Task18 artifacts
  were read only and remain outside this commit.

See SOURCE-PROOF.json for exact affected source files, Task18 reuse hashes and
invariant source closures. Task-root STATUS/HANDOFF/RESULT.bundle bind the final
commit and exit handback; the wrapper records actual native exit after final.
