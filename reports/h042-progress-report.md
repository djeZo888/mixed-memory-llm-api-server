# Sova progress report — 1 October 2026

**The two immediate live goals remain unresolved:** CHA_FAN3 is not fixed on the host, and the first native no-generation startup/owned-shutdown gate has not run. Context compaction is not qualified end to end. The work below is tested source progress, not a completed live repair.

This reports the roughly three-hour H042 run beginning 17:44:17 UTC, as of 20:36 UTC. We will keep this conversation as the working context; this is an outcome report, not a chat handoff.

## Completed and verified

| Item | What was completed | Practical limit |
| --- | --- | --- |
| Existing state | Adopted saved worker/download state and protected credentials. Preserved Sova runtime pins, accepted histories, uncertain owners and normal services. | No downloads replayed or whole model weights rehashed. |
| Codex updates | Verified all three Mac desktop apps at 26.928.31416/build12553. New worker sessions actually used CLI 0.159.2, GPT 6.1 Sol, Ultra. | Linux Sova stays pinned at 0.158.0/upstream064c; it was not upgraded. |
| Worker execution | Eight fresh isolated SSH worker sessions completed; actual terminal exits were 0/0 and recorded processes/PGIDs were absent. Original failed checks were preserved. | A02 and Fan05 missed export targets, while closing before hard deadlines. No old SID was resumed. |
| Reviewed source publication | Integrated reviewed changes and pushed source HEAD `e5ecf127d327f371ba34f758ed73591fa1574083` to [draft PR11](https://github.com/djeZo888/mixed-memory-llm-api-server/pull/11); exact remote HEAD verified. | Source was not deployed or merged. |
| Ada readback | Both 48GB Adas were present and idle at 34–36°C, with no compute jobs. Accessible current-boot guest logs showed no matching Xid/fallen-off-bus/AER errors. | No image/OCR workload, sustained link or cable test. Host/rotated logs were not qualified; ECC counters are disabled/N/A. |

## Fixed or completed in source

| Change | Result and evidence | Live status |
| --- | --- | --- |
| Abort and failure cleanup | Abort reaches entry loading; original failure/settlement evidence is retained instead of being hidden or promoted to success. 85 source checks pass. | Not deployed. Early failure cleanup is still unproved in one important branch. |
| Authenticated cold adoption | Same-parent verification occurs before the first native open. Genuine IPC/new-child source fixtures and 100 checks pass. | Native cold restoration remains NOT_TESTED/default-disabled. |
| Retained-history verification | Verifies exact source-derived SQLite/WAL constructor repairs while preserving unrelated rows, fields and history. Actual Store reopen plus 102 independently corrupted copies pass. | Existing live owners/history were not reconciled or rewritten. |
| Queued admission race | The pending admission gate is installed before a synchronous failure can occur. Three queued regressions and 27 production-memory checks pass. | Not deployed. |
| Minimal startup tooling | Current-window protected source/artifact/issuer/cleanup checks are prepared. A-startup01/02/03 pass 31/27/39 synthetic tests respectively. | Native invocation count is zero; no staging/native GO was issued. |
| Requested CHA_FAN3 curve | Implements 40% duty below 70°C, 80% at 70–80°C, 100% strictly above 80°C; immediate raises and 30s fresh lower-tier dwell. Startup/fault/stale/missing telemetry command 100%. 70 controller tests pass; static review found no policy blockers. | **NOT_INSTALLED / NOT_FIXED.** Duty percentage is not a tachometer RPM percentage. |
| Fan recovery tooling | Corrected protected UID1000 credential reading, 30s baseline, clocks after reads, fixed-start polling and finite recovery-budget checks. 82 private-graph tests pass. | Actual credential/BMC access, recovery and physical stability remain NOT_TESTED. The baseline reads actuator configuration once, so continuous configuration stability is unproved. |

The C4 focused checks and server typecheck/build pass. Its full suite remains **1,548 total / 1,541 passed / 3 failed / 4 skipped**, exit 1. The three failures are existing Mac Unix-socket path-limit fixtures; the four native opt-in tests remain skipped. No full-suite or native PASS is claimed. See [C4 details](h042-c4-queued04.md) and [fan source details](h042-fan05.md).

## Still unresolved

1. **First native startup and verified shutdown.** Failure before a launch receipt can race private process capture or omit original producer/scope/settlement facts. This remains UNKNOWN, not successful cleanup. A private polling workaround cannot guarantee every branch. The next implementation needs a narrowly reviewed durable producer/scope receipt before child launch and authentic failure settlement on every postfork error, preserving original failure status. Then requalify the current combined source and perform the single bounded no-generation call. The old frozen A03 candidate cannot implicitly include later C4 changes.
2. **Actual context compaction.** Manual/full retention, ordinary native turns, repeated compaction, genuine 400K automatic compaction and browser/UI acceptance remain untested. TraceV2 source work was not started. These remain behind the first startup/shutdown gate.
3. **CHA_FAN3 live repair.** The host controller remains unchanged, failed/stopped, PID 0/exit 78 with `competing_writer_or_overwrite`. The user-reported 2,800–5,000 RPM cycling every 10–15s is unresolved. No BMC authentication/PUT, latch clear, install or restart occurred. The next fan task must review the sealed recovery graph, obtain fresh bounded BMC/thermal/owner/config evidence, qualify owned recovery, install the new source and independently observe stable behavior. Other fan channels and integrated GPU fan policy must stay intact.
4. **Ada model operation.** Keep the user's Razer Core X/certified 40Gbps 0.5m USB4 cable baseline. Intended allocation remains external Ada for **Qwen-Image-2.1**, stable Ada for **Qwen3.5-9B BF16 + PaddleOCR-VL-1.6** image-to-text/OCR. Both allocations, sustained cable/link stability and throughput need actual workload tests. External guest x4 versus stable x16 is not proof of a bad card; physical slot2/slot5 UUID mapping remains unproved. No card problem was observed in the limited idle evidence.

## Where this run fell short

The work concentrated on source fixes, failure/ownership guards and their verification. It did **not** deliver the requested physical fan repair or clear the first live compaction gate. Repeated private-wrapper work did not remove the underlying early producer-evidence gap. The next startup implementation should address that producer contract directly, with fan recovery proceeding as a separate bounded task from its now-tested source. Do not spend another run replaying bootstrap, rechecking unchanged downloads or recreating a chat handoff.

The working context and protected originals remain available in this conversation and `/Users/agent/Documents/LLMServer/orchestration/tasks/H042-20261001/`. [Worker results](h042-worker-sessions.json) retain actual SIDs/terminal/absence times; original source bundles, hashes and failed logs remain private. Existing approvals are expired/spent/withdrawn; any live action still requires a concrete current approval of its exact source and owner state. Pins remain **480000 context  / 400000 auto-compaction  / 65536 output**; credentials and histories are preserved.
