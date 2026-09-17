# N1S private TCP transport — source ready for root review

This change supplies only fixed transport policy, six units, and one stdlib
validator/owned-iptables helper. **No live apply was performed.** Installer work
is paused. N1VM requires a fresh root-reviewed apply assignment.

## Fixed boundary and L2 contract

`configs/network/ai-vm-private-api.json` is the entire transport schema. All
fields, types and values are fixed; duplicate/unknown keys and non-UTF-8 JSON
are refused. The only approved source network is `10.156.100.0/24`. A later
frontend /32 narrowing requires reviewed policy and validator changes.

`from scripts.control.private_network import load_policy` exposes the sole
read-only public loader: `load_policy()` returns a fresh dict or raises
`PrivateNetworkError` (ValueError). It opens only `/etc/llm-server/network.json`,
requiring root0600, a regular single-link bounded file, no symlinks, and protected
root-owned parents. It runs no commands. `private_address` supplies the stable
advertised host; `ports` maps `control`, `glm`, `qwen38`. There are no environment,
request, Host/Origin-header, URL, command, CIDR or path override inputs.

| Role | Private IPv4 socket | Fixed numeric upstream |
| --- | --- | --- |
| control | 10.156.100.60:30000 | 127.0.0.1:30000 |
| glm | 10.156.100.60:30002 | 127.0.0.1:30002 |
| qwen38 | 10.156.100.60:30004 | 127.0.0.1:30004 |

L2 owns actual catalog/config advertised-host, Storage dependency, and client
acceptance. Its final catalog is exactly GLM5.3 + Qwen3.8; context variants map
to the fixed role ports without expanding this policy. Old models are retained
and deferred. L2 must include this helper in its separately owned control source
closure/manifest. Its client rule is canonical RFC1918 literal HTTP(S), explicit
port, `/v1`, required key, superseding the older exact-origin expansion proposal.
N1S does not change those files, model profiles, Manager, native authentication,
backend/container loopback bindings, GLM32K, or model/backend ownership.

## Ingress and activation

IPv4 filter INPUT gets one first-position rule, with tag `llm-private-n1s-v1`:

```text
-d 10.156.100.60/32 -p tcp -m multiport --dports 30000,30002,30004
-m comment --comment llm-private-n1s-v1 -j LLM-PRIVATE-IN
```

The exact chain order is loopback ACCEPT; `enp6s18` plus source
`10.156.100.0/24` ACCEPT; terminal DROP. All three rules are separately tagged.
The first INPUT position precedes any broad/established ACCEPT. Other addresses,
ports, SSH22, default policies, Docker chains and IPv6 are untouched. There is
no flush, restore, DOCKER-USER change or BPF assumption.

Apply builds the unreachable complete chain before inserting its jump. A
protected receipt records original filter text and reviewed helper/policy/unit
hashes **before** mutation. An existing chain/jump without the matching receipt
is refused even when its contents look identical. Repeated apply checks actual
rules. Wholly absent rules may be restored after reboot; partial/drifted state
is refused and needs the stopped-unit inverse. `check` always refuses missing
rules regardless of the receipt. The inverse removes only exact owned entries,
refuses extra references/rules, and retains the original snapshot. It never
replays the whole snapshot. A shared flock serializes this helper's operations;
N1VM must exclude concurrent manual/system firewall writers and unit activation.

Each socket has apply then check in ExecStartPre, before any bind. Exact private
address/prefix must be present on UP `enp6s18`. `FreeBind=no` prevents binding an
absent IP. DefaultDependencies=no plus explicit sysinit, network-online and
shutdown ordering avoids the sockets.target/basic.target/network-online cycle;
sockets are enabled under multi-user.target. Boot restoration is therefore
pre-bind and fail-closed. Firewall/source failures leave private activation off.

`BindToDevice=enp6s18` enforces SO_BINDTODEVICE and adds device ordering/lifetime
dependencies. **Host-local calls to the private address can fail** because their
route uses `lo`, despite the firewall's explicit loopback allowance. Use the
unchanged native `127.0.0.1` endpoints for local administration; use a separate
LAN host for private transport acceptance. An interface removal stops the bound
socket; address loss while the device remains requires an explicit check.

Service pre-start also checks effective ingress using systemd's root `+` prefix;
only proxyd then runs as DynamicUser with NoNewPrivileges. Type=notify,
connections-max=16, null stdout/stderr, no core dumps, host network namespace,
no HTTP parser, credentials, body/access logs, buffering layer, or active
connection idle timeout. Services depend only on their own transport socket.
Stopping a socket also stops its proxy; it never stops a model backend.

Six passive units do not continuously police later root-admin firewall edits.
Run `check` after firewall/network maintenance and stop the private sockets on
failure. A removed jump while sockets already run is not automatically repaired
until a later pre-start apply; never claim continuous enforcement. No status
marker or open TCP socket is application readiness.

## Exact later N1VM deployment sequence (NOT EXECUTED)

Run the following only inside the reviewed source checkout on ai-vm under the
separate N1VM assignment. No packages are installed by these commands.

1. Verify source commit and published hashes against the root-reviewed N1S bundle.
   Run data guards before and after deployment:

   ```sh
   scripts/common/require-data-mounted.sh
   scripts/common/root-disk-guard.sh
   python3 -B scripts/control/private_network.py source-check
   dpkg-query --show --showformat='${Version}\n' systemd
   ```

   Required package family: canonical `255.4-1ubuntu8.N`, decimal `N >= 16`;
   the helper enforces this security-update allowlist. Confirm native
   control/model authentication gates with their owners before enabling their
   transport. Keep key bytes, containers and native endpoints unchanged.
   Confirm the address reservation with the network owner; no DHCP changes here.

2. Confirm all proposed destination files are absent, including dangling symlinks,
   and no unit of these names, override/dependency directories, or chain/jump is
   preexisting. Refuse conflicting files; do not overwrite them. Preserve a
   nonsecret root0600 N1VM file inventory under `/data/services/` recording each
   originally absent path and directory plus exact delivered hashes. Existing
   parent directories belong to their current owner and must not be removed.
   The helper will separately preserve the pre-change filter snapshot in its
   protected ownership receipt. Deploy only these reviewed files using root-owned
   protected directories (0755 or tighter), creating only absent directories
   after inspecting every existing parent for root ownership and no symlinks or
   group/other write access:

   ```sh
   sudo install -o root -g root -m 0644 scripts/control/private_network.py /usr/local/lib/llm-server/private-network/private_network.py
   sudo install -o root -g root -m 0600 configs/network/ai-vm-private-api.json /etc/llm-server/network.json
   sudo install -o root -g root -m 0644 configs/network/llm-private-{control,glm,qwen38}.{socket,service} /etc/systemd/system/
   sudo systemd-analyze verify --man=no /etc/systemd/system/llm-private-{control,glm,qwen38}.{socket,service}
   sudo systemctl daemon-reload
   ```

   The above install commands assume the absent-file checks and protected-parent
   checks succeeded; `install` itself is not a drift guard. Do not chmod existing
   parent directories with `install -d`: create only absent directories, preserving
   their existing protection if present. `systemd-analyze verify` must have no
   relevant errors before activation. L2 separately deploys the same helper bytes
   in its reviewed control closure; N1S does not deploy that closure.

3. Run targeted read-only preflight, then dry-run/apply/check before enabling any
   socket. The helper checks exact source/policy/unit bytes, package version,
   effective loaded fragments, missing/pending overrides, interface and ingress.

   ```sh
   sudo /usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network.py preflight
   sudo /usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network.py apply --dry-run
   sudo /usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network.py apply
   sudo /usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network.py check
   sudo systemctl enable --now llm-private-control.socket llm-private-glm.socket llm-private-qwen38.socket
   sudo /usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network.py check
   scripts/common/require-data-mounted.sh
   scripts/common/root-disk-guard.sh
   ```

   The enable step belongs only after native auth acceptance for the exposed
   services. Do not enable a keyless upstream later behind an already open socket.

4. On failure, stop and disable sockets, then stop all proxy services before
   removing ingress. Service units are static and need no enable/disable action.

   ```sh
   sudo systemctl disable --now llm-private-control.socket llm-private-glm.socket llm-private-qwen38.socket
   sudo systemctl stop llm-private-control.service llm-private-glm.service llm-private-qwen38.service
   sudo /usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network.py remove --dry-run
   sudo /usr/bin/python3 -I -B /usr/local/lib/llm-server/private-network/private_network.py remove
   ```

   If drift is reported, stop here with sockets off; preserve evidence and review
   the changed asset. Never flush to work around refusal. For file rollback,
   compare each live file hash to the N1VM inventory and remove only the exact
   six reviewed unit files, policy and standalone helper which that inventory
   proves were newly installed. Remove only now-empty newly created directories;
   daemon-reload afterward. Retain `/etc/llm-server/private-network-state.json`
   as ownership/backup evidence (it contains no keys); future changed-source apply
   must review/archive this receipt, never silently adopt it. Do not remove L2's
   control closure copy or change unrelated files. Rollback interrupts private
   streams; native loopback backends keep running. If preflight failed before
   ownership existed, no rule change was authorized; roll back owned files only.

## Later probe / direct-client acceptance outcomes (NOT EXECUTED)

| Probe | Required result / evidence boundary |
| --- | --- |
| Worker2 actual source and route | Record measured LAN source, return route, exact private destination; do not invent the host address |
| Allowed LAN TCP to the three private ports | Connects when socket active, even when upstream absent; does not prove Ready |
| Missing control or inactive model upstream | Connection closes/resets; no synthetic HTTP503 and no Ready claim |
| Non-LAN source or wrong ingress interface to those ports | Terminal DROP; usually client timeout; a real outside-/24 vantage is needed to prove denial |
| Private local-address test on ai-vm | May fail with BindToDevice; test native 127.0.0.1 separately and require unchanged authenticated admin behavior |
| Native auth at control and inference | Missing/wrong/cross-role keys rejected; correct key succeeds only when upstream ready; keys read privately from files, never argv/logs |
| Catalog and direct client | Exactly GLM5.3 + Qwen3.8; policy-derived host and corresponding fixed port, actual served identity and authenticated readiness required |
| Streaming and client disconnect | Long prefill/SSE gap survives absent transport idle timeout; final bytes/DONE received; disconnect/cancellation behavior measured, not inferred |
| IPv6/wildcard/public | No new matching listener; no public/Internet/NAT/IPv6 isolation claim without separate evidence |
| Reboot / changed policy / missing rule | Check fails on drift or missing rules; approved reboot restores wholly absent owned rules before socket bind |

L2/V1 owns actual direct OpenCode read/edit/test/repair acceptance, canonical
RFC1918 URL and required-key validation, switch/stop admission and readiness.
Those are live closure dependencies, not N1S worker tests. Plain LAN HTTP has no
on-path confidentiality; the existing encrypted SSH-to-loopback path remains
available. The proxy hides client source from the upstream and passes native
HTTP/auth bytes unchanged.

## Focused worker checks and source references

```sh
python3 -B scripts/control/private_network.py --help
python3 -B scripts/control/private_network.py source-check
python3 -B -m unittest discover -s tests -p 'test_private_network*.py' -v
git diff --check
```

Mac has no discovered systemd-analyze or existing disposable Linux runtime:
actual `systemd-analyze verify`, installed Ubuntu package execution, live ingress,
reboot, auth and streaming are **NOT_TESTED**. The exact later verify command is
in step2. No VM/container was created or accessed for these worker checks.

Official semantics checked against [systemd v255 socket documentation](https://raw.githubusercontent.com/systemd/systemd/v255/man/systemd.socket.xml),
[proxyd manual](https://raw.githubusercontent.com/systemd/systemd/v255/man/systemd-socket-proxyd.xml),
[proxyd source](https://raw.githubusercontent.com/systemd/systemd/v255/src/socket-proxy/socket-proxyd.c),
and [Ubuntu systemd.service command prefixes](https://manpages.ubuntu.com/manpages/noble/man5/systemd.service.5.html).
These establish configuration/source semantics, not runtime proof for an installed
Ubuntu package; current online Noble manuals may describe a later patch.

## NETPATCH security-update compatibility — 2026-09-17

Worker1 reported that an unattended Ubuntu security update from
`255.4-1ubuntu8.16` to `255.4-1ubuntu8.17` blocked socket-proxy startup at the old
exact-equality check. The helper now allowlists only canonical `255.4-1ubuntu8.N`
with ASCII decimal `N >= 16`. Whitespace, leading-zero patches, downgrades,
different upstream/distro/Ubuntu bases, epochs and extra suffixes are refused.
The raw package query, fixed proxyd binary path, exact six units, protected
source/policy files, ownership receipt and firewall checks are unchanged.

The installed-source fixtures exercise `_installation()` for `.16`, `.17` and
synthetic future patches, plus rejected boundary and malformed versions. This
is a bounded supported-family policy, not evidence that future patches have
been live-tested. Actual updated-host startup and private API behavior remain
pending Worker1 acceptance; NETPATCH performed no host access or mutation.
The helper digest changes: final composition must refresh the separately owned
source inventory and review the existing ownership receipt; NETPATCH does not
modify shared inventories or bypass source-signature drift checks.
