# Active H028 — added Ada and status recovery

The user confirmed both VMs are reachable after the MAC-based NIC-name fix and
requests verification/fan control for the new Ada, an explicitly authorized third Qwen at200K with7%
reserve, and status-page repair. This new scope supersedes H026/H027's closed
windows. Read `docs/h028-added-ada-status-plan.md`. Root coordinates/reviews;
W1 owns ai-vm writes; W2 owns ai-harness status recovery/source and coordinates
ai-vm patches with W1. Fresh bounded native worker sessions, isolated copies.
Window ends September29 00:10UTC; stop new inference00:00, report gaps honestly.
No frontier repair, driver/ECC/power changes or broad stress/context benchmarking.

# Latest checkpoint — H026 complete; both guests shut down

H026 measured both warm Qwen GPUs at 600/550/500/600 W, plus one discarded
warm-up per card. All ten requests settled at 21:18:54 UTC on September 28,
2026. Actual input was about 64K tokens with 512 output; configured capacity
stayed 480K. At 500 W, complete requests took 6.5%/3.8% longer. Output speed
changes were within baseline drift. Peak temperatures were 74 C/73 C, with
no guard fault. See `reports/h026-overview.md` and the linked compact evidence.

Original configured/enforced 600 W limits were restored and read back. No
persistent 500/550 W policy was installed. The user requested both VMs shut
down to add another Ada. Worker1's ai-vm poweroff succeeded at 21:20:08 UTC;
SSH closed at 21:20:11. Worker2's ai-harness poweroff succeeded at 21:24:20;
SSH/web became unavailable and the journal connection closed at 21:24:29.
Hypervisor power state was not independently queried. The user should confirm
VM120/130 show Stopped before powering down the host. Histories/files/configs
were preserved; no more live work is scheduled.

Worker sessions all exited 0:
- W1 execution: 01a0e9d7-255c-7153-907a-b9136e22c032, 21:22:59 UTC.
- W2 review: 01a0e9d7-f14b-74e0-89db-66798f81319b, 21:13:37 UTC.
- W2 shutdown: 01a0e9e5-5156-7632-bdb5-03eb4fcd0566, 21:25:37 UTC.

W1 commit 046f1e2 was integrated as 972f739: compact benchmark evidence,
narrow client dispatch/timestamp corrections and three boundary tests. W1
reported 17 focused tests passed; root reviewed source/results without rerunning
tests. The pre-dispatch raw-directory mode failure was preserved. No accepted
request replay or runtime stop was needed. Raw traces remain private on Mac.

The user's next hardware/restart instructions determine subsequent work. Do not
start GPUs/models, run stress tests, repair services, persist caps, start VMs or
operate Proxmox automatically. Do not revive older expired task windows. Fan
policies remain unchanged. MiMo remains selected but absent; GLM was the retained
test fallback before poweroff. Root plans/reviews/publishes; workers implement,
test and operate VMs. Publish to feature/glm53-flash / draft PR10; do not merge
incomplete qualification.

# Previous checkpoint — H025 closed

Execution closed on September 28, 2026, at 20:59:33 UTC. Final worker2 native
session exited 0; its wrapper and watchdog are absent. Worker1's final source
session also exited 0. Do not restart the expired campaign or open a new paid
session simply to wait. Root reviewed and integrated the supplied evidence.

Fan control is deployed: CHA_FAN1 is exclusively BMC/user-controlled from
PCIe2/PCIe5 temperatures. Existing NVIDIA integrated fans boost to 100% at 70 C
and return to firmware control at <=65 C for 30 seconds. Sova's CHA_FAN3 service
uses only the server Blackwell temperature: 80% at >=70 C, 40% after <=65 C for
30 seconds, holding the prior setting between thresholds. CPU source stays off.
The natural external hot/cool transitions and idle/lifecycle checks passed.

The corrected five-minute campaign is a SOFTWARE FAIL, not a full four-model
functional pass. Qwen0/Qwen1 completed 162/124 requests and image completed six.
An unsent Qwen0 request at the cutoff unnecessarily stopped its runtime; GLM's
16,268-token request timed out after 900 seconds with no response bytes. All
accepted work was physically settled; separate owner reconciliation retained
original failed/UNKNOWN history. No automatic repair or workload retry.

All four native model services were restored and reported ready at 20:58:11 UTC;
app/status HTTP 200, search retained, external fan healthy at 40%. Readiness does
not retroactively qualify GLM inference. Retained GLM was test-only: permanent
frontier selection remains MiMo generation12, and MiMo was not started or repaired.
Both Qwens remain 480K, retained GLM 1,048,576, image Full HD. Histories/files and
three old quarantines were preserved. No new benchmark client or bridge remains.

See `reports/h025-overview.md`, `reports/h025-exec05-20260928/SUMMARY.md`, and
`reports/h025-power-20260928/README.md`. The full300s sampled three-Blackwell sum
averaged843.74W and peaked1172.43W; peak GPU temperature75C. These are board
readings, not whole-PSU or worst-case qualification. CPU400W or200-250W figures
are user planning allowances, not measured CPU power.

The user asked about 500W caps. Read-only limits confirm both workstation cards
support150-600W and server card300-600W. Current/default/enforced remain600W.
NO power caps were changed. A proposed500/500/200W Qwen/Qwen/frontier profile
and adding anotherAda are discussion only; no hardware/cap-performance task ran.

Root coordinates/reviews/publishes; mac-worker1/mac-worker2 perform actual coding,
builds, tests and VM operations in bounded native CLI sessions with isolated
copies. Publish to feature/glm53-flash / draft PR10; do not merge incomplete
Codex/frontier qualification. Next work requires a newly assigned scope/window.

## Previous H024 checkpoint

**Bounded execution closed.** Both final worker sessions exited cleanly by
18:38:41 UTC. The reviewed app is deployed, but Codex's full live qualification
is incomplete and MiMo is absent. Read `reports/h024-codex-checkpoint.md` and
`reports/h024-codex-results.json`. Do not restart the expired window or repeat
tests automatically; the next work needs a newly assigned bounded task.

The user authorizes a separate two-hour Codex implementation window after H023:
**September 28, 2026, 16:52–18:52 UTC (18:52–20:52 Ljubljana).** Root plans,
reviews, integrates and publishes. mac-worker1 and mac-worker2 perform coding,
builds, tests and VM work through fresh bounded native Codex CLI sessions and
isolated copies. Retain task/session IDs and compact durable results.

Use `ai-harness/PLAN-CODEX-COMPLETION.md`. Worker1 owns readiness after reboot,
both Qwen qualifications, provider/gateway/MiMo integration and needed ai-vm
supervision changes. Worker2 owns Responses/tool/PDF compatibility, context/UI
and the single combined ai-harness deployment. Agree shared provider interfaces
before edits. Root reviews combined source before deployment; ordinary assigned
edits and focused checks are already authorized.

H023 work has settled. At H024's start all four models were resident; MiMo
later stopped at 18:04:30 UTC after a canonical-lease guard timeout. Do not
treat its static qualification receipt as current readiness or blindly restart
it. See `reports/h024-acceptance02-20260928/CONTROL-REFRESH-FUTURE-FIX.md`.
Keep MiMo Pro-RL configured at
950,000 configured tokens, both Qwens at 480,000 and the existing Full HD image
profile, with the same weights, runtimes and GPU assignments. No 950K test,
thermal retest, new model, hosted fallback, driver/runtime upgrade, GLM
restoration or Proxmox change. The first MiMo 16K request completed; 950K remains
configured capacity, not qualified occupied context. Preserve histories, files,
native IDs, old failures and uncertain-request evidence. Reconcile holds through
their owners; do not delete historical quarantines or replay work.

App/status were intentionally paused for H023. Worker2 restores them during the
coordinated release and health checks. MiniMax remains available and default;
qualify Codex capability by capability. Do not accept arbitrary changed runtime
identity, hide tool failures, strip unexplained arguments or silently rescue a
failed acceptance prompt. Record PASS, FAIL and NOT_TESTED honestly.

The user removed CHA_FAN3's CPU-temperature source and physically confirmed that
cycling stopped. Preserve this working setting. H024 Worker1 made no BMC writes;
the requested GPU-driven 40% below 70°C / 80% at or above 70°C policy remains
unimplemented. Existing integrated GPU fan boost and the 85°C guard remain.
No fan sweep or permanent BMC controller belongs here.

Initial implementation sessions last at most 50 minutes, followed by fresh
integration/acceptance sessions. Reserve the final 15 minutes for settlement,
health, reports and publication. Do not extend silently or force a success claim
at the deadline. Keep healthy models resident. Publish source and results on
`feature/glm53-flash` / draft PR10; do not merge incomplete qualification.

H023 records are in the orchestration task files outside this checkout and
`reports/h023-*`. Earlier instructions are archived under `docs/orchestration`.
