# N1VM — GLM private transport deployment

2026-09-15, Mac-Worker1 through worker `ssh ai-vm` only. Reviewed source exactly `05cb7ae253f6b93d5d3e0f55c168960c73075bea`; report-only branch `milestone/n1vm-private-glm-exposure`.

**Transport installation, ingress and GLM socket gates: PASS. Native GLM authentication/readiness: PASS. Separate-host forwarding/auth/SSE/agent acceptance: PENDING Worker2.**

Only `llm-private-glm.socket` is enabled/active, listening at **10.156.100.60:30002** on `enp6s18`. Its proxy service is static/inactive, awaiting a first client connection at the final snapshot. Control30000 and Qwen30004 sockets are disabled/inactive; their services are static/inactive and native upstreams absent/not ready. No TCP/client/generation request was made to the private endpoint by this worker.

## Authorization and evidence boundary

The reviewed root authorization and [coordination](n1vm-evidence/coordination-input.md) cover this existing-host deployment. [Apply plan](n1vm-evidence/apply-plan.md) was published at the task root before deployment; it enumerated all eight reviewed hashes, exact destinations and inverse. [Exposure-ready](n1vm-evidence/exposure-ready.md) was published immediately after activation and post-activation guards: socket enabled **02:46:50.260625 UTC**, gates verified **02:46:51.244732 UTC**. Final verification **02:48:48.712345 UTC**.

All VM temporary, staging, report and backup files are under guarded root0700 `/data/services/n1vm-20260915`. The installed small policy/helper/units and explicitly approved helper receipt/lock remain at their fixed system paths. No production source changed. No packages, model/backend/container reload, generation/GPU operation, lifecycle/registry/model state/key/control closure change, driver/daemon/storage/SSH/unrelated-firewall change or reboot was performed. `systemctl daemon-reload` loaded only unit-file changes; it did not reload a backend or Docker. Installer remains paused.

Q38V fixture containers were not inspected or mutated; Docker inspection targeted only the exact preexisting GLM container. Q38A acquisition/seal assets, old models, the obsolete dirty checkout and existing `/tmp` artifacts received no mutation commands. These are operation-scope preservation statements, not byte-for-byte audits of those unrelated assets.

## Checks and outcome

| Check | Result / evidence |
| --- | --- |
| Source identity | Eight deployed files match reviewed Git objects and N1S contract; standalone helper remains byte-identical |
| Initial destinations/units/rules | Absent-file and dangling-symlink checks; relevant systemd search/override/dependency paths inspected; six units not-found/inactive; receipt, lock, enable link and chain/tag absent; [inventory](n1vm-evidence/inventory-before.json) |
| Protected guard/support identity | Exact D3 commit `7b541017c3e1b2bda80676bcd31bc87d0a4507bc`, protected root-owned nonsymlink parents/files, exact source SHA256; [guard metadata](n1vm-evidence/guard-identity-before.json) and [authorized identities](n1vm-evidence/VM-GUARDS.json) |
| Storage guards | Exact protected `require-data-mounted.sh` and `root-disk-guard.sh` PASS [before](n1vm-evidence/root-guard-before.md), [after activation](n1vm-evidence/root-guard-after.md) and [final](n1vm-evidence/root-guard-final.md); no guard bypass |
| Mount identities | Exact ext4 `/data` UUID `8daf56f1-5649-4163-9d87-919c2d271875`; `/data/models-large` UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`; both rechecked |
| Actual Linux units | `systemd-analyze verify --man=no` all six installed units, rc0, no stdout/stderr diagnostics; installed package `255.4-1ubuntu8.16`; [exact command/result](n1vm-evidence/systemd-verify.json) |
| Helper source/preflight | Source-check from reviewed eight-file source layout PASS; installed standalone preflight PASS after daemon-reload; no standalone source-check workaround or helper edits |
| Helper apply/dry-run/check | All PASS; effective chain/jump inspected before socket bind and again afterward; [commands](n1vm-evidence/ingress-result.txt), [rules](n1vm-evidence/ingress-after.json) |
| Native authentication | `/v1/models`: missing401, wrong401, correct200; served `glm-5.3`, `n_ctx=32768`; correct-key `/health`200 `ok`; actual HTTP client source127.0.0.1; [sanitized probes](n1vm-evidence/native-auth.json) |
| Key handling | Existing root0600 `/data/services/secrets/llm-api-key` read through protected no-follow file descriptors into process memory; no value in argv/env/logs/Git; metadata unchanged across the read/probes |
| Final units/files/listeners | All six exact fragments, no effective/pending overrides, NeedDaemonReload=no, exact modes/hashes; only selected-port listeners native127.0.0.1:30002 and private10.156.100.60%enp6s18:30002; [activation](n1vm-evidence/exposure-state.json), [final](n1vm-evidence/final-verification.json) |
| Root free bytes | Before 5,211,570,176; final 5,210,505,216 (4.852661 GiB): above exact4GiB STOP, WARN below6GiB |
| Local focused source checks | Independent local review: 37 private-network unit tests PASS, source-check PASS; production source remains unchanged |
| Rollback | Retained exact original-filter receipt/backup, created-file manifest and [inverse instructions](n1vm-evidence/inverse.md); inverse NOT EXECUTED |

Guard source directory is `/data/services/releases/7b541017c3e1b2bda80676bcd31bc87d0a4507bc-d3-20260915/scripts/common`. `require-data-mounted.sh` SHA256 `5bd86b1e3f84fe5ca76922ca896289edb723b09bc03b99044b7d1ec320215c4f`; `root-disk-guard.sh` SHA256 `2f798c28d905fd819b00c550c0fd3cd7ebdac95ebb32f38876bce952dcbaf813`. The empty `.gitkeep` was also verified; the root guard's only local script dependency is the exact sibling require-data guard. The obsolete checkout guard was never invoked. An initial read-only mount query assumed `/data/models` was a mount, returned no match, and was corrected to the observed/documented `/data/models-large` before guards and deployment; no storage failure or mutation occurred.

## Exact delivered files

All eight files were initially absent and created exclusively with no-follow writes. Source copies under the task's protected `/data` source layout contain only these eight files. [Planned manifest](n1vm-evidence/deploy-manifest-planned.json), [actual created resources](n1vm-evidence/created-resources.jsonl), [installed final hashes](n1vm-evidence/exposure-state.json).

| Destination | Root mode | SHA256 |
| --- | --- | --- |
| `/usr/local/lib/llm-server/private-network/private_network.py` | 0644 | `ad0c48db68ce47213f292abb74aebc9b321b41baefc3385785bb7322e7e78ddc` |
| `/etc/llm-server/network.json` | 0600 | `095bbf0ea64c792efa49ddf16a78383ec74528abe605c86b54ba8ac01563cb60` |
| `/etc/systemd/system/llm-private-control.socket` | 0644 | `9fc827cdb6b0819dd5c1d01e860bf44f230e174f5a27af02cdf3645a727e19fc` |
| `/etc/systemd/system/llm-private-control.service` | 0644 | `8a2c5350d8fdffdf0a1fc154538d5210f40b09c0eb88cddf6368fa77d748ba24` |
| `/etc/systemd/system/llm-private-glm.socket` | 0644 | `884d669f6cb05aab8460fe01c634370025eea366b151a70a888fb746a4967fee` |
| `/etc/systemd/system/llm-private-glm.service` | 0644 | `329b70c762a866acc8f1547f8374d18d97c19f8e8caface17f77507517d108a8` |
| `/etc/systemd/system/llm-private-qwen38.socket` | 0644 | `0c964858717fbf9b838fe2b0e606f19128ee9ef7dfba0ed6fb660d7dc1282ad7` |
| `/etc/systemd/system/llm-private-qwen38.service` | 0644 | `a7cfd0d1a333a9a830d1ef63449dbdc5607978712ea0f616fa4bd9d67fffbff5` |

## Effective ingress and unchanged native model

Owned tag `llm-private-n1s-v1`, chain `LLM-PRIVATE-IN`. Exact first INPUT jump matches destination10.156.100.60/32 TCP ports30000,30002,30004. The chain order is tagged loopback ACCEPT; tagged source10.156.100.0/24 plus ingress enp6s18 ACCEPT; tagged terminal DROP. Helper check verifies precedence and exact rows. Removing these owned rows/declaration from the live filter yields the exact original filter text; SSH/Docker/default policies and all other IPv4 filter rows are unchanged. The receipt's original snapshot also equals the captured baseline.

Only GLM30002 is bound. Rules cover all three fixed reviewed ports, as prescribed by the approved helper; that does not activate control/Qwen. No IPv6 commands changed firewall rules. Selected-port IPv6/wildcard listeners are absent; IPv6 rule equality, outside-LAN denial, public/NAT isolation and reboot behavior were not measured. Units check pre-bind and pre-service-start; they do not continuously police later root firewall edits.

GLM identity remained identical across inventory, native probes, activation and final verification:

- Container `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55` (`/llmctl-glm-5.3-32k`).
- Image `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`.
- PID 149976, started `2026-09-15T00:48:45.235739944Z`, running true, restart count0.
- Command/config-command SHA256 `89510f6d1b0ede1ae1bba8a1f9097c42fa063f2196ee14c000e6c9810e7fae00`.
- Docker native publication remains `127.0.0.1:30002:30002/tcp`; bridged container command was not changed.
- Docker restart policy remains `no`; model manual boot/lifecycle state was not mutated. The new GLM socket's enabled boot intent belongs only to transport.

## Owned resources and inverse

New root0755 parents: `/etc/llm-server`, `/usr/local/lib/llm-server`, `/usr/local/lib/llm-server/private-network`. Eight new files above; new root0600 `/etc/llm-server/private-network-state.json`; new root0600 `/run/llm-private-network.lock`; new root-owned enable symlink `/etc/systemd/system/multi-user.target.wants/llm-private-glm.socket` → `/etc/systemd/system/llm-private-glm.socket`; four tagged rules and one chain. [Supplemental metadata](n1vm-evidence/owned-resources.json) proves their installed ownership. The preexisting `multi-user.target.wants` parent is retained and not owned.

The helper [receipt backup](n1vm-evidence/policy-receipt-backup.json) SHA256 is `38969d24cf79aec51c821743cd4a035689b0b248b04c0f38080322bf8c9185a7`. Protected VM evidence retains the exact original filter, source signatures, delivered/created manifests and inverse. No rollback was needed.

If rollback becomes necessary, stop/disable only the new GLM socket and stop its exact proxy service. Verify all six owned units quiescent and all three sockets disabled; run the exact installed helper `remove --dry-run`, then `remove`. Keep helper/policy/all six units intact until inverse passes. Remove only manifest/hash-proven new files and empty new directories afterward; retain receipt/backups/evidence. Do not remove the preexisting enable parent, stop the model/Docker, flush rules or ignore drift/guard refusal. Detailed [inverse](n1vm-evidence/inverse.md) is retained on the VM.

## Warnings and pending acceptance

- Root space WARN persists. Guard also reports the small preexisting `/home/user/codex-bootstrap` and `/data.pre-mount-root-20260702-083425`; no cleanup was attempted. Guard reports round available GiB; the explicit byte check enforces the actual4GiB STOP threshold. Historical guard report boilerplate describes the guard invocation, not this transport milestone.
- Procedural inventory limitation: initial checks verified ancestors and enable-link absence, but protection of the exact preexisting `multi-user.target.wants` directory was checked after enable. It passed root0755/nonsymlink protection in the supplemental check. No claim of a before-enable metadata capture for that directory is made.
- Worker1 made four native read-only HTTP requests and zero generation, private TCP/API, SSE or agent requests. Native readiness does not prove forwarding. At final capture proxyd had not activated, so direct separate-host forwarding/auth/SSE/disconnect behavior remains pending Worker2's coordinator handshake. Actual Worker2 source/route must be measured by Worker2, never inferred from worker SSH.
- Control/Qwen upstream authentication is not ready; sockets stay off. Reboot restoration, outside-LAN denial, long SSE idle gaps, cancellation and direct agent behavior are not claimed tested.

Next action: coordinator assigns Worker2 the separate-host direct acceptance against `http://10.156.100.60:30002/v1`. Keep installer and all further live model work paused. Stop N1VM at this bounded transport handoff. Report/evidence only are committed; no push.
