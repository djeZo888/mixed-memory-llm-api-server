# H019 reviewed candidate deployment and continuation

This is a prepared procedure, **not a deployment receipt**. No live source,
service, selection or model change was made by REPAIR01. Execute only after
root GO on the exact candidate. Root coordinates worker2's normal Sova pause;
worker1 never operates ai-harness. Existing automation stays paused.

## Package and installation

`deployment-files.json` lists every destination, repository source and raw
SHA-256. `client-closure.json` binds current owner/manifest, control and node
policy copies, both clients, dispatch and all historical dependencies. Rebuild
locally with `python3 scripts/h019/build_package.py` only if reviewed source
changes, then refresh CANDIDATE and root review. Historical H018 files are not
modified. The unchanged policy is
`cf5581289148f419f7056165e244ade8d696542cbb24c045b7d3533f873c46d1`.

Use existing `MountedStorageGuard`/`AnchoredRoot` to stage the package beneath
`/data/build/H019-20260928/package` (root owned, no group/world writes). Preserve
relative repository paths, including `deployment-files.json`. The external
`H019-DEPLOYMENT.tar` contains only required source files and that manifest;
it contains no credentials. Validate registered `/data` and `/data/models-large`
UUIDs and exact paths before transfer; do not extract into root-disk scratch or
hold the lifecycle lease across transfer. No model files are transferred.

After that guarded staging, the exact next deployment command is:

```sh
ssh ai-vm 'sudo -n /usr/bin/python3 -I -B /data/build/H019-20260928/package/scripts/h019/deploy.py'
```

The script first checks currently installed H018 source pins, settled MiMo,
GLM selection generation11, and active control/node processes. It backs up all
changed target bytes/modes plus existing owner state, selection, guard and proxy
state to root-only `/data/build/H019-20260928/BACKUP.json`, mode0400. Historical
failure receipts and retained models/runtime are untouched. Backups include
ABSENT markers for new files. A partial install is a failure requiring review;
there is no automatic retry or model rollback.

Normal `llm-node.service` and `llm-control.service` stop/start is required because
their Python processes hold imported policy modules. Service stop/restart occurs
outside the canonical lease. Source writes use the existing validated lease and
leave `/run/llmctl/lifecycle.lock` inode unchanged. Heavy lifecycle scans run
outside that short critical section. One daemon-reload loads the two new static
client units; production model/service/slice definitions are unchanged.

The observed MiMo/prep import is control-api's `lifecycle/hardware_policy.py`;
node imports its own node-api copy. There is no third shared-policy directory.
Image's oneshot owner imports the separate pinned release
`/data/services/releases/h005-qwen0-mount-order-fix-20260925`, whose policy SHA is
`ecd956b312543a6d21a74ed2cede4ce1e39ae34c02bdcf36ba502b71eebe8d74`.
That owner is not the periodic proof producer. Keep its release/config and native
resident unchanged; no image restart. Keep both Qwens unchanged. The old
`control-api.manifest.json` is a historical release provenance record and has no
hardware-policy entry; retain it. The H019 deployment receipt and MiMo manifest
supply the current changed-source closure.

## Mandatory measurement before a model load

Immediately after deployment, execute the read-only45-second observer:

```sh
ssh ai-vm 'sudo -n /usr/bin/python3 -I -B /data/build/H019-20260928/observe.py' > POSTDEPLOY-OBSERVATION.json
```

Review every proof sample for same current boot, age within unchanged15seconds,
no positive faults, and every observed lock interval/holder. Record the maximum
observed busy duration and proof age. Sampling is100ms; short holds can be missed
and edge intervals are censored. Do not represent this as an exact-duration trace.
Do not load if proof freshness or the existing five-second guard budget remains
unproven. Do not widen either bound. On contention retain this observer output:
`holder_capture` contains PID, comm, cgroup, matching FD target and `/proc/PID/fdinfo`
including actual FLOCK identity. Capture `/proc/locks` and that holder's FD info
immediately at the new failure; the historical holder cannot be reconstructed.

REPAIR01 baseline: canonical device26/inode1838; nodePID3309508; maximum observed
continuous busy1.878s; maximum observed proof age10,022ms. This was measured
**before** the fix. It is not live qualification of the candidate.

## Ordinary GLM release and independent MiMo start, next bounded session

After root review of the postdeploy evidence and worker2's current quiet receipt:

1. Preserve the current selected generation and exact GLM container ID/PID/start
   and cgroup. REPAIR01 observed container
   `2b5e5e386f70678cefebbfcb66cfdab568e9b3744abfb366f03a66ea7fdb03ab`, PID3099917,
   start`2026-09-28T01:14:13.228759037Z`. Validate using its unchanged owner's
   `validate_container`, protected config/state and actual runtime identity.
2. Without an outer lifecycle lease, run normal
   `systemctl stop llm-frontier-flash.service`. The existing owner obtains its
   own canonical lease. An uncertain timeout is not permission to retry.
3. Prove the exact old native PID and cgroup released, exact container stopped,
   no frontier compute process and no competing request/proxy. Record source
   pins and physical evidence. Preserve histories/receipts and the stopped GLM
   container; no model download/hash/build/tuning work.
4. Run candidate owner source_preflight outside the canonical lease. Check the
   existing Qwen/Ada guards, host15% reserve and frontier7% free reserve,85C or
   lower hardware bound. Under the existing canonical lease, check previous
   MiMo settlement, actual source and selection, memory policy and fresh same-
   boot sample. Call `latch(..., lease=lease, evidence=sample['hardware_validation'],
   deadline=cycle+5)`; do not add a second sample. Write selected_frontier MiMo,
   new manifest digest and generation12 using the protected owner writer.
5. Release the parent lease, then normal `systemctl start llm-frontier-mimo.service`.
   Its supervisor runs independently. Verify new launch/invocation/native identity,
   LOADING and dedicated704GiB/zero-swap parent with zero owned swap/OOM, then
   exit the paid CLI. Do not wait through the model load. No GLM rollback at end.

The loader/runtime/checkpoint remain unchanged:8decode,64batch,F16KV,950000usable,
GOMP_SPINCOUNT=0, all-node interleave. A real resource fault still stops affected
work safely and leaves MiMo selected but unavailable.

## Current clients after actual readiness

Client units and all source files are installed before any load. No active
authority is fabricated during deployment. After actual readiness, prepare the
short authority from the currently running generation, then dispatch once:

```sh
ssh ai-vm 'sudo -n /usr/bin/python3 -I -B /data/build/H019-20260928/prepare_authority.py short'
ssh ai-vm 'sudo -n /usr/bin/python3 -I -B /data/build/H019-20260928/dispatch.py short'
```

Inspect actual CLIENT/ALLOCATION/FINAL17-QUALIFICATION receipts. Short must prove
all17 offered schemas, a real allowlisted read, actual tool result continuation,
usage and complete owned HTTP/SSE drain/native settlement. Worker2 then performs
genuine Sova Qwen-parent/MiMo-child/tool-result/Qwen-verification acceptance.

Create a protected acceptance JSON requiring `final_native17` and `production`,
with optional real `sova` PASS; each names actual receipt path/rawSHA/status_field/expected_value(PASS or
PASSED). Native uses `FINAL17-QUALIFICATION.json`, production uses `ALLOCATION.json`.
The optional Sova receipt is supplied after actual acceptance, never invented.
Absent Sova acceptance is recorded separately as PENDING_NOT_TESTED_APP_PAUSED.
Sova remains paused and does not block the native benchmark.
Then:

```sh
ssh ai-vm 'sudo -n /usr/bin/python3 -I -B /data/build/H019-20260928/prepare_authority.py final --acceptance /data/build/H019-20260928/acceptance.json'
ssh ai-vm 'sudo -n /usr/bin/python3 -I -B /data/build/H019-20260928/dispatch.py final'
```

Both held-lease dispatches use the same actual fresh sample and borrowed lease.
No lease spans systemd start or inference. New final runs exactly one request,
948,975 actual counted input plus1024output and one native-slot reserve within
950000. No64K prerequisite or hidden queued-after64K stage remains. Admission
closes at2026-09-28T04:10:29Z, rechecked immediately before dispatch. Request receipt
retains actual BODY-SENT/request-sent timestamps separately from preparation. The existing systemd8h total cap is retained;
client cap starts with job preparation and therefore never exceeds8h after
actual dispatch. No ambiguous request replay; complete HTTP/SSE drain and native
settlement remain mandatory. Verify actual BODY-SENT/running native request and
close the paid session; no multi-hour polling. Keep automation paused.
