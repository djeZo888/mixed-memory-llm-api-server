# N1S — fixed private TCP transport source

2026-09-15 · **PASS: BOUNDED SOURCE CHECKS; NOT DEPLOYED.**
Branch: `milestone/n1s-private-tcp-transport`.
Base: `6ffd620` (full prerequisite is recorded in task-root handoff/bundle).

## Delivered

Published task-root `../transport-contract.md` before implementation, with exact
schema, no-argument read-only `load_policy()` API, owned paths and L2 closure
requirements. Final hashes and source revision are appended there after commit.

- Fixed protected `/etc/llm-server/network.json` policy; exact
  `enp6s18`, `10.156.100.60/24`, trusted `10.156.100.0/24`, ports30000/30002/30004.
- Six exact socket/proxyd service units, private IPv4 to matching numeric
  loopback ports, Accept=no/FreeBind=no/BindToDevice, network-online ordering,
  pre-bind apply/check, DynamicUser/NoNewPrivileges, notify/cap16, no idle timeout.
- One stdlib `scripts/control/private_network.py`: protected loader, source/unit/
  interface/effective-ingress checks and fixed tagged iptables apply/inverse.
  No arbitrary URLs/CIDRs/commands, request/header/environment overrides, backend
  owner, package install, HTTP parser, credentials or installer machinery.
- [N1VM runbook and acceptance outcomes](../docs/private-network.md): exact later
  file destinations, guards, verify/preflight/dry-run/apply/enable ordering and
  stopped-unit inverse, ownership/hash conditions for file removal.

Owned INPUT jump is first and scoped only to the private destination and three
TCP ports. The owned chain allows lo, allows the selected interface/LAN, then
DROP. The helper builds the complete unreachable chain first, retains a protected
pre-change snapshot and source hashes, refuses unowned/drifted assets, and never
flushes/restores tables or touches SSH/Docker/default policies. Reboot activation
restores wholly absent owned rules before binding; stale receipt alone fails check.
Interrupted partial apply can be removed only with the exact stopped-unit inverse.

## Checks actually run on Mac-Worker1

| Check | Status | Evidence / practical boundary |
| --- | --- | --- |
| AGENTS, root-approved N1 plan, coordination-input at start/implementation/verification boundaries | PASS | Revision1 transport-only ownership followed |
| `python3 -B scripts/control/private_network.py --help` | PASS | Fixed CLI; apply/remove support dry-run |
| `python3 -B scripts/control/private_network.py source-check` | PASS | Exact JSON policy and generated six unit source bytes |
| `python3 -B -m unittest discover -s tests -p 'test_private_network*.py' -v` | PASS | 37 tests, final run 0.046s; no host/API calls |
| Protected policy reads | PASS | Actual temporary descriptor/metadata tests; symlink/parent/hardlink/FIFO/owner/mode/size/race negatives; fixture maps worker uid only |
| Strict policy and interface | PASS | Unknown/duplicate/type/address/prefix/encoding negatives, no loader host commands/overrides; mocked ip response drift/absence/down |
| Unit and installed-source drift | PASS | Source mapping, pre-bind ordering, fragment/drop-in/pending dependency dirs/reload, byte drift, approved-package version negatives; host calls mocked |
| Owned ingress/inverse | PASS | First jump before existing SSH accept; exact LAN/interface/deny order; no receipt adoption; stale receipt/missing rules; duplication/foreign refs/drift; interruption at each apply write; dry-run/idempotence/static-service inverse; simulated rules only |
| `git diff --cached --check` and changed-file secret/path checks | PASS | Final staged scope checked; credential scan reports filenames only, no values |
| Author and committer / incremental bundle | PASS | Both CodexAIagent <133749519+djeZo888@users.noreply.github.com>; exact revision/hash and bundle verification in task-root handoff |
| Actual `systemd-analyze verify` | **NOT_TESTED** | Worker Darwin; no systemd-analyze or existing disposable Linux runtime discovered; exact later command below |
| VM/firewall/unit/service changes, backend/API/model requests, live auth/SSE/readiness, reboot | **NOT_TESTED / NOT EXECUTED** | Source-only authorization; no ai-vm access, container/VM creation, package installation or push |
| Installer / broad suites | NOT RUN | Explicitly paused/out of scope |

One interim combined test run failed only because the expected diagnostic still
said “drop-in” after dependency-directory checks changed its wording. The wording
and dependency regression coverage were reconciled; the final 37-test run passed.
Independent source review also caught and fixed static-service inverse admission,
strict UTF-8 parsing, dependency-directory drift and the socket boot-order cycle.

Later compatible-host verification, **not run here**:

```sh
sudo systemd-analyze verify --man=no /etc/systemd/system/llm-private-{control,glm,qwen38}.{socket,service}
```

## Warnings and closure dependencies

- `BindToDevice=enp6s18` can exclude host-local private-address traffic via lo,
  even though the firewall permits lo. Native127.0.0.1 admin endpoints stay
  unchanged; a separate LAN worker must validate the private endpoint.
- Six passive units enforce activation/reboot preconditions and explicit checks.
  They do not continuously police later root firewall edits. A missing rule
  detected after activation requires stopping sockets; concurrent firewall/unit
  mutations must be excluded during apply/inverse.
- Opaque TCP can accept then close/reset with an absent upstream. This is not
  Ready and does not synthesize HTTP503. Native auth and readiness remain required.
- Official v255 sources support the unit and opaque-forwarding semantics; actual
  Ubuntu255.4-1ubuntu8.16 execution, stream/cancel behavior and live rules remain
  untested. The helper refuses an unreviewed systemd package version.
- N1VM must preserve exact reviewed files, existing native auth/key bytes/backend
  binds/GLM32K and run before/after data/root guards. It must refuse conflicting
  files, keep an exact new-file inventory, and remove only hash-matching owned
  assets on rollback. Ownership receipt is preserved, not used as readiness.
- L2 alone owns advertised catalog/control config/Storage/client integration and
  closure manifest changes. Final catalog exactly GLM5.3 + Qwen3.8; old artifacts
  retained/deferred. N1S policy does not enumerate deployment/context variants.
- Worker2 direct-client, actual source/route, denied-source vantage, auth, model
  identity/readiness and real tool workflow acceptance remain live-owner work.
  No Internet/IPv6/publication/isolation, DHCP permanence, or TLS claim is made.

Next action: root reviews this source/contract/bundle, then assigns fresh N1VM
live apply using the runbook. Installer remains paused. No extra policy framework
or alternative transport research is required.
