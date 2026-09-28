# Sova current task — H024 Codex implementation

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

All four models are resident and H023 work has settled. Keep MiMo Pro-RL at
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

CHA_FAN3 was commanded and read back at 100%. Physical speed increase remains
unproven because raw tach decreased from 5040 to 2760. Other fan settings are
unchanged. Existing integrated GPU fan boost and the 85°C guard remain. Returning
to the user's 75% baseline requires fresh third-GPU idle/below-65°C proof and an
exact scoped BMC action. No fan sweep or permanent BMC controller belongs here.

Initial implementation sessions last at most 50 minutes, followed by fresh
integration/acceptance sessions. Reserve the final 15 minutes for settlement,
health, reports and publication. Do not extend silently or force a success claim
at the deadline. Keep healthy models resident. Publish source and results on
`feature/glm53-flash` / draft PR10; do not merge incomplete qualification.

H023 records are in the orchestration task files outside this checkout and
`reports/h023-*`. Earlier instructions are archived under `docs/orchestration`.
