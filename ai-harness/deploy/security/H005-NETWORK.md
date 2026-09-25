# H005 task network boundary — source candidate

This is a source/configuration candidate, not deployment evidence. Linux nftables,
rootless Slirp process placement, nginx access, systemd socket permissions and
Chromium network isolation are **NOT_TESTED** here. Do not expose admin routes
until the complete live matrix below passes under a separately authorized window.
The old Slirp configuration alone permits broad host access. Shell permission
checks, CSRF and secret URLs cannot enforce this network boundary.

The task launcher enters a fixed `aiharnesstasks.slice` under the existing ordinary
user manager and verifies its actual cgroup membership before Podman starts. The
Podman systemd cgroup parent is fixed to the same slice. Root installs a scoped
`inet ai_harness_tasks` output table matching that slice's cgroup v2 ancestor,
including host-side Slirp sockets. Other host processes retain their existing
network policy. The table permits TCP127.0.0.1:8081/8082, exact reviewed DNS
resolvers on53, and public TCP80/443 research. Other host-local, private,
link-local, multicast and translation/tunnel address ranges are rejected. Host
aliases and redirected requests undergo the same destination checks. No engine
mount exposes host UDS, D-Bus, Podman sockets, credentials or writable host
cgroups. Dropped capabilities/no-new-privileges remain in place.

Root's policy watcher verifies the live nft JSON identity and slice inode every
2 seconds, then publishes a root-owned receipt. Launch requires a receipt no more
than6seconds old with matching boot ID and current slice inode, both before and
after entering the scope. Watcher failure or changed rules removes/stales the
receipt and prevents new task starts; it does not depend on status/chat. It does
not terminate already running tasks; installed firewall rules persist. Root must
not remove the policy while any task remains active. Receipts attest recent
configuration identity; only actual-container tests establish packet enforcement.

nginx separately denies actual local/Slirp peers for `/admin` and `/api/admin/`.
It never trusts forwarded addresses. `/status`, `/status-assets/` and
`/api/status/` use the independent status daemon UDS even if chat8080 is down.
The optional `status.ai-harness` vhost is read-only and has no admin routes.
Existing image approval-token route restrictions remain intact. The privileged
helper is a different private UDS and has no TCP listener. Status/control
credentials use server-side systemd credentials; never mount or export them to
engines/browser. Anonymous reachable LAN/VPN administrators all have the same
current authority; paths are not authentication.

## Reviewed activation sequence (not executed)

1. Record current source identities, listeners, nft table state, nginx config and
   existing tasks without reading conversations. Schedule a bounded task drain
   before changing launch/network policy. Preserve source/config backup and
   protected credential files without printing contents. Provision no new model,
   account, key or inference during boundary checks.
2. Install reviewed policy and helper source under a root-owned nonwritable
   deployment directory. Install `task-egress.json.example` as root-owned0644
   `/etc/ai-harness/task-egress.json`, with root-owned nonwritable ancestry. Set
   the verified existing service UID and exact resolver addresses from the
   current host. No environment overrides are accepted. Verify Linux unified
   cgroup v2, nft socket cgroupv2 support and the existing user systemd manager.
3. Install root-owned `/etc/systemd/user/aiharnesstasks.slice`, reload the existing
   user manager and start that slice. It must be exactly
   `/user.slice/user-UID.slice/user@UID.service/aiharnesstasks.slice`. The user
   manager must keep the slice active; stop/recreation invalidates its inode.
4. Render `python3 ROOT_OWNED_DEPLOY_DIR/security/task-egress-policy.py --dry-run`
   into a protected review artifact. Review its exact table and resolver scope;
   it must never flush unrelated rules. Render `ai-harness-egress.service.in`
   replacing only reviewed paths/UID, validate the system unit, then in the
   approved window start it. `--apply-watch` performs nft syntax check before an
   atomic replacement of its own table. An error refuses launch; no fallback.
   A later root rule change requires explicit review/restart, not auto repair.
5. Update launch source with pinned existing engine identities unchanged. Test
   a synthetic task container before admitting real chats. Inspect every host
   Podman/Slirp/conmon socket-owning process and container cgroup: all task egress
   must match the protected ancestor. A helper outside the slice blocks release.
6. Install root-owned nginx includes under `/etc/ai-harness/`. Inventory **all**
   current harness IPv4/IPv6/Slirp egress addresses and add them to
   `admin-peer-deny.inc` and the existing approval-token deny list. Keep private
   listener10.156.100.61:80 only. The main HTTP context must not use realip header
   rewrites. `validate-nginx-boundary.py --check` reads `nginx -T` privately and
   reports only pass/fail; never run `nginx -T` into public logs because approval
   proxy includes contain protected values. This preflight is not full nginx
   policy verification; inspect source route changes and perform real requests.
7. Render the independent status system unit with existing ordinary user and
   nginx group. Runtime directory0750 and HTTP socket0660 must permit only that
   service and nginx. No required dependency is added to chat. Use existing
   control-key authority copied to root-owned0600
   `/etc/ai-harness/control-api-key` only in the approved credential-provisioning
   step; `LoadCredential` gives it to status alone. Parent daemon configuration
   determines node URL, state directory and allowed origins; never browser JS.
8. Validate nginx then reload only after complete container-denial checks against
   staged routes succeed. Keep admin exposure withheld on any failed/unknown
   enforcement result. Check status with chat stopped in the approved window;
   keep watcher available independently of both chat and status.

## Actual-container acceptance required

Use a fresh synthetic ordinary task container with no model invocation or real
history. Test shell HTTP and Chromium navigation/fetch, with forged Host,
Origin, X-Forwarded-For and X-Real-IP. Record status/error classes only, no tokens
or response payloads. Destinations include10.0.2.2,127/8, harness.61, ai-vm.60,
all host aliases/currentIPv6, direct node30008, existing control30000 and every listener/alternate
port. `/admin`, `/api/admin/v1/targets`, action/operation routes, private helper
UDS and the canvas approval-token route must be inaccessible to the task.
Follow a public fixture redirect and a DNS alias resolving to each protected
address; denial must hold at the final destination. Verify neither privileged
UDS nor host D-Bus/cgroup controls can be reached through task mounts.

Verify gateway8081 with a non-inference fixture and search8082 with synthetic
query; public HTTP/HTTPS research and DNS must remain functional. Check public
IPv6 if enabled. Confirm an external trusted peer can view status/admin, valid
CSRF actions use only approved synthetic/no-op fixtures, stale/absent CSRF fails,
and `status.ai-harness` cannot mutate even with a forged Origin. Verify status
survives stopped chat and chat does not require the status daemon. Repeat
launcher signal/cancellation/exact-container settlement tests through the real
systemd scope; offline ACP tests intentionally use a fake interpreter and do not
establish signal behavior through systemd-run. Finally alter a synthetic policy
identity or stale its receipt in an isolated acceptance fixture: new launches
must fail closed. No production firewall fault injection is authorized here.

## Rollback

Disable external admin routing first, retain the protected helper/credential
files, drain/settle exact synthetic tasks, and stop new task admission. Restore
reviewed previous nginx/source templates and validate before reload. Keep this
egress policy while any H005 task runs. Only after proving the slice empty may
root stop its watcher and delete exactly `inet ai_harness_tasks`; never flush a
ruleset. Restore old task launch only with admin/control exposure removed. Restore
status independently; do not restart models, alter pins or run installer work.

## Offline checks and reference

`python3 ai-harness/deploy/tests/test-task-egress.py` exercises generated rule
semantics with a small independent packet interpreter, stale/boot/inode receipt
rejection, UDS route and actual-peer fixtures. It does not emulate the Linux
kernel. `python3 ai-harness/deploy/tests/test-run-engine.py` verifies existing
ACP/token/mount/signal/cleanup behavior with fake Podman and fake scope entry.
`bash -n ai-harness/deploy/run-engine.sh` checks shell syntax.

The priority frozen node transport is10.156.100.60:30008; existingcontrol30000
remains separate. Both are denied to tasks on all ports by the same private
destination rule. Neither port is an exception.

The cgroup socket ancestor match is documented by
[the nftables project](https://netfilter.org/projects/nftables/manpage.html).
The scope command inherits caller environment and executes synchronously per
[Ubuntu systemd-run documentation](https://manpages.ubuntu.com/manpages/noble/man1/systemd-run.1.html).
Neither source reference is evidence that the current host kernel/runtime has
passed this release's boundary acceptance.

Placement review also checked [Podman4.9.3 conmon cgroup source](https://github.com/containers/podman/blob/v4.9.3/libpod/oci_conmon_linux.go)
and [its Slirp helper source](https://github.com/containers/common/blob/v0.57.5/libnetwork/slirp4netns/slirp4netns.go).
These support the intended inheritance/explicit-parent design; the installed
runtime identities and all socket-owning process placement still require live
readback and packet tests.
