# Sova current task — H025 fan hysteresis and overlap

The user now authorizes a focused fan-control task and a four-model concurrent
test, including GLM 5.3 Flash in place of unavailable MiMo. This supersedes the
H024 no-fan-controller/no-thermal-test/no-GLM restriction only for H025.
Window: 28 September 2026, 18:50–21:00 UTC. The20:16 campaign failed on a monitor
storage error. A20:23 bounded reproduction identified an atomic status-file read
race. Root authorizes one focused reader/diagnostic fix and one reviewed corrected
campaign: startby20:37, admissionsendby20:42, settlementby20:58;900srequest plus60s
stopreserve. Preserve original failure. No further repair/retry/automaticextension.
Root plans,
reviews and publishes; both Mac workers execute fresh bounded native sessions.
W1 owns integrated 100% >=70 C / firmware profile <=65 C and CHA_FAN3 80% >=70 C /
40% <=65 C, preserving the user-disabled CPU source and holding state in between.
W2 owns GLM readiness, compact monitoring-driver repair, independent review and
the eventual five-minute overlap with both Qwens and the image model. Coordinate
live changes centrally, preserve credentials/history and keep the 85 C guard.
No Codex work, MiMo repair, large-context prefill, drivers, model/runtime upgrades
or permanent Sova frontier-policy change. Task plan/status live outside this
checkout under `orchestration/tasks/H025-20260928`.

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
