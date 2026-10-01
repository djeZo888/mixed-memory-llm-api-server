# H041 worker outcomes

**All 22 launched worker CLI phases are closed.** Eleven ended at their explicit deadline, nine closed cleanly and two failed for capacity. H041 started at 08:05:07 UTC on 1 October 2026. The user requested wrap-up; the overall compaction goal remains incomplete and native acceptance remains NOT_TESTED.

A is mac-worker1, SID `01a0f4d8-9d87-78d0-94cc-5a73d9056be2`. E is mac-worker2, SID `01a0f4fa-aee1-7cb0-8b3d-9fa0577a26c9`. Times below are UTC. “CLI/outer” describes worker process exits, not application or inference acceptance.

| Phase | Mac | Start | End | CLI/outer | Outcome |
|---|---|---|---|---|---|
| A-runtime-integration | A | 08:09:24 | 08:54:45 | -15/143 | Deadline; partial source retained |
| E-compaction-integration | E | 08:09:25 | 09:09:45 | -15/143 | Deadline; partial source retained |
| A-current-preflight | A | 08:57:37 | 09:09:45 | -15/143 | Deadline; partial source retained |
| A-production-compaction | A | 09:13:57 | 10:29:45 | -15/143 | Deadline; partial source retained |
| E-compaction-completion | E | 09:13:57 | 10:21:52 | 0/0 | Clean CLI close; source only |
| A-production-entry-03 | A | 10:30:20 | 10:49:44 | -15/143 | Deadline; partial source retained |
| E-full-retention-03 | E | 10:30:20 | 10:49:41 | 0/0 | Clean CLI close; source only |
| A-production-linux-preflight-04 | A | 10:53:34 | 11:24:45 | -15/143 | Deadline; partial source retained |
| E-full-producer-04 | E | 10:53:35 | 11:24:19 | 0/0 | Clean CLI close; source only |
| A-delivery-preparation-05 | A | 11:30:03 | 12:14:26 | 0/0 | Clean CLI close; source only |
| E-delivery-combined-05 | E | 11:30:04 | 12:13:17 | 0/0 | Clean CLI close; source only |
| A-ordinary-qualified-source-06 | A | 12:23:06 | 13:09:44 | -15/143 | Deadline; partial source retained |
| E-ordinary-qualified-consumer-06 | E | 12:23:06 | 13:09:04 | 0/0 | Clean CLI close; source only |
| A-compaction-completion-07 | A | 13:12:09 | 14:14:44 | -15/143 | Deadline; partial source retained |
| E-compaction-completion-07 | E | 13:12:09 | 14:11:03 | 0/0 | Clean CLI close; source only |
| A-compaction-completion-08 | A | 14:26:59 | 15:24:45 | -15/143 | Deadline; partial source retained |
| E-compaction-completion-08 | E | 14:27:00 | 15:24:45 | -15/143 | Deadline; partial source retained |
| A-compaction-completion-09 | A | 15:26:36 | 16:34:45 | -15/143 | Deadline; partial source retained |
| E-compaction-completion-09 | E | 15:26:36 | 16:34:10 | 1/1 | Capacity; source retained |
| A-compaction-completion-10 | A | 16:35:56 | 16:58:53 | 0/0 | Clean CLI close; source only |
| E-compaction-completion-10 | E | 16:35:56 | 16:36:00 | 1/1 | Capacity before work |
| E-compaction-completion-10b | E | 16:38:11 | 16:57:40 | 0/0 | Clean CLI close; source only |

Deadline receipts explicitly record SIGTERM (-15) / outer 143; these are bounded terminations, not failed test exits. A10 closed at 16:58:53 UTC and E10b at 16:57:40 UTC, each 0/0. Root separately verified same-SID and owned worker PIDs absent at 17:00:17 UTC. Retire both SIDs; use a fresh session for each future bounded SSH subtask.

Source checks remain separate:

| Exact source/evidence | Total | Pass | Fail/error | Skip | Check exit |
|---|---:|---:|---:|---:|
| Earlier A8a reviewed source |1410|1405|1/0|4|1|
| Latest Aca423 source, original retained in A10 |1411|1406|1/0|4|1|
| E5d source, retained historical result |1410|1406|0/0|4|0|
| E10b private helper, first run |14|12|1/1|0|1|
| E10b private helper, corrected run |14|14|0/0|0|0|

A10 was a report-only phase and retained the unchanged failing source suite. E10b strict and helper syntax checks exited 0; its helper fixtures do not qualify the current imported application graph or live fan behavior. There is no current combined full-suite PASS or completed native/manual/full-retention/ordinary/AUTO acceptance claim. Counts from different commits and retries are not summed.

The [JSON ledger](h041-worker-outcomes.json) preserves each launch and terminal receipt path/SHA256, exact timestamps/PIDs, source evidence and the original private-audit provenance. Successor ADOPTED-TERMINALS files close the preceding phase. Two initial adopted closures predating H041 were excluded. All 22 phases have materialized terminal pairs; the process-absence readback is attributed to root rather than independently repeated by this ledger author.

Original audit: `orchestration/tasks/H041-20261001/root-review-acceptance/wrapup-worker-outcomes/PROPOSED-worker-outcomes.json`, SHA256 `9f86b3bc28bc7143bb2525e3522e306fe286a03e1ae58b79dd552ffaafe8bee6`. Final A10/E10b originals were added after that audit. No tests, implementation, VM/live actions or worker launches were performed to prepare this ledger.

During publication, one additional scripted SSH operation on mac-worker2 removed a single trailing blank-line space reported by GitHub D2 whitespace checks (17:08:25–17:08:28 UTC, actual exit0). This did not initiate another Codex session or live action. It is tracked separately in [publication cleanup](h041-publication-cleanup.json); the22 native CLI phase count is unchanged. Initial hosted failure is preserved privately.
