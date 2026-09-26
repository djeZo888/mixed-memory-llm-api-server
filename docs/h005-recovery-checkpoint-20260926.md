# H005 recovery checkpoint — 2026-09-26

**Incomplete; resume from this checkpoint, not from bootstrap.** New implementation, deployment, reboot and inference work stopped during the account/connection incident audit. Ordinary shell checks found no native `codex exec` worker task running on either Mac. Neither VM was changed by this audit.

## Preserved work

- Reviewed integration before this note: `f03915d2b99b4004eabfe34d89dea4dcd2f4bc92`.
- Adaptive 600-second idle policy is deployed to both text schedulers and the Ada image scheduler. Both Qwens retain their 480,000-token configuration.
- Status/admin surfaces, UUID-based service isolation, scoped operations and the boot-validation correction are deployed. See the dated [acceptance report](service-resilience-acceptance.md) for exact component identities and limits.
- Boot correction `cb0fca5` passed 95 focused tests and independent source review; live publication at September 25 22:11:56 UTC preserved all model invocations.
- Private relay diagnostics `142a950` passed 18 focused tests, type checking and source review. Source is committed; **deployment remains pending**.
- Original failures, worker session IDs, immutable bundles, protected backups and raw test records are retained. Raw traces, credentials and chats stay outside Git.

## Recovered idle observation

Worker1's existing observer completed at September 25 **22:39:04 UTC**, after **665.25 seconds**. This audit recovered its existing output; it did not rerun the test. Passive status polling continued, with no observation flags or status errors.

| Scheduler | Mean CPU over final 65 seconds | Maximum CPU | Main thread blocking |
|---|---:|---:|---|
| Qwen GPU0 | 0.314% | 0.4% | Yes |
| Qwen GPU1 | 0.329% | 0.6% | Yes |
| Ada image | 0.843% | 1.0% | Yes |

100% means **one logical CPU**, not the whole VM. Each row uses 14 scheduler-process samples. Both text schedulers transitioned from busy polling after recent work; image was already idle at observation start. Device VRAM stayed constant at 61,018 / 61,050 / 32,238 MiB respectively. Residency is not proof of cache contents. **Post-window wake acceptance is still pending.**

## Remaining work, in order

1. Read current live status and operation journals before resuming. Do not replay an uncertain action.
2. Complete the prepared tiny text wake checks and one qualified image edit; preserve originals and confirm all three models remain warm.
3. Deploy the reviewed private relay diagnostics through the existing scoped deployment procedure.
4. Perform one distinct explicit ai-vm reboot and verify automatic restoration; then the planned ai-harness reboot, preservation and containment checks.
5. Publish the final evidence/report and review PR7. Do not merge main or claim final acceptance before those results exist.

The first ai-vm reboot changed boot but failed automatic Qwen1 restoration; separate manual recovery succeeded. The later relay request at 22:16:46 UTC failed without a canonical VM operation being recorded. Its original precise rejection was not retained; current validators passed. **Its historical cause remains unknown.** Diagnostics are not a claimed fix for an unproven cause.

Do not repeat the completed 665-second observation if idle/runtime bytes remain unchanged. No capacity benchmarks, new models, GPU reassignment, ECC changes or installer work belong to this recovery.

## Resume locations

- Orchestrator: `orchestration/tasks/H005-RESILIENCE-20260925/STATUS.md` and its `incident-recovery/` directory.
- Worker1 native observer: `01a0da7a-046a-79c3-81e5-6bafdf9b0c72`.
- Worker2 native acceptance: `01a0da5a-f10a-7d12-ab52-e6429586ce84`.
- GitHub: Draft [PR7](https://github.com/djeZo888/mixed-memory-llm-api-server/pull/7), `feature/service-resilience`, based on `feature/ai-harness-v0.0.3`.
