# F1A Qwen acquisition continuation

Full acquisition acceptance is pending at handoff unless the final F1A report explicitly records all 48 computed-verified files. No inference is authorized by a download status.

## Durable identities

- Run: `/data/build/f1a-qwen-20260915`; isolated source: `repo/scripts/f1a/`.
- Destination: `/data/models-large/qwen3-coder-next-fp8`; adjacent `.partial` files; owner lock `.f1a-acquisition.lock`.
- Initial unit: `f1a-qwen-fast-acquire-20260915.service`. Inspect the actual unit/PID alongside JSON; neither old JSON nor a directory size proves the owner is alive.
- State: `evidence/acquisition-status.json`; log: `acquisition.log`; source/manifest hashes: `evidence/helper-sha256.json` under the run.
- Qwen manifest SHA256: `022674d4daf63fa57c2798a30fea80c6dde7b1b2e73630ae3c3aa94e45debb9e`; exact [48-file manifest](f1a-qwen-manifest.json), 80,407,722,953 bytes.
- Companion GLM manifest SHA256: `8e7cb419a9dea83f1978f936455cedace1b964cbbb3580f7be191998f6a999d3`. F1A reads actual GLM file sizes to reserve both downloads; it never writes GLM source, state, files, lock or job.
- `/data` UUID `8daf56f1-5649-4163-9d87-919c2d271875`; `/data/models-large` UUID `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`. Both must be actual distinct ext4/rw mounts, distinct from root. Root below 4 GiB stops; retain 20 GiB plus write buffers after both remaining downloads.
- Two streams, 2 GiB service memory cap, nice 10, 36-hour runtime limit, 120-second stop timeout. Transient unit survives SSH exit but **does not survive reboot**. No automatic restart.

## Bounded inspection through worker SSH

```bash
ssh ai-vm 'systemctl show f1a-qwen-fast-acquire-20260915.service --property=ActiveState,SubState,MainPID,ExecMainStatus,Result'
ssh ai-vm 'cat /data/build/f1a-qwen-20260915/evidence/acquisition-status.json'
ssh ai-vm 'TMPDIR=/data/build/f1a-qwen-20260915/tmp PYTHONDONTWRITEBYTECODE=1 python3 /data/build/f1a-qwen-20260915/repo/scripts/d1/storage_guard.py --model-uuid a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a --report /data/build/f1a-qwen-20260915/evidence/root-continuation.md'
```

Do independent useful work before another status sample; do not follow raw logs indefinitely. `download_complete_artifacts` counts exact-length files, not hashes. `sha256_verified_artifacts` counts SHA gates; `fully_verified_artifacts` includes Git-blob gates for the seven non-LFS assets. `verified_weight_shards` counts weights only. A terminal STOP/CANCELLED or stale status is not completion.

## Completion gates

Require `status=PASS_ALL_48_VERIFIED`, `fully_verified_artifacts=48`, `verified_weight_shards=40`, and `fully_verified_bytes=80407722953`; every computed SHA256/size must match the immutable manifest. Seven non-LFS files must also have computed Git blob identities matching the manifest. Confirm exact destination names (48 finals plus owner-lock file), no partials/unexpected entries, the complete 40-shard index, `runtime_asset_contract=PASS_NATIVE_NO_TRUST_REMOTE_CODE`, and final common/strict guards. Inspect current files and evidence, not just a historical success claim.

On integrity mismatch preserve the artifact and STOP/report; do not delete/redownload automatically. If either mount/root guard prevents terminal state writing, the prior JSON can remain stale.

## Resume only after interruption

Confirm the previous specific Qwen unit is inactive, its process has exited, and the Qwen flock is free. Preserve all partials and manifests. Run the same reviewed launcher with a fresh unit suffix; it rechecks both mount identities, exact metadata and fresh combined capacity, rehashes existing finals and resumes partials only after exact HTTP Range validation:

```bash
ssh ai-vm '/data/build/f1a-qwen-20260915/repo/scripts/f1a/launch-acquisition.sh /data/build/f1a-qwen-20260915 022674d4daf63fa57c2798a30fea80c6dde7b1b2e73630ae3c3aa94e45debb9e 8e7cb419a9dea83f1978f936455cedace1b964cbbb3580f7be191998f6a999d3 f1a-qwen-fast-acquire-20260915-next-reviewed-resume 2'
```

Never stop/change GLM to resume Qwen. Record successor unit/PID/start time. F1S owns the SGLang lifecycle adapter and safe auth redaction contract; F1D owns reviewed model activation and actual inference, tool calls, resource fit and endpoint/auth acceptance. See [installed SGLang contract](f1a-sglang-contract.md).
