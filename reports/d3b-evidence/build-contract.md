# D3B early build contract

Status: FAILED before compilation at 2026-09-15T02:58:50Z; one authorized attempt consumed. No restart. Historical launch MainPID=202062, Docker=202548, buildx=202651; current MainPID=0. Top-level ownership is RELEASED; see ownership-release.md.

- Run: `/data/build/d3p-d3b-20260915` (new; user:ai, mode 2770, inode 44302940).
- Clean owner repository: `repo/` at `48a982420561ad6d0189a710a228beb1e2838de7`.
- Clean upstream context: `source/` at `b29c606e28a01b1bc8c1351026a0fa6e616bf6c4`, tree `950999fe62b7fe55f44ab5b7394e3c8542f37f12`.
- Combined patch SHA256: `43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b`.
- Prospective verified tree: `0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e`.
- One exact invocation: `/data/build/d3p-d3b-20260915/repo/containers/llama-cpp/build-d3p-runtime.sh /data/build/d3p-d3b-20260915`.
- Planned transient unit: `d3b-glm-cuda-build-20260915.service`, user:ai, 12h bound, no restart.
- PID: `job.pid`; unit evidence: `evidence/unit-launch.txt`; log: `build.log`; runner status: `build.state`, `build.exit`; outer completion: `job.exit`, `job.finished` (all under run).
- Unmodified reviewed recipe, named context, jobs8, `120a-real`, pinned CUDA 13.2.1 base digests and Ubuntu snapshot 20260914T000000Z.
- Planned tag: `local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-43e4aeb5b63d`.
- All new source/tmp/cache/log/evidence paths stay inside the run; Docker/containerd existing data roots remain `/data/docker` and `/data/containerd/root`. HOME unchanged.
- Canonical protected guards from `VM-GUARDS.json` passed after exact path/root ownership/hash verification. Both exact UUIDs and root >=4GiB passed. Registry parent absent at preflight; will recheck immediately before launch.
- No model load, generation, endpoints, GPU access, existing container changes, installer, registry mutation, no-cache or pruning.
- Restart after registry-parent creation is prohibited without new reviewed continuation; entry guard must not be bypassed. In-flight final common guards may select registered-host semantics; report any failure precisely and preserve produced image/proof.

## Measured terminal result

Docker stage build 7/7 reached the checked patch helper, then git apply reported index mismatch for src/llama-context.cpp and tools/server/server.cpp. Clean host preflight passed; no CUDA compiler was reached and no image IID was produced. Runner and outer exit=1; final runner storage guards passed. Existing GLM container remained running on the exact original image. No help/version container was created because no new image exists. Root must review the source/COPY/index continuation before another build.
