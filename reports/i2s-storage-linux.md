# I2S actual disposable Linux storage verification

**Status: source prepared; actual hosted execution NOT_TESTED.**

## Scope and source

- Approved base: `e6c77debb4989ada0c7a563159f8df45aa89f7b5`.
- Feature branch: `milestone/i2s-storage-linux`.
- Authorization: taskroot I1S review/handoff and incoming revision1, read at phase boundaries.
- Owned changes: new I2S validation scripts/workflow/tests and this report only.
- No existing installer/lifecycle/writer/storage/helper/workflow changed.
- [Independent source review](i2s-source-review.md).
- [Execution interface and local verification commands](../scripts/validation/i2s/README.md).

The exact shipped I1S dry-run/apply runs only inside the approved I2P-guarded
GitHub-hosted Ubuntu24.04 VM. Mac checks are ordinary-user source/safety checks.
The reviewed wrapper uses protected internally allocated256 MiB backing and its
own private mount namespace. New fixtures additionally verify kernel backing
inode/device. No physical or production device is exposed as a mutation target.

## Validation status before hosted run

| Check | Status |
| --- | --- |
| Exact requested base, feature branch and safe HTTPS remote | PASS |
| I2S safety tests and final source review | PASS:61 I2S tests;97 including reused I2P safety suite |
| Existing Mac disk source suite |34 PASS,1 ERROR in existing final process cleanup; see review |
| Actual Linux GPT/ext4/replay/refusal matrix | NOT_TESTED |
| Actual same-device writer alias and mount loss | NOT_TESTED; I1W known source issue pending |
| Actual parent SIGKILL process adapter | NOT_TESTED |
| Canonical global admission/autonomous child deadline | NOT_TESTED; I1O pending |
| Role-aware data-only persistence/I1c writer conversion | NOT_TESTED; source pending |
| Physical4Kn and production root exclusion | NOT_TESTED |
| Actual package/GPU/model/image installation and reboot | NOT_TESTED |

The fixture distinguishes real Linux tool/mount effects from synthetic topology
and process adapters. Python exceptions after completed tools are not hard parent
death. Disk-local flock is not global admission. Unknown ownership preserves
state and fails cleanup; expected failures/skips never establish acceptance.

## Publication and next action

Source/safety review fixed an early-return cleanup-report persistence bug in the new harness. Regression tests prove missing or uncertain namespace cleanup prevents subsequent loop allocations. All four new probe dry-runs, Python syntax, and shipped-wrapper shell syntax pass on the worker. These are not Linux disk results.

Publish reviewed source with `[skip ci]`, immediately export the full bundle,
then separately push only the new I2S launch marker to trigger one actual job.
This avoids the existing I2P `tests/validation/**` actual-job path trigger.
The final report will bind actual results to the marker SHA/run URL and sanitized
artifact/source hashes. Report production defects to the coordinator for a new
bounded fix; never bypass them or edit concurrently owned source.
