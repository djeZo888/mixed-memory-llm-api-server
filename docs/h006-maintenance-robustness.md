# H006 narrow maintenance robustness — source candidate

This candidate is based on `d703a254033cacc227644be47cc2d1150ac908f4`.
It is source-only: root exact-source review and a fresh deployment/recovery GO
are still required. The separate topology plan `acee029` is not included.
The September 26 diagnosis establishes an unattended library-update/API-restart
shutdown chain, but **not the precise replacement-start refusal**. This change
cannot retrospectively identify it. No healthy-backend adoption is added.

## Exact maintenance deferral

[The four-entry override](../configs/needrestart/90-llm-managed-units.conf)
merges into `override_rc`, matching only `llm-control.service`,
`llm-node.service`, `llm-image-api.service`, and `llm-image-backend.service`.
Perl `\A`/`\z` anchors and escaped dots exclude suffixes, instances, sockets,
lookalikes and other services. Existing overrides remain intact. The override
does not alter restart mode, unattended security package installation, APT hooks,
Docker policy, kernel handling, automatic reboot policy or NVIDIA exclusions.

Read-only ai-vm facts on September 26 confirm Ubuntu needrestart
`3.6-7ubuntu4.5` and unattended-upgrades `2.9.1+nmu4ubuntu1`. The installed
`/usr/sbin/needrestart:263-274` selects automatic mode for the Ubuntu APT hook;
`:1088-1103` checks `override_rc` in the noninteractive/automatic service loop,
adds a zero-valued match to skipped services, and skips restart dispatch. The
following block reports those services as deferred. `/etc/needrestart/needrestart.conf`
loads sorted `conf.d/*.conf` snippets. This is **deferral with visibility**, not
`blacklist_rc` suppression. [Recorded versions, hashes and policy](../reports/h006-maintenance-source-20260926/host-facts.json)
bind this finding to the inspected installation; refresh it if needrestart changes.
No `needrestart`, APT, upgrade or package-maintenance command was executed on the VM.
This override controls needrestart selection; explicit maintainer-script or manual
service restarts remain outside it.

Deferral leaves already mapped libraries in resident processes unchanged even
when the on-disk package is patched. It is not immediate process remediation.
The canonical maintenance owner must review deferred units after each unattended
upgrade cycle, arrange an explicit guarded maintenance window within 24 hours
for ordinary library security updates, and prioritize urgent fixes according to
the advisory (sooner when required). Record completion or the reason and next
deadline for any delay; never leave deferral indefinite. Coordinate dispatch
holds and interruption authority before restarting the affected owner. Updating
container packages/runtime images remains a separately reviewed change; restarting
an unchanged pinned image does not patch its internal libraries.

Control service restarts use the existing typed canonical owner. Node observer
maintenance uses the existing root maintenance procedure under the same lease
and coordination holds (the node API does not offer a node-service target).
Image maintenance uses the single image-owner procedure below. Do not execute
needrestart's printed combined restart command or independently restart the native
backend. Preserve the current manual NVIDIA upgrade policy; this source does not
create another maintenance scheduler or owner.

## Attempt diagnostics and start admission

The existing image `service.py` creates a unique attempt before Runtime
construction for each start, recover or stop. Its terminal receipt includes
`action`, `phase`, `attempt_id`, `boot_id`, `invocation_id`, start/finish UTC,
status, enumerated `code` and optional terminal `settlement_code`. The helper's
sanitized environment does not carry a systemd invocation; in that case
`invocation_id` is null and the new `attempt_id` identifies that helper call.
Never substitute the stale native run ID for this attempt. `boot_id` can be null
only when its local read is unavailable; it is not invented.

Receipts are unique, exclusively created, fsynced files at registered
`logs/image-runtime-attempts/<attempt_id>.json` (currently
`/data/logs/image-runtime-attempts/`). The root-owned directory is created 0700;
files are 0600. The same protected registration, full mounted/ancestry guard and
root payload guard run before/after writes. No diagnostic write acquires a second
lifecycle lock: these immutable exclusive files do not replace shared state.
Existing registration identity and anchored descriptors remain authoritative.
No fallback file is written on missing storage, mount loss, unsafe ancestry or
capacity refusal. A partially written file is not a complete valid receipt.

Only explicit error constants or fixed fallback codes are emitted. No exception
text, command arguments/output, prompt, environment, credentials or traceback is
included. The small record is emitted before storage as `storage_status=pending`
and again as `verified` or `unavailable`, to stderr and authpriv syslog tagged
`llm-image-attempt`. The backend unit now uses `StandardError=journal`; stdout
stays null. Authpriv retains the safe helper record even though the API continues
to suppress raw sudo/helper subprocess streams. Journal transport/durability
must be verified during deployment; source tests do not prove it.

The first caught start/recover failure is retained before settlement can replace
it with a different exception. Pre-container constructor, lease, guard, hardware,
port and ownership failures reach the same terminal diagnostic. A successful/new
start moves only `failure_type`, `failure_code`, `native_failure`, and
`recovery_failure` out of current state into `historical_failure`, preserving
legacy values and their original run ID in one frozen snapshot. Later attempt
failures have separate receipts; they never merge into or relabel that snapshot. Existing
native evidence is not removed. The node image reader
(`scripts/control/node_observation.py:326`) derives status from exact ownership,
unit state and health, not those legacy errors; the API uses its existing health
contract. No frontend/status schema change is necessary.

SIGKILL, an import/bootstrap failure before the entry point, unavailable logging
transport, uninterruptible filesystem I/O or an outer deadline can still prevent
receipt completion. A journal-only `unavailable` result is not protected-storage
success. Diagnostics never authorize a retry or alter lifecycle settlement.

Only `start` waits up to two seconds for **entry** to the canonical lease. It
retries only `LeaseBusy`, never an unsafe lease error or an exception from the
yielded lifecycle body. Guards are refreshed under the admitted lease; existing
start hardware/latch/ownership checks then run. Stop and both recover admission
gates retain their immediate refusal semantics. The helper still releases its
lease before `systemctl restart` so the systemd child can acquire it. No accepted
mutation, request, warm generation or uncertain outcome is replayed. Existing
source and the closeout's observed transient collector contention justify this
preventive admission change; they do not prove the 06:00 failure subtype.

## Root deployment and recovery recipe — not executed

1. Review the exact source head and bundle in task `SOURCE-RESULT.json`. Refresh
   root's current deployment manifest, node/control/image identities, package
   versions, boot, source hashes, storage registration and all relevant operation
   journals. Check responsible-node hold/queue aggregates without history contents;
   arrange existing maintenance holds and explicit interruption authority. Refuse
   any nonterminal or uncertain operation; do not replay it. Record the two text
   Qwen container IDs, start times, image IDs, process identities, ready state and
   configured **480000** contexts. Check Ada UUID, hardware latches and absence of
   conflicting owner/job. No GPU reset, driver/ECC change or VM reboot.
2. Refresh the installed registered guard identity. The image owner currently
   imports `/data/services/releases/h005-qwen0-mount-order-fix-20260925/scripts/`.
   Its reviewed `common/registered-storage.py` SHA256 is
   `21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d`;
   `common/lifecycle_lease.py` is
   `483ba038c62a8b4633449cef9c0f9a6664c00276662498abc748b58c8be644e0`.
   Verify the **entire** protected release closure against the current manifest,
   not these two hashes alone. Run this installed registered-storage script with
   `--json`, then `--json --root-guard`, before and after staging or writes. There
   is no standalone root-disk-guard.sh in that installed release; do not substitute
   an old checkout. The diagnostic path additionally uses the same registered
   `Storage.root_payload_guard` and `RegisteredStorageBinding.mounted_guard` APIs.
   Registered data/model UUIDs and roots are in the facts record and must match
   protected `/etc/local-ai-server/storage.json` and fresh mount checks.
3. Prepare protected backups under registered backups of the exact current source,
   protected config, backend unit, and any existing same-named needrestart snippet;
   record hashes/owner/mode. Preserve state/native evidence and all models. Stage
   candidate bytes under a fresh protected registered service directory; do not
   modify the old immutable dependency release or any text source/config. Under
   `common.lifecycle_lease.acquire_lease(blocking=False)` from the verified installed
   release, recheck guards/identities and atomically publish only the following:

   | Candidate source | Installed target / required change |
   | --- | --- |
   | `scripts/image_runtime/service.py` | `/data/services/image21-runtime-20260923/source/service.py`, preserve root:ai 0644 |
   | `scripts/image_runtime/llm-image-backend.service` | `/etc/systemd/system/llm-image-backend.service`, root:root 0644 |
   | `configs/needrestart/90-llm-managed-units.conf` | `/etc/needrestart/conf.d/90-llm-managed-units.conf`, root:root 0644, protected nonsymlink ancestry |
   | Existing protected runtime config | `/data/services/image21-runtime-20260923/config.json`, root:ai 0600; update **only** `source_sha256["service.py"]` to the reviewed candidate hash |

   The four runtime source entries and complete release hash map remain mandatory.
   Other runtime/native/checkpoint/network/image/model values remain byte-identical.
   Update root's external delivery manifests to bind the new host source/unit/config
   and override hashes. No native overlay/image build or source-closure expansion.
   Re-read protected installed bytes and run `Runtime()` source/config validation
   with the matching installed dependencies; it performs no model start. Release
   the publishing lease before invoking a systemd job or canonical HTTP action.
4. Run `systemctl daemon-reload` only after source/config/units match, without
   restarting a service. Re-read backend `StandardError=journal` and `Restart=no`.
   Validate the snippet using Perl's actual config loader/selection semantics:
   all four targets must resolve to override zero, and lookalikes, sockets,
   private forwarding units, `polkit.service`, and `llmctl-boot.service` must not
   match the new expressions. Compare existing overrides and APT/NVIDIA config
   hashes to pre-change values. Do not use automatic-mode needrestart to test this.
   Record policy presence without claiming a pending-library scan is acceptance.
5. **After separate recovery/warm-up GO**, submit exactly one fresh canonical node
   action through the existing authenticated private channel:
   `POST /control/v1/node/actions`, with `schema_version=1`, `node_id="ai-vm"`,
   `action="service.restart"`, `service_id="image"`, a new idempotency key,
   freshly observed `expected_boot_id` and image `expected_generation`, and
   `allow_interrupt=true` only under the authorized interruption scope. Keep keys
   out of commands/output. Do not separately invoke the helper/backend start.
   The existing node owner dispatches the image API restart with `--no-block`,
   releases its lease, and the API invokes the fixed recover helper once. The
   helper resets only its exact owned image backend, releases its lease, and
   starts the backend unit; that unit performs its existing deterministic warm
   generation. This is model inference and requires the later GO.
6. Poll the returned operation URL; on unknown, timeout or failure retain that
   operation and collect the new attempt receipts/journal records. Do not replay,
   delete locks/latches, call recover again or invent success. A pre-admission
   409 is a refusal, not permission for an automatic second action. Root owns the
   next decision. For success, compare boot and both text identity/context records,
   confirm image API capabilities ready/admitting, native ownership/residency,
   absence of latches and complete protected start/recover receipts. Confirm
   current state no longer projects old error fields. Verify safe journal output
   is actually retained and files/parents remain protected. Only if separately
   authorized, issue **one** public image smoke at an already qualified size,
   retain the output and review it. No additional text inference or broad benchmark.

Rollback is a reviewed source/config rollback, not an automatic recovery. Under
fresh guard/identity/hold checks and the canonical lease, restore the matched
backed-up service.py, its exact config hash map and backend unit; restore the
previous snippet, or remove only this exact newly created snippet after verifying
its candidate hash. Restore external manifest bindings, daemon-reload, and verify
APT/NVIDIA configuration is unchanged. Retain every attempt/native receipt and
historical state entry; do not restore a stale container ID from a state backup.
A source rollback does not restore model readiness. Any additional image-owner
restart/warm-up requires fresh root direction; never restart either Qwen for this
rollback. Restoring the old override state also restores its known unattended
restart exposure, which root must assess.

## Local verification and limits

On mac-worker1 only:

```sh
python3 -B -m unittest discover -s tests/image_runtime -v
python3 -B -m unittest discover -s tests/lifecycle -p test_lease.py -v
```

The candidate passes 53 image-runtime tests (24 new maintenance tests) and 37
canonical-lease tests. These cover real local anchored private writes, symlink
and mode refusal, mount/guard loss, pre-container failures, adversarial exception
privacy, legacy/current error separation, bounded contention, no yielded-body
replay, refreshed guards, parent/child lock behavior and the actual Perl selection
loop with exact exclusions. Existing image source-closure, ownership, settlement
and fixed launch tests still pass. No installer suite, native/image build, GPU
request, service restart, VM reboot, deployment, push or merge was performed.
Source evidence does not prove live recovery or an installed maintenance policy.
