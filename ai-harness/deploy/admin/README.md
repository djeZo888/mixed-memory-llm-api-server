# H005 local harness owner adapter — source only

`local_helper.py` is a Python standard-library root service with no TCP listener.
Its fixed private socket is `/run/ai-harness-admin/helper.sock`. It implements
the root-frozen H005 v1 routes and action envelope:

- `GET /control/v1/node/status`: cached partial status; no command dispatch,
  lifecycle reconciliation, history inspection or status-triggered observation.
- `POST /control/v1/node/actions`: strict typed body; durable asynchronous 202
  receipt, one operation capacity, exact repeated idempotency receipt even after
  target/boot changes; mismatched repeated key returns 409.
- `GET /control/v1/node/operations/{id}`: cached receipt; unfinished operations
  become `unknown` after helper restart and are never replayed.

The envelope is `schema_version:1`, `node_id:"ai-harness"`, `action`,
`service_id` for service actions, `idempotency_key`, `expected_boot_id`,
`expected_generation`, and boolean `allow_interrupt`. Callers cannot provide a
command, executable, unit, path, URL or GPU target. The status daemon relays this
server-side; browsers and task containers never connect to the helper directly.

Only registered `service.start` currently executes. `harness` maps to the
existing ordinary user's `ai-harness.service`; `search` maps to the existing
user's `ai-harness-searxng.service`; `status` maps to the independent system
`ai-harness-status.service`. The user manager remains the lifecycle owner.
User commands use fixed `runuser`/`env -i`/`systemctl` argument vectors with no
shell. No ai-vm contact, model lifecycle, GPU reset, installer or Proxmox action
exists here. The backend adapters on ai-vm remain Worker1-owned.

**Local stop/restart/reboot are deliberately unavailable (422)** until the
protected app admission interlock is integrated and reviewed. A typed internal
`freeze(request) -> release_callback` seam has an offline fixture, but the
production default rejects these actions. A freeze implementation must stop new
native/chat/gateway/image dispatch before mutation and keep the hold when owner
state is stopped or uncertain. Explicit interruption confirmation alone cannot
substitute for that integration. The fixed reboot command exists only behind
this closed guard; its return would record `unknown`, never completed reboot.
The helper must later confirm changed boot identity to establish completion.

Status observers independently poll each registered systemd service every five
seconds with two-second command deadlines and one outstanding probe per service.
Getters never wait for a probe. Failed probes preserve original observation age;
after 15 seconds cached state becomes stale. State, readiness and activity are
separate: an active systemd unit is not evidence of successful API readiness.
CPU/RAM/disk/network counters have separate passive Linux collectors. GPU
inventory, queues and work counts are explicitly unknown; no private application
database or user histories are read. Unknown work requires
explicit interruption confirmation even for start. The displayed affected
service is exact; affected work count is unknown. Reboot affects the whole host,
including nginx, every native task and these three registered services.

Generation is durable and increments for changed boot/systemd invocation/state,
not metric timestamps. Confirmation is checked against fresh observations at
admission and again before dispatch. Systemd's normal job serialization remains
authoritative; there is no new ai-vm lifecycle lease, custom systemd ownership
replacement, or atomic-drain claim. Local starts can race an out-of-band host
operator; stop/restart/reboot cannot be enabled until their ownership/interlock
semantics are reviewed. Unknown command outcomes are not retried automatically.

`resource_observer.py` reads only fixed `/proc/stat`, `/proc/meminfo`,
`/proc/pressure/memory`, `/proc/diskstats`, `/proc/net/dev`, root filesystem
capacity and root device identity. CPU percentage uses delta aggregate non-idle
ticks; 100% means all logical CPUs. Memory/swap/capacity use bytes, pressure
avg10 uses percent, and rate fields use bytes per second. Disk capacity and I/O
describe the root filesystem and its exact backing major/minor device; this is
not a registered AI storage validation or a sum of all volumes. Network rates
sum host non-loopback interfaces and can include virtual interface traffic.
First-sample rates, unavailable pressure sensors and unmapped root I/O counters
are null. Four independent fixed worker slots poll every five seconds. A resource
probe hung beyond two seconds is reported timeout and retains its slot until it
returns; no replacement thread is created. Cached age remains tied to original
successful evidence and is stale after 15 seconds. GET status and operation
receipts are memory-only and do not acquire the audit/operation writer lock.
HTTP uses four fixed workers with four total admitted connections, including
queued handlers. A separate single POST admission slot prevents blocked durable
writes from consuming all read workers; further mutation requests return 503
`operation_admission_busy`. Socket reads retain the two-second timeout. The
separate command worker remains limited to one operation.

The audit database contains bounded operation IDs, typed actions/reasons and
timestamps, never raw request bodies, command output, credentials, prompts or
chats. At 10,000 retained operation IDs, admission closes pending reviewed audit
archival; idempotency records are not silently evicted to permit replay. No
automatic operation resumes after daemon restart.

## Protected deployment prerequisites (not executed)

Root must review exact sources and authorize a new activation session first.
Use the existing ordinary harness UID; no additional Linux login user is needed.
Install the helper, adjacent `resource_observer.py`, and every source ancestor
root-owned with no group/other write bits. Render `local-admin.json.in` with the existing numeric UID into
root-owned `/etc/ai-harness/local-admin.json` (0600). This file contains only
that numeric UID, never a key. The helper takes no runtime path/command overrides.

Render `ai-harness-admin.service.in` with a root-owned absolute helper file and
the existing user's primary group. The unit owns root:group 0750 runtime ancestry
and root-owned 0700 state. The helper creates its root:group socket 0660 and checks
Linux `SO_PEERCRED` against exactly the configured ordinary UID. Missing peer
credential support fails closed. Existing host processes with that UID have
authority; this is not isolation between same-UID host processes.

The independent status service needs that group in `SupplementaryGroups`.
Protect its UDS behind the reviewed nginx actual-peer boundary and apply the
separate task cgroup egress policy. Task containers must never mount helper,
status or user systemd sockets, protected `/etc` or audit state. UDS absence plus
the reviewed rootless mount/egress boundary is essential; CSRF, paths and peer
UID alone cannot distinguish an authorized daemon from a task that escapes its
namespace. No live Linux, Podman, systemd, network or credential provisioning
acceptance was performed here.

After root approval, validate protected metadata with the installed helper's
`--check` before starting its unit. `--check` only checks paths/configuration;
it neither opens the socket nor observes systemd nor dispatches an action. Keep
the existing chat startup independent: its unit must not require this helper or
status service. Local-adapter downtime leaves chat intact and local admin closed.

## Focused offline verification and live follow-up

Run `python3 -m unittest discover -s ai-harness/deploy/admin -p 'test_*.py' -v`.
Fixtures use temporary SQLite, fake owners, synthetic identities and a private
temporary UDS. They execute no privileged commands. They verify fixed command
vectors, malformed action denial, stale/unknown state, boot/generation changes,
unknown work confirmation, durable idempotency, restart no-replay, dispatch
recheck, bounded hung probes, cached reads, bounded operation capacity, audit
redaction, HTTP routes, exact peer identity and the closed destructive guard.
They also consume the exact Worker1 fixtures copied with provenance under
`server/test/fixtures/h005`, test required status/receipt keys, prove cached reads
do not wait for the writer lock, exercise audit-capacity denial, and check resource
counter units/deltas plus bounded hang behavior. The current focused suite has
18 tests. An HTTP-level fixture blocks mutation admission, rejects eight further
mutations promptly, and verifies status GET remains responsive before releasing
the blocked write. Real `/proc` accuracy and hardened-unit visibility remain live gates.

Separately authorized Linux acceptance must validate user/system manager access
with this hardened unit, real `SO_PEERCRED`, no task mounts, direct/aliased/IPv6
and redirected HTTP denial, ordinary LAN admin, gateway8081/search8082/research
preservation, status survival while chat is down, and no chat dependency on the
helper. Before enabling local destructive actions, integrate/fault-test admission
freeze and reconcile reboot completion via changed boot. These remain NOT_TESTED.

Rollback disables only this new helper/status access path through the reviewed
owner, restores the prior root-owned nginx/policy configuration as a coordinated
set, and preserves the audit database for no-replay evidence. It must not change
the existing chat data, service intent, credentials, task containers or model
services. Never restore an admin HTTP path without its accompanying task denial.
