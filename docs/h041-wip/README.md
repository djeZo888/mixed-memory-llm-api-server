# Preserved H041 work in progress — disabled

These files preserve important unintegrated worker work for the next chat. They are outside application imports, builds, deployment and service units. **No live GO or production qualification is carried by this directory. Do not execute the recovery helper from this handoff.**

| File | Origin | Disposition |
|---|---|---|
| E-manual-cleanup-ceb847.patch.gz | A ceb847120242896f483102db5eff0ebdaa039b8d | Coherent cleanup direction, but E owns these paths and has not adopted it. Loader must also forward the existing AbortSignal; source acceptance and actual cleanup proof remain pending. |
| A-queued-admission-ca42389.patch.gz | A ca42389b3b1b5c52239bc7ca095840b01dc8d55c | Queued admission synchronous-failure correction, not applied to final root source. Worker retained 1,411 total / 1,406 pass / one fail / four skips, EXIT1, on its separate graph. Review and qualify with the final E graph before integration. |
| fan_recovery.py | E SOURCE10B protected export | Partial one-start recovery/90-second observer; not installed. Requires independent final review and a fresh complete whole-state/failed-owner/BMC/GPU proof before any concrete root GO. |
| test_fan_recovery.py | E SOURCE10B protected export | Fourteen corrected synthetic checks passed; initial twelve pass/one failure/one error retained privately. No Linux/live/physical acceptance. |

Current fan-helper limitations include namespace freezing after its own mutations and ambiguous queued automatic restart ownership when the first start fails before a process birth is observed. Actual abort/owned termination must not infer a PID from expectations. See the [final handoff](../../reports/h041-final-handoff.md).

SHA256 identities are in [manifest](manifest.json). Protected original receipts, helper dependencies, failed checks and raw state stay under orchestration/tasks/H041-20261001 outside Git; no keys or raw credentials are exported here. These files can be reviewed individually without reopening the entire old worker context.

The REJECTED startup09d executor and caller preserve the exact source of the failed/expired invocation. They are not successor launch scripts. The executor has known result-directory contamination, unbounded post-TERM reap and terminal-persistence ordering defects; the original runtime ancestor protection also failed. A future09e must correct these and receive a new packet/GO. The bounded evidence helper and TRACE V2 source plan are reference inputs only, not enabled modes or live proof. No original input/approval/key packet is included.

The final helper review also found no final post-loop physical-owner/readback rejoin after the90-second sequential observation boundary. Treat that as a pending qualification check.

Patches are gzip-compressed to retain their exact original Git patch bytes. Review/decompress privately with `gzip -dc <path>.patch.gz`; use `git apply --check` on the reviewed target before any owner-authorized application. The manifest records both stored and uncompressed SHA256.
