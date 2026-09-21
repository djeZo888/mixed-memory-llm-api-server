# L2VMP early host facts

Read-only observation: 2026-09-15T02:30:47.866533+00:00. One compact SSH inventory from Mac-Worker1, followed by two narrowly scoped schema-completion reads. No VM writes, key-content reads, authenticated API requests, lifecycle/status calls, GPU work or installed tooling. Evidence: `host-inventory.json`; exact probe: `inventory-readonly.py`, `inventory-contract-followup.py`, `inventory-path-completion.py` (worker only).

## Verified identity

| Mount | Source observed only | UUID | Fstype / FSROOT |
|---|---|---|---|
| `/data` | `/dev/sdb1` (8:17) | `8daf56f1-5649-4163-9d87-919c2d271875` | ext4 / `/` |
| `/data/models-large` | `/dev/sdc1` (8:33) | `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a` | ext4 / `/` |

Both exact mounts rw; distinct whole-volume roots. These source device names are observations, never apply targets. Root available 5,219,024,896 bytes (4.861 GiB): WARN <6 GiB, PASS >=4 GiB. STOP later apply below4 GiB. Root/boot ancestry is /dev/sda; data/model ancestry /dev/sdb and /dev/sdc respectively, based on captured lsblk, no serials/WWNs.

## Current protected lifecycle

- Instance: root `0600`, gid 1001, one link; SHA256 `8a5f7787c00319f093656d4fe0b6953c79ae31669b4da7690e6f7386ecad839a`.
- Durable active state: root `0600`, gid 0, one link; SHA256 `c63de9b1a77aa4d62496880c7dad8cb6a22a10de9736c5305545e3579d576f1f`.
- Volatile recovery journal: root `0600`, gid 0, one link; SHA256 `c63de9b1a77aa4d62496880c7dad8cb6a22a10de9736c5305545e3579d576f1f`.
- GLM completion receipt: root `0600`, gid 0, one link; SHA256 `bcd8d9f85baa9bd1fe54dc65b9022487307190cf11583580ab66af845b53f48b`.

- Instance `ai-vm-d0b`, schema1, no storage_identity or historical_import yet. Existing paths: state `/data/services/llm-manager/active`, lock `/run/llmctl/lifecycle.lock`, recovery `/run/llmctl/recovery.json`.
- Both states schema2, selected `glm-5.3-ud-q4-k-xl-32k`, last_selected `glm-5.3-ud-q4-k-xl-8k`, desired=running, observed=ready, boot_policy=manual, failure=null, state_persisted=true. Original hashes identical; do not transform or reset timestamps. Legacy `/data/services/llm-manager/state/active.json` absent.
- Running exact container `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55`; image `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`; name `/llmctl-glm-5.3-32k`; StartedAt `2026-09-15T00:48:45.235739944Z` unchanged from D3.
- Selected labels: owner=mixed-memory-llm-api-server, instance=ai-vm-d0b, deployment=glm-5.3-ud-q4-k-xl-32k; no io.llmctl.profile label. Runtime bridge; restart=no. Alias glm-5.3, ctx32768, parallel1; only host binding127.0.0.1:30002 to container30002. Full allowlisted argv/mounts are in sanitized evidence; no Docker env dump; follow-up selected only three exact reviewed nonsecret values.
- Native API key `/data/services/secrets/llm-api-key` metadata only; never opened/hashed. Existing key path and all five container mounts remain.
- GLM receipt hash matches D3; receipt records 11 shards /467,289,116,837 bytes and exact pinned revision. This task did not reread payload hashes or verify new Q38 acquisition progress.
- Protected release `/data/services/releases/7b541017c3e1b2bda80676bcd31bc87d0a4507bc-d3-20260915` exists. Five focused file hashes captured; guard matches D3. Full release was not re-audited.

## Relevant filesystem metadata

| Path | Present / type | uid:gid | Mode |
|---|---|---|---|
| `/` | directory | 0:0 | 0755 |
| `/data` | directory | 0:0 | 0755 |
| `/data/backups` | directory | 1000:1001 | 2775 |
| `/data/build` | directory | 1000:1001 | 2775 |
| `/data/containerd` | directory | 0:0 | 0711 |
| `/data/docker` | directory | 0:0 | 0710 |
| `/data/hf-cache` | directory | 1000:1001 | 2775 |
| `/data/logs` | directory | 1000:1000 | 2755 |
| `/data/models-large` | directory | 0:1001 | 2755 |
| `/data/models-large/glm-5.3-ud-q4-k-xl` | directory | 0:0 | 0555 |
| `/data/models-large/glm-5.3-ud-q4-k-xl/UD-Q4_K_XL` | directory | 0:0 | 0555 |
| `/data/services` | directory | 0:1001 | 2755 |
| `/data/services/installer` | absent |  |  |
| `/data/services/llm-manager` | directory | 0:1001 | 2755 |
| `/data/services/llm-manager/acquisition` | directory | 0:0 | 2700 |
| `/data/services/llm-manager/active` | directory | 0:0 | 0700 |
| `/data/services/llm-manager/evidence` | absent |  |  |
| `/data/services/llm-manager/state` | absent |  |  |
| `/data/services/releases` | directory | 0:0 | 2755 |
| `/data/services/releases/7b541017c3e1b2bda80676bcd31bc87d0a4507bc-d3-20260915` | directory | 0:0 | 2700 |
| `/data/services/secrets` | directory | 0:0 | 0700 |
| `/data/services/secrets/llm-api-key` | regular | 0:0 | 0600 |
| `/etc` | directory | 0:0 | 0755 |
| `/etc/llm-server` | absent |  |  |
| `/etc/llm-server/control-api-key` | absent |  |  |
| `/etc/llm-server/control.json` | absent |  |  |
| `/etc/llm-server/network.json` | absent |  |  |
| `/etc/local-ai-server` | absent |  |  |
| `/etc/local-ai-server/storage.json` | absent |  |  |
| `/etc/systemd/system/llm-control.service` | absent |  |  |
| `/etc/systemd/system/llmctl-boot.service` | absent |  |  |
| `/etc/systemd/system/m6b-post-reboot-verify.service` | regular | 0:0 | 0644 |
| `/run/credentials/llm-control.service/control-api-key` | absent |  |  |
| `/run/llm-control` | absent |  |  |
| `/run/llm-control/operations.json` | absent |  |  |
| `/run/llmctl` | directory | 0:0 | 0700 |
| `/run/llmctl/lifecycle.lock` | regular | 0:0 | 0600 |
| `/usr` | directory | 0:0 | 0755 |
| `/usr/local` | directory | 0:0 | 0755 |
| `/usr/local/lib` | directory | 0:0 | 0755 |
| `/usr/local/lib/llm-server` | absent |  |  |
| `/usr/local/lib/llm-server/control-api` | absent |  |  |
| `/usr/local/lib/llm-server/private-network` | absent |  |  |

## Units and narrow gaps

- `m6b-post-reboot-verify.service`: loaded, disabled, active(exited), MainPID0, no drop-ins. Preserve as-is.
- `llmctl-boot.service`, `llm-control.service` and three private socket units: not-found/inactive; no drop-ins. No model boot unit installed. Preserve manual boot intent; no enable/start of model boot.
- Fixed `/etc/local-ai-server/storage.json`, control key/config/root source and N1 policy/standalone helper all absent at checked exact paths.
- Current base Storage.verify lacks read-role support needed by the actual data-only writer guard; use frozen L2 contract for plan and require root-reviewed L2 source/hash before apply.
- Control startup reads control credential; authenticated GET refresh can write operations.json and reads native inference key for readiness. Those calls were deliberately excluded from this inventory.

## Focused source-completion facts

- `host-contract-followup.json`: both unchanged state hashes retain container_running=true. Reviewed required environment triples match; json-file max-size20m/max-file3 and DeviceIDs0,1 match current profile. No GPU command executed.
- `host-path-completion.json`: actual control journal path is `/data/services/llm-control/operations.json`; it and its parent are absent. Earlier `/run/llm-control` presence check is not the production journal path.
- Separate boot recovery closure `/usr/local/lib/local-ai-server` and `/etc/tmpfiles.d/llmctl.conf` are absent.
- Correct Q38A destination `/data/models-large/qwen38-27b-fp8` is root:root0555. Mode alone does not prove 81 hashes/seal. The initial misspelled qwen3.8 path absence was discarded; no conclusion derives from it. Q38A remains artifact evidence owner.

## Late Q38A handoff (external evidence, not new host inventory)

Q38A commit `d42b885ecc25e092dfb0ea1bbc0247b8f91f0b89` reports COMPLETE_ROOT_REHASHED_AND_SEALED at02:27:48UTC. L2VMP read the committed byte-identical protected-evidence copy SHA256 `a9b1ee9c80ca7030b79387b64f63d494159d0db7966f6510737e20c568584cfe` and checked all81 computed tuples plus sealed stat records against the pinned manifest on worker. No L2VMP payload read or fresh live81-stat validation occurred. Proposed receipt is supplied; actual registered publication/auth/live readiness remain separate.
