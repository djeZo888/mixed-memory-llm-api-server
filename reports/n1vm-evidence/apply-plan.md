# N1VM reviewed apply plan

Published UTC: 2026-09-15T02:42:45.544650+00:00

Authorization: reviewed N1S `05cb7ae253f6b93d5d3e0f55c168960c73075bea`, root independent review PASS, live GLM-only assignment and coordination revision1. This plan is within that authorization; no further approval gate.

## Exact source files

| Source | Destination | Root mode | SHA256 |
| --- | --- | --- | --- |
| `scripts/control/private_network.py` | `/usr/local/lib/llm-server/private-network/private_network.py` | 0644 | `ad0c48db68ce47213f292abb74aebc9b321b41baefc3385785bb7322e7e78ddc` |
| `configs/network/ai-vm-private-api.json` | `/etc/llm-server/network.json` | 0600 | `095bbf0ea64c792efa49ddf16a78383ec74528abe605c86b54ba8ac01563cb60` |
| `configs/network/llm-private-control.socket` | `/etc/systemd/system/llm-private-control.socket` | 0644 | `9fc827cdb6b0819dd5c1d01e860bf44f230e174f5a27af02cdf3645a727e19fc` |
| `configs/network/llm-private-control.service` | `/etc/systemd/system/llm-private-control.service` | 0644 | `8a2c5350d8fdffdf0a1fc154538d5210f40b09c0eb88cddf6368fa77d748ba24` |
| `configs/network/llm-private-glm.socket` | `/etc/systemd/system/llm-private-glm.socket` | 0644 | `884d669f6cb05aab8460fe01c634370025eea366b151a70a888fb746a4967fee` |
| `configs/network/llm-private-glm.service` | `/etc/systemd/system/llm-private-glm.service` | 0644 | `329b70c762a866acc8f1547f8374d18d97c19f8e8caface17f77507517d108a8` |
| `configs/network/llm-private-qwen38.socket` | `/etc/systemd/system/llm-private-qwen38.socket` | 0644 | `0c964858717fbf9b838fe2b0e606f19128ee9ef7dfba0ed6fb660d7dc1282ad7` |
| `configs/network/llm-private-qwen38.service` | `/etc/systemd/system/llm-private-qwen38.service` | 0644 | `a7cfd0d1a333a9a830d1ef63449dbdc5607978712ea0f616fa4bd9d67fffbff5` |

## Gates already passed

- Exact protected corrected D3 guard/support bytes match Git commit `7b541017c3e1b2bda80676bcd31bc87d0a4507bc` and supplied VM-GUARDS.json. All parents protected, root-owned, no symlinks; guard scripts root0700.
- `require-data-mounted.sh` and `root-disk-guard.sh --report /data/services/n1vm-20260915/root-guard-before.md`: PASS. Data and model UUIDs verified at `/data` and `/data/models-large`. Root free recorded in guard identity; exact measured 5,211,570,176 bytes (4.853 GiB), above 4 GiB STOP and below 6 GiB WARN.
- All eight destinations, six unit identities, relevant dependency/override paths, owned receipt/lock, activation symlink, chain and tag absent. Existing parents protected. Linux systemd package exactly `255.4-1ubuntu8.16`.
- Only native `127.0.0.1:30002` listener; control30000/Qwen30004 absent. GLM container `bb77b764cb9677f3c04c1e60359d287a15abb304ba289f38703e58b5a6fc0d55` running with PID149976, restart_count0, started `2026-09-15T00:48:45.235739944Z`; command hash `89510f6d1b0ede1ae1bba8a1f9097c42fa063f2196ee14c000e6c9810e7fae00`.

## Anticipated operations in order

1. Create only absent root0755 parents `/etc/llm-server`, `/usr/local/lib/llm-server`, `/usr/local/lib/llm-server/private-network`. Preserve all preexisting parent metadata. Record O_EXCL-created files and dirs in root0600 inventory under `/data/services/n1vm-20260915`. Keep staged source-layout copy of only the eight exact files there for source-check and inverse evidence.
2. Copy eight exact files with exclusive no-follow creation; verify bytes, SHA256, root UID/GID, single-link and modes. Run actual `systemd-analyze verify --man=no` on all six installed unit paths. Any real unit/source defect stops before activation without local edits.
3. Run source-check in reviewed staging layout. Daemon-reload only as needed to load the exact six fragments. Run installed helper preflight and apply --dry-run. Those create only root0600 `/run/llm-private-network.lock`.
4. Apply reviewed helper and check effective rules. Helper creates root0600 `/etc/llm-server/private-network-state.json` with original filter backup and file signature before changes. Build `LLM-PRIVATE-IN`: tagged lo ACCEPT, tagged enp6s18 + 10.156.100.0/24 ACCEPT, tagged terminal DROP. Insert the exact first INPUT jump for destination10.156.100.60/32 TCP30000,30002,30004 tag llm-private-n1s-v1. Compare remaining IPv4 filter rows with baseline; preserve SSH/Docker/default policies, IPv6 and all unrelated configuration.
5. Prove native GLM `/v1/models` missing/wrong key401 and correct key200, served identity glm-5.3/context32768; correct-key `/health`200. Read existing key only from no-follow protected descriptor into Python memory. Record statuses/identity only, no header/key/body logs or generation. Recheck exact container/image/command identity.
6. Enable/start ONLY llm-private-glm.socket; record new `/etc/systemd/system/multi-user.target.wants/llm-private-glm.socket` symlink. Its native proxyd service may start upon connection. Control/Qwen sockets remain disabled and services inactive. Verify only exact private10.156.100.60:30002 plus native127.0.0.1:30002; no matching wildcard/IPv6 listener. Run installed helper effective check and all six drift/ownership checks. Run protected guards again.
7. Publish ../exposure-ready.md immediately after successful gated bind with UTC, endpoint, root guard, and unchanged-model evidence. Worker2 owns direct separate-host auth/SSE/agent acceptance after coordinator handshake. No Worker1 generation. Stop at bounded handoff; report-only commit/bundle, correct author/committer, no push.

## Owned resources and inverse

New deliverables: eight files and three parents above. Side effects: exact helper lock, policy receipt, four firewall rules plus one chain, GLM socket boot-intent symlink. Evidence/staging/temp: `/data/services/n1vm-20260915` root0700, root0600 files; no model/state/registry/keys/control source mutation.
If failure after activation: disable/stop ONLY new llm-private-glm.socket then stop llm-private-glm.service; verify all six owned units quiescent, all three sockets disabled. Keep all eight exact files for installed helper remove --dry-run then remove. Never flush. Remove only manifest/hash-proven new files and now-empty new parents after inverse; retain receipt/filter backups and inventory. If blocked before activation, preserve reviewable state and report exact category.
Existing GLM/Docker, Q38V fixture containers, Q38A acquisition/seal assets, obsolete dirty checkout, /tmp artifacts and unrelated host settings remain outside this task.
