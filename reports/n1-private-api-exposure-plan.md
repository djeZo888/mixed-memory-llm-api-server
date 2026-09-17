# N1 — private API exposure plan

2026-09-15 · **PLAN READY FOR ROOT REVIEW; NOT DEPLOYED.**
Reviewed source: `6cffccbf1927ff610c21cfc6a0bea3b2f14bd85a`.
Session: `01a0a2cb-6d20-7af0-aa31-71f0509faebf`.

## Decision

Select the installed **systemd-socket-proxyd** as an opaque TCP transport:
three sockets on the exact private IPv4 forward to the three existing loopback
ports. Existing lifecycle/U1B owners retain all model, control and key ownership.
GLM32K, its container, protected release/instance and native key remain unchanged;
no backend restart is needed for this transport. Installer remains STOP.

| Bounded alternative | Observed availability / change cost |
| --- | --- |
| **systemd-socket-proxyd — selected** | `/usr/lib/systemd/systemd-socket-proxyd`, systemd255 (`255.4-1ubuntu8.16`) present; six declarative socket/service units plus narrow ingress policy; keep backend binds and validators unchanged |
| nginx stream | No nginx executable in PATH or standard checked locations; would require installation/module verification and stream timeout configuration |
| Direct private bind | Requires Manager creation/reuse/network guard changes, Q38 equality coordination, private control listener validation, and GLM container replacement; unnecessary here |

This is fixed transport configuration, not a model router or another lifecycle
owner. It does not interpret URLs, inject auth, choose a backend or start models.
No further alternatives were explored after coordination revision4; revision5 fixes the trusted LAN scope.

Publish exactly two **model identities**: `glm-5.3-ud-q4-k-xl` (served `glm-5.3`)
and `qwen38-27b-fp8` (served `qwen3.8-27b`). Only one backend runs at a time.
The two Qwen context variants are deployments of the same model. Exclude old
smoke, Coder-Next and other retained profiles from the published catalog and
remote switch allowlist; keep their artifacts intact. SGLang0.5.14 is deferred.
GLM stays at its proven 32K; Qwen128K/256K require Q38B and live acceptance before
choosing the highest practical context. N1 establishes no new fit or speed claim.

## Observed boundary

One compact SSH inventory at 02:01:58 UTC, native worker TCP cross-check, and
a control metadata follow-up and the final bounded transport availability check. Details and command families are in
[nonsecret evidence](n1-network-evidence.json); early facts were published to
task-root `network-facts.md` before detailed planning.

| Item | Actual observation |
| --- | --- |
| ai-vm private interface | `enp6s18`, `10.156.100.60/24`, UP |
| IPv4 default route | `10.156.100.1` via enp6s18, DHCP; reservation unknown |
| Mac-Worker1 stand-in | `en0`, `10.156.100.120/24`; direct on-link route to VM; SSH confirms source; VM return route direct |
| Inference | `llmctl-glm-5.3-32k`, running PID149976; Docker bridge; exact `127.0.0.1:30002:30002/tcp`; proxy PID150263 |
| Control/Qwen | No relevant listeners on30000/30004; U1B key path and root source closure absent at observation |
| Worker native TCP | SSH22 connected;30000/30002/30004 connection refused; no application bytes sent |
| Host firewall | sudo-n available; UFW inactive; IPv4 INPUT/OUTPUT ACCEPT, FORWARD DROP; empty DOCKER-USER; IPv6 INPUT/FORWARD/OUTPUT ACCEPT |
| Docker |29.6.1; ordinary IPv4 bridge/NAT, ip_forward=1; explicit loopback publish overrides bridge default; no inspected network overrides in daemon.json or daemon CLI |
| IPv6/public | Global IPv6 address and IPv6 default route exist. No inference/control IPv6 listener observed. Upstream ingress/NAT/firewall and public reachability unverified |

The initial Python TCP probe returned macOS errno65 even for SSH22. Native
`/usr/bin/nc` and actual SSH succeeded on22; use that evidence, not Python's
unexplained tool-specific failure, to assess the path. No authenticated API,
generation, test suite, container start, GPU query/allocation or host mutation
was performed. Key **metadata** was checked for control; no key values were read.

Current supportable remote path is the existing SSH-to-loopback arrangement,
with native inference authentication retained. Direct private API access is not
currently available. RFC1918 IPv4 does not prove Internet isolation, especially
with a global IPv6 address. This is a single-host vantage point, not an external
public scan or upstream-router review.

## Exact proposed endpoints and trusted policy

| Service/deployment | Private address | Retained local address | Authentication |
| --- | --- | --- | --- |
| U1B control | `http://10.156.100.60:30000/control/v1` | `http://127.0.0.1:30000/control/v1` | Dedicated control bearer key |
| `glm-5.3-ud-q4-k-xl-32k` | `http://10.156.100.60:30002/v1` | `http://127.0.0.1:30002/v1` | Existing inference key |
| `qwen38-27b-128k` / `qwen38-27b-256k` | `http://10.156.100.60:30004/v1` | `http://127.0.0.1:30004/v1` | Existing inference key through reviewed Q38B file-auth contract |

### Transport and trusted configuration

Proposed nonsecret source policy `configs/network/ai-vm-private-api.json`,
installed root0600 at `/etc/llm-server/network.json` by the existing owner:

```json
{
  "schema_version": 1,
  "mode": "socket_proxyd_private_ipv4",
  "interface": "enp6s18",
  "private_address": "10.156.100.60",
  "prefix_length": 24,
  "allowed_client_ipv4": ["10.156.100.0/24"],
  "control_port": 30000,
  "deployments": {
    "glm-5.3-ud-q4-k-xl-32k": 30002,
    "qwen38-27b-128k": 30004,
    "qwen38-27b-256k": 30004
  }
}
```

These are **proposed** fields. U1B validates a fixed protected path/parents,
regular single-link root0600 file, no symlink, bounded strict JSON, exact schema
and canonical literal RFC1918 IPv4. Verify address/prefix on the named UP
interface, the exact approved source CIDR10.156.100.0/24 (later explicit /32), declared deployment ports/aliases and fixed
loopback upstreams. Reject wildcard/public/IPv6/DNS, alternate encodings,
unknown fields, collisions and arbitrary URLs. Generic `is_private` is not an
RFC1918 allowlist. No env/request overrides. Missing/invalid private policy keeps
private sockets off; existing local service remains usable. Address drift fails
private activation rather than rebinding all interfaces. Confirm a DHCP
reservation before claiming the numeric endpoint durable across lease changes.

Proposed source files: `configs/network/llm-private-{control,glm,qwen38}.socket`
and corresponding `.service` files. Install under the same existing deployment
owner, with the following **exact substitutions**:

| Unit suffix | Socket ListenStream | Numeric proxyd upstream |
| --- | --- | --- |
| control | `10.156.100.60:30000` | `127.0.0.1:30000` |
| glm | `10.156.100.60:30002` | `127.0.0.1:30002` |
| qwen38 | `10.156.100.60:30004` | `127.0.0.1:30004` |

Socket settings: `Accept=no`, `FreeBind=no`, `BindToDevice=enp6s18`, explicit
matching `Service=llm-private-<suffix>.service`; never `[::]` or an omitted host.
Before listening, a small owner validator, proposed
`scripts/control/private_network.py`, checks the fixed policy, interface,
exact unit mapping and effective ingress rules. Wire it through socket
`ExecStartPre=/usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/control/private_network.py check`.
Failure refuses the private socket. Reapply/check the tagged ingress policy
before socket activation after boot; no success marker substitutes for rules.

Each service uses `Type=notify`, `DynamicUser=yes`, `NoNewPrivileges=yes`,
`StandardOutput=null`, `StandardError=null`, and
`ExecStart=/usr/lib/systemd/systemd-socket-proxyd --connections-max=16 <numeric-upstream>`.
Use the host network namespace (no `PrivateNetwork=yes`), no model-service
Requires/Wants/Exec hooks, no credential loading, no body/access logs and no
new model supervisor. Leave `--exit-idle-time` at its infinity default. The
16-connection transport cap does not replace U1's existing bounded request
handling. Do not install/enable any unit in N1.

The v255 manual describes one upstream connection per accepted client and idle
exit only when no connections exist. Source `connection_shovel`/`traffic_cb`
forwards opaque bytes with bounded pipe buffers, drains pending client bytes
before releasing a closed client, and contains no active-connection idle timer
or HTTP/SSE parser. Thus no HTTP response buffering toggle or proxy read timeout
is needed; client/backend timeouts still apply. These are source findings, not
live SSE/cancellation proof for the Ubuntu package. Upstream authentication
headers and body bytes pass unchanged; the proxy cannot verify model readiness.
Sources: [v255 manual](https://raw.githubusercontent.com/systemd/systemd/v255/man/systemd-socket-proxyd.xml),
[v255 source](https://raw.githubusercontent.com/systemd/systemd/v255/src/socket-proxy/socket-proxyd.c).

## Exact source seams and advertised-origin policy

| Owner / files and functions | Required action |
| --- | --- |
| U1B `scripts/control/adapter.py::production_application`, `serve.py::main` | Finish reviewed production binding with dedicated root0600 `/etc/llm-server/control-api-key` and root closure `/usr/local/lib/llm-server/control-api`; current base refuses startup and both live paths were absent. Retain single loopback listener30000, same Application/executor/journal/canonical lease and credential reader. Consume protected exposure policy for discovery; no private listener option needed here. |
| U1B `scripts/control/catalog.py::_endpoint`, `Catalog.__init__`, `Catalog.public`, production DTO builder | Current `_endpoint` rejects private host and emits loopback `base_url`, `address_scope=server_loopback`, `server_relative=true`. Permit only policy-derived endpoint host/port/alias; emit exact private `base_url`, `address_scope=private_ipv4`, `server_relative=false`, existing `served_model`/`authentication_required`. Retain all four readiness proofs: trusted identity, safe backend network, authenticated model, runtime health. Verify transport configuration separately; a socket accepting TCP is not ready inference. Publish only the two allowed model identities and eligible deployment variants. Never derive origins from HTTP Host/Origin or arbitrary strings. |
| V1/V0 `scripts/client/client_common.py::endpoint`, `config_for`, `verify_install`; `bootstrap.py::parser/bootstrap`; `launch.py::launch` | Add explicit private mode and exact approved origins `{http://10.156.100.60:30002/v1,http://10.156.100.60:30004/v1}` to the ordinary user's private manifest. Require key-file auth, validate origin/model again at launch, reject redirects, arbitrary private hosts, credentials/query/fragment and auth-disabled private mode. Stable control origin is exactly `http://10.156.100.60:30000/control/v1`; separate key. Current V0 has no automatic control discovery/switch integration. Use reviewed bootstrap into a new private prefix per changed selection; never hand-edit installed files. |
| L1/Q38B runtime validators | **No exposure relaxation.** Keep `Manager.validate_deployment` loopback `endpoint.host`, `create_args` loopback publication, `network_check`/`validate_reused_contract`, `runtime_io.validate_container_network`/`validate_published` exact loopback guards, and `probe`/`probe_sglang` unchanged. Q38 `validate` whole-profile equality, `validate_reused`30004 mapping and `probe` exact loopback URL/alias remain valid. Base Manager still dispatches SGLang through `qwen_next`; actual Q38B integration is required independently, never infer the old Coder-Next contract. |
| Profiles/control HTTP | GLM/Q38 files under `configs/deployments/` retain endpoints, ports, context, aliases and key mounts unchanged. `scripts/control/http.py::make_server` retains literal loopback-only bind checks. Existing control credential/unit hardening and recovery contracts remain U1B-owned. |
| Documentation/installer seam | Update `docs/control-api.md`, `docs/client-install.md`, `docs/agent-client.md` for exact private mode, discovery, transport limitations and separate keys. `scripts/install/config.py::validate` is loopback-only; coordination reports newer I1c receipt binding also loopback-only, but its implementation is absent here. Record this gap; installer remains STOP, no receipt is rewritten. |

## Narrow firewall and transport boundary

Use the observed iptables interface; UFW is inactive. Before private sockets,
install one tagged INPUT jump for destination `10.156.100.60/32`, TCP dports
`30000,30002,30004` into an owned `LLM-PRIVATE-IN` chain. Ordered chain rules:

1. `-i lo -j ACCEPT` (local use of the private address).
2. `-i enp6s18 -s 10.156.100.0/24 -j ACCEPT`.
3. `-j DROP` for remaining matching traffic.

Check jump precedence against existing INPUT rules and exact counters/order.
Apply idempotently; retain an exact inverse removing only this jump/chain.
No default-policy change, UFW enablement, table flush/restore, SSH22 change,
Docker chain edit or upstream forwarding. Reapply and verify this owned rule set
before sockets can listen after boot. No BPF allowlist is assumed: BPF enforcement
was not verified. The userspace proxy is a host INPUT listener; its upstream
connection is host-local to existing loopback publication, so this selection
requires **no DOCKER-USER relaxation or new Docker publication**. The proxy hides
client IP from upstream; source enforcement must happen before it, not inside
control. Keep Docker's existing loopback/direct-routing protection.

Root coordination revision5 approves **the current trusted LAN10.156.100.0/24**
for this plan, including a future frontend whose IP is not yet assigned. This
supersedes the early Mac-only /32 draft. Mac-Worker1 remains the observed stand-in
at10.156.100.120; Worker2 is the requested separate-host acceptance client and
must record its actual source/route before validation. Do not invent its IP.
Source CIDR is an access selector, not user identity; native bearer auth remains
mandatory. Plain HTTP supplies no confidentiality against on-path LAN peers.
The trust boundary is root-selected; upstream isolation/TLS are not verified.
Existing encrypted SSH-to-loopback remains available when that transport is
needed. No hostname/certificate, public IPv4 or IPv6 publication is proposed.
Later tighten to the observed frontend /32; retain worker/admin sources only
when selected. Frontend server-side tools hold credentials; browsers never
receive keys or call control. API server remains API-only.

## Caller workflow and future acceptance

1. An ordinary user in an explicit trusted worker/frontend workspace calls
   authenticated `GET /control/v1/status` and `/catalog` at stable control30000.
   Select a catalog **deployment_id**, not a served alias or arbitrary profile.
2. POST `/switch` with exactly `deployment_id`, fresh `expected_active`,
   `expected_generation`, `allow_interrupt`, and an `Idempotency-Key`. Changing
   the active model explicitly permits interruption. Stop uses the two expected
   fields on `/stop`. Busy/stale state yields409; unready infrastructure may503.
3. A202 is admission only. Poll `operation.poll_url`, then refresh status/catalog;
   require successful operation and current `ready=true`. Stop must prove the
   owned container stopped; failed/timeout/interrupted outcomes are not Ready.
4. Read the selected endpoint's exact `base_url` and `served_model`; authenticate
   with the **inference** key. After a switch, refresh them again. Control does
   not proxy `/v1`: GLM30002 and Qwen30004 are different origins. A private socket can accept TCP even when its upstream model/control is absent;
   the connection then closes/resets, not an invented HTTP503. The inactive
   model port has no ready inference service. No drain or automatic stream replay exists.
5. Use V0's reviewed OpenCode bootstrap/launcher with the discovered selection,
   then V1's actual read/edit/test/repair workflow, retaining normal tool approval
   behavior. Tools run on the worker/frontend, never ai-vm. No new agent framework.

Future deployment/validation, **not executed in N1**:

- Root reviews this concrete plan; coordinate Q38B/U1B/L1/client source and the
  released request lease. Before any apply, worker-only source checks must cover private unit mappings, missing-policy/rule rejection, opaque transport limits,
  control auth/bounds,
  catalog origins, stale switch admission and client origin/key restrictions.
  Reuse `tests/test_control*.py`, `scripts/client/tests/` and the existing
  lifecycle regressions; verify proposed unit files with `systemd-analyze verify`
  on a compatible worker. No tests/image fixtures were run in N1.
- Before/after later deployment run `require-data-mounted.sh` and
  `root-disk-guard.sh`; preserve key bytes, protected artifacts and current GLM
  container. Apply/check only owned ingress policy then sockets; no GLM reload.
  Roll back by stopping/disabling only the new sockets and their proxy services,
  then removing only their tagged firewall rules. Existing loopback service stays
  usable. Do not bind private control before U1B auth is accepted, or claim Qwen
  ready before Q38B gates. Transport rollback can interrupt remote streams.
- From Worker2 (and Mac-Worker1 stand-in): record actual source/return route; native TCP22 and the three
  private sockets; prove catalog/application readiness separately. Confirm local
  admin still works and absent upstreams fail truthfully. Validate source denial
  from an explicitly available host outside the allowed /24 when one exists; the
  allowed host alone cannot prove that negative test. Include long-prefill/SSE
  idle gaps, final bytes, client disconnect and bounded reconnect behavior through
  the actual proxyd package; TCP forwarding is not generation cancellation proof.
- With secret-safe file readers, verify missing/wrong/correct-key results on
  inference `/v1/models` and chat and every control route (401/401/success as
  applicable). Use distinct key roles and test cross-key rejection. Control keys
  never enter argv/env/logs/Git; inference key stays file-mounted in the server.
  Ordinary-user local key copies, if provisioned later, require private0600
  files outside Git and no terminal print. V0 currently passes the file-loaded
  inference key only to its isolated child environment: do not claim file-only
  end-to-end secret transport or dump child env/debug config with real keys.
- Prove exactly `glm-5.3` / `qwen3.8-27b` at their discovered endpoints: ordinary
  generation, nonstream and SSE tool calls/results/continuation, final DONE and
  finish reason, and real V1 edit/test/repair evidence. Reuse
  `scripts/agent/acceptance.py` and V1's actual pinned OpenCode workflow. GLM
  uses reviewed `reasoning_effort=low`; Q38 requires its reviewed no-thinking
  preset, not copied GLM/Coder-Next settings. Current V0 effort enum accepts only
  low, so Q38B/V1 must supply the reviewed client preset before Qwen acceptance.
- Exercise actual GLM→Qwen→GLM switch and stop, catalog two-model roster,
  generation/identity concurrency checks, busy/stale/idempotent operations,
  failed/timeout truthfulness without destructive injection, and the selected
  context's practical workload. Q38 source declares keyless health/metrics
  exceptions; verify its final native route contract and do not call all routes
  authenticated. Model/control authentication and WebSocket denial remain gates.
- Inspect only bounded nonsecret evidence; prove no key argv/log/Git exposure.
  No external vantage or router inventory was available: public IPv4 NAT and
  global IPv6 reachability remain **NOT VERIFIED** until separately checked.
  Absence of a wildcard/IPv6 listener plus the scoped /24 rule narrows host exposure but
  does not certify upstream isolation or LAN confidentiality.

## N1 checks and next action

PASS: instructions/current reviewed reports and focused source inspection;
read-only network/port/firewall inventory; separate-worker native route/TCP;
nonsecret evidence and report-only review. WARN: Python probe discrepancy,
DHCP permanence/LAN trust/upstream ingress unknown, U1B absent at observation,
Q38B and newer receipt source unavailable here. NOT RUN: tests, API/model
requests, deployment, switches, firewall changes or public reachability tests.

Next action: root reviews the exact policy, bindings and source-owner changes
above (coordination revisions3/4/5), then assigns the bounded live exposure/client follow-up. No additional
human permission prompt is requested by N1. Installer work remains STOP.

Report delivery checks: JSON evidence parse and changed-file whitespace review;
changed-file credential-pattern scan, report-only scope, author/committer, clean
tree and incremental bundle verification are recorded in task-root `handoff.md`.
