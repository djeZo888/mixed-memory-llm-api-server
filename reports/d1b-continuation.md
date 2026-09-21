# D1b continuation — acquisition acceptance still pending

The bounded optimization is complete when the accompanying D1b report records its measurement. Do not wait in this session for full download. A fresh task should inspect current live state; elapsed time or old JSON alone is not completion evidence.

## Durable identities

- Active successor: `d1-glm53-acquire-20260915-d1b-p4.service`; initial PID `49253`; started `2026-09-14 23:02:39 UTC`; invocation `55ab64073abe462189f82c54ce8e299e`.
- Original `d1-glm53-acquire-20260915.service` was gracefully stopped and its PID 34781 exited before the successor started. The new unit has four distinct shard workers, one process/global flock, MemoryMax 2 GiB, RuntimeMax 36 h, stop timeout 120 s; it is transient and does not survive reboot.
- Reviewed helper source commit `220887d722d1f481f87c246a7e3767cd94b07453`, isolated `/data/build/d1b-glm53-20260915/repo/scripts/d1/`. The deployed `acquire.py` SHA256 is `950334895648a53db8ffef32171f2e97a64bdf6b0c07eed56424a4649a76fcf4`. Do not launch the old sequential D1 helper by accident.
- Existing reviewed state/run remains `/data/build/d1-glm53-20260915`; authoritative state `evidence/acquisition-status.json`; file log `acquisition.log`; manifest `repo/reports/r2-flagship-artifact.json`; ready evidence `evidence/d0b-storage-ready.md`, SHA256 `31b06dda448a3a339e2911c4a51d9da4d2626737589cb4a54fb5bcaa3f702a2d`.
- Approved model: `unsloth/GLM-5.3-GGUF@346b3591c7f28d1a23716f97a065ecf12ec14771`, only eleven R2 UD-Q4_K_XL files, 467289116837 bytes.
- Files/partials and global lock: `/data/models-large/glm-5.3-ud-q4-k-xl/` (shards in `UD-Q4_K_XL/`, lock `.d1-acquisition.lock`). No existing byte was deleted/truncated; the retained 6106906624-byte shard-3 prefix was hashed after stop/before restart and after resume and matched, with the same inode and exact HTTP 206 offset.
- `/data` UUID `8daf56f1-5649-4163-9d87-919c2d271875`; model mount UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`. Root below 4 GiB or wrong/missing mounts must STOP; 20 GiB model spare remains required.

## Bounded read-only inspection

```bash
ssh ai-vm 'systemctl show d1-glm53-acquire-20260915-d1b-p4.service --property=ActiveState,SubState,MainPID,ExecMainStatus,Result'
ssh ai-vm 'cat /data/build/d1-glm53-20260915/evidence/acquisition-status.json'
ssh ai-vm 'python3 /data/build/d1b-glm53-20260915/repo/scripts/d1/storage_guard.py --model-uuid a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a --report /data/build/d1-glm53-20260915/evidence/root-next-acceptance.md'
```

Evidence of this optimization is under new isolated run `evidence/`: `helper-source-commit.txt`, `helper-sha256.json`, both test outputs, `startup.json`, `preservation-check.json`, `measure-start.json`, `measure-end.json`, `measurement.json`, duplicate launch refusal, and final snapshot/guards. Exact before/after-stop inventory is in original run `evidence/d1b-{before,after}-stop.json`. The Mac task sibling files `../acquisition-state.md` and `../runtime-contract.md` provide handoffs for orchestrator/Worker2.

## Completion and failure gates

Final acceptance requires live helper status `PASS_ALL_11_COMPUTED_SHA256`, 11 verified rows and 467289116837 verified bytes, each R2 computed hash and size, exactly the eleven expected finals with no partial/unexpected entries, and final strict/common storage guards. Inspect exact files and evidence; directory byte totals and published hashes alone are insufficient. A STOP/CANCELLED state is not completion; if guards prevent even status writing, the previous JSON may be stale. Preserve mismatch files and investigate rather than redownload automatically.

Do not launch a second owner while any acquisition unit is active/activating/deactivating or its flock is held. Resume only after confirming the previous owner exited and the lock is free, reviewing current status/bytes and rerunning guards. With the same reviewed storage evidence, use the new helper and a fresh unique suffix:

```bash
/data/build/d1b-glm53-20260915/repo/scripts/d1/launch-acquisition.sh \
  /data/build/d1-glm53-20260915 \
  a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a \
  31b06dda448a3a339e2911c4a51d9da4d2626737589cb4a54fb5bcaa3f702a2d \
  d1-glm53-acquire-20260915-next-reviewed-resume 4
```

Worker count 1 is available as a sequential fallback; use it only after stopping the specific current owner safely, preserving all offsets and recording the reason. Full GLM load/inference/tool calls, authenticated readiness, memory fit and lifecycle remain NOT_TESTED and belong to later authorization. The existing completed build job/image are unchanged; CUDA enumeration is not inference proof.
