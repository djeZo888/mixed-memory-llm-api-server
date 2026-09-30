H025-MIRRORFIX01 source-only completion

Commit: `2ecd1704e51f17ae33d2c2093bcb6a0a23236234` on `h025-mirrorfix01`.
Package SHA256: `01ed8314a50e2f3dea9dc14c9cd014315d689257c7238ef728d9acb26f9d9ca6`.
Base: `6079d748e556c48d5fbb7ce1ba573a96042861ad`; imported deployed baseline commit `ca5b3d8` exactly reproduced supplied package `f567cc8ac3b8a4e8685139d0be594aa50f8965c604b98a611a44a9fef6538a13`. Only baseline contract clocks differed. Historical receipts retained.

Fan reader allows at most three fresh reads through unchanged AnchoredRoot.read_json, only after one of two known replacement faults and guarded before/after identities differ. The same held root guards every attempt. Invalid current owner/private mode/hardlinks/symlinks, missing names, malformed JSON and mount faults fail. Freshness, TTL, identity and fan validation remain unchanged. No shared storage module edits.

Monitor diagnostics contain static allowlisted storage codes, recognized numeric errno and sample/observe-persistence/tick stage; arbitrary exception messages/paths/codes are omitted. Absolute admission/settlement literals are 20:42/21:00 UTC. Existing duration caps remain; fixture uses actual planned settlement 20:58 UTC and rejects later bounds appropriately. No GO or campaign created.

Validation: PASS 25 focused reader/monitor/fan-validation/clock tests; PASS compile 18 Python files; PASS git diff checks; PASS full-history bundle verification. The real os.replace fixture observes nlink0 on the old open descriptor, invokes the original shared check, reproduces StorageIOError invalid_storage_file_or_hardlink, then proves corrected coherent fresh reread. Synthetic mountinfo fixtures do not claim live Linux mount qualification. Original campaign cause remains unproven.

Artifacts: `driver/` exact source/tests, `package.json`, `focused-tests.log`, `compile.log`, `COMMIT.txt`, complete `H025-MIRRORFIX01.bundle`, base-to-head `H025-MIRRORFIX01.diff`, deployed-baseline `CORRECTION-ONLY.diff`, hashes in `RESULT.json`. Early artifacts and initial failed fixture log retained. Initial local corrections fixed the diagnostic set wrapper, fixture import cwd/stub, and clock expectation to preserve the existing settlement duration cap. Final focused run passed.

No VM/BMC/model/network access, deployment or live test. Root reviews; W2 owns live recovery/qualification. Worktree clean at completion.

Latest 20:32 inbox diagnostic clarification applied in final commit; final focused suite and compile rerun after that change. Earlier complete artifacts retained under PRE-OBSERVE names.

Root integration: reviewed exact worker source and passing receipts, then
cherry-picked ca5b3d84, acf2f533 and 2ecd1704 as d810c00, 983c323 and a782064.
Root did not run implementation tests. The source-only report is distinct from
the subsequent corrected live campaign; its result belongs to that campaign.
Bulky/private artifacts remain in task storage outside Git.
