# H026 ai-harness guest shutdown

Normal guest poweroff accepted; SSH closed and TCP22/HTTP became unavailable. Host-side power state was not independently queried.

- Worker: mac-worker2.local. Native session `01a0e9e5-5156-7632-bdb5-03eb4fcd0566`, PID 20461.
- Start: 2026-09-28T21:21:54.617659+00:00; hard deadline: 2026-09-28T21:29:54.617659+00:00; receipt: 2026-09-28T21:25:29.354884+00:00.
- Exact clean source: `d5a456ac3f87115750bc0e639609c16348599531`. No code edits or builds.
- Explicit root/W1 release SHA256: `308e7a5a46c09be7052181b6046aaa368d87ff3f05a41361f665f6c1d3c25cfe`.
- Guest `aiharness` / `10.156.100.61`; boot ID `a80a9860-7fde-4483-abc4-00903793c201`.
- Current read-only ownership: zero active application runs; all 118 gateway requests settled; gateway lanes idle; no running native task containers. Three historical quarantines and two historical uncertain engine bindings preserved. Only search container running. No active unknown application work found.
- App/status already inactive. Normal stop commands both exited 0; both Result=success, MainPID=0, inactive, still enabled. Search/model/state configuration and persistent SQLite/chats/files/secrets/holds/quarantines untouched.
- Fan service was active before shutdown; normal systemd guest teardown and existing stop fail-safe retained, without direct fan writes.
- Selected current-boot journal exported before disconnect. Bounded live journal stream returned SSH exit 255 / remote closure and **no shutdown-target messages**. Final fail-safe execution was not independently observed.
- `sync` exited 0. `sudo -n systemctl poweroff` ACK exit 0: guest timestamp 21:24:20 UTC; Mac command 21:24:19.762–21:24:19.982 UTC (subsecond clock offset retained).
- External checks from mac-worker2: TCP22 still reachable at 21:24:20.986 and 21:24:22.205; final check beginning 21:24:23.397 timed out on TCP22 and TCP80; public `/api/health` returned HTTP000/curl28. HTTP was already unavailable with services paused.

Evidence: `SHUTDOWN-RECEIPT.json`, `stop-services.*`, `current-boot-selected-journal.*`, `shutdown-journal-stream.*`, `sync-poweroff.*`, `external-disappearance.json`, and compact initial/ownership readbacks. No hypervisor confirmation or claim that shutdown-target messages were seen. No host/Proxmox/BMC/new-hardware actions or GitHub publication. Native session closes immediately after this receipt; no follow-on work.
