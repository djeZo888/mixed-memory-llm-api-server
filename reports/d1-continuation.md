# D1b continuation — acquisition final verification

D1 runtime image is built and CLI/CUDA enumeration passed. The durable acquisition remains on ai-vm. Do not start a second downloader while its unit is active. No D3 deployment is authorized by this continuation.

## Identity and paths

- Run: `/data/build/d1-glm53-20260915`; isolated implementation: `repo/scripts/d1/`.
- Acquisition unit: `d1-glm53-acquire-20260915.service`, initial PID `34781`.
- Build unit: `d1-llama-build-20260915-r2.service` completed; initial PID `30604`. `build.exit=0`; final image ID in `evidence/image.iid` and committed runtime proof.
- Model mount UUID: `a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a`; existing `/data`: `8daf56f1-5649-4163-9d87-919c2d271875`.
- R2 manifest is `repo/reports/r2-flagship-artifact.json`; revision `346b3591c7f28d1a23716f97a065ecf12ec14771`, eleven shards / 467289116837 bytes.
- Destination: `/data/models-large/glm-5.3-ud-q4-k-xl/UD-Q4_K_XL`; final entry `GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf`.
- `evidence/acquisition-status.json`, `acquisition.log`, reviewed `evidence/d0b-storage-ready.md`, and its SHA in `evidence/d0b-ready.sha256`.
- External D0B source handoff: `/Users/agent/CodexProjects/llm-orchestration/tasks/D0B-20260915/storage-ready.md`. Final PASS was read and independently checked in D1.

## Bounded status and final gates

Run through SSH; do not dump environments, auth configuration or signed download URLs.

```bash
cd /data/build/d1-glm53-20260915
python3 repo/scripts/d1/storage_guard.py \
  --model-uuid a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a \
  --report "$PWD/evidence/root-d1b-check.md"
systemctl show d1-glm53-acquire-20260915 \
  --property=ActiveState --property=SubState --property=MainPID \
  --property=ExecMainStatus --property=Result
cat evidence/acquisition-status.json
```

Do useful independent checks before another bounded status check. Do not follow raw logs indefinitely. A stale DOWNLOADING JSON is not evidence of a running process; inspect the unit too. A stopped/killed job may have no final status update. The unit has a 36-hour maximum and does not restart on boot.

Full acceptance requires `status=PASS_ALL_11_COMPUTED_SHA256`, `verified_shards=11`, `verified_bytes=467289116837`, each computed hash and file length equal to R2, no unexpected GGUFs/partials, and final common/strict guards PASS. Inspect actual files and the final evidence. Preserve mismatch files and report STOP; do not delete/redownload automatically. Do not treat metadata or directory byte totals as computed integrity evidence.

## Resume after interruption only

First confirm the previous unit is inactive and repeat exact mount checks plus D0B evidence review. Then run the task launcher with a fresh unit suffix:

```bash
cd /data/build/d1-glm53-20260915
repo/scripts/d1/launch-acquisition.sh "$PWD" \
  a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a \
  "$(cat evidence/d0b-ready.sha256)" \
  d1-glm53-acquire-20260915-d1b
```

This revalidates pinned metadata and rehashes existing finals. Partials resume in place only after exact HTTP Range validation; they stay on the new disk. Never change the UUID to bypass a guard or move partials onto old `/data`/root. Record the new MainPID/unit/start time in progress documents.

## Runtime verification/rebuild

The exact tested image is `sha256:6866856c573d69d504f82265321b182f631a7b3912a1ed1b4efbf893729d4e62`. Full raw version/help/device outputs and CMake/package identity evidence are under `evidence/`. Proof hashes are committed in `reports/d1-runtime-proof.json`. Normal continuation does not need a rebuild.

If a reviewed change requires rebuilding, use `repo/scripts/d1/build-runtime.sh "$PWD"` inside a fresh bounded systemd transient job with file logs under this run. The script requires the existing clean pinned upstream Git checkout, validates source/fix ancestry and storage roots, pins base digests and Ubuntu snapshot, builds with eight jobs, then runs network-disabled CLI/device checks and after guards. It never starts an inference service. Preserve prior attempt evidence before reuse.

D1's actual version string has upstream default `-dev` suffix/build 62 but exact released source commit. Do not silently relabel it. Full model loading, GPU execution under GLM, Jinja tool calls, readiness/authentication, performance and lifecycle acceptance remain **NOT_TESTED** until later milestones execute them.
