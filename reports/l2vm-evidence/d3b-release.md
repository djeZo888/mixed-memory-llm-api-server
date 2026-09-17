# D3B top-level ownership release — RELEASED; BUILD FAILED

D3B has finished its ONE authorized Docker build attempt. No further direct children under `/data/build`, `/data/hf-cache`, `/data/backups`, or `/data/logs` are required. L2VM may proceed with its approved nonrecursive owner-only changes, preserving gids, setgid, content and inodes. D3B continues evidence work only inside its owned run.

- Run: `/data/build/d3p-d3b-20260915`, user:ai, mode 2770, inode 44302940.
- Unit: `d3b-glm-cuda-build-20260915.service`; launch 2026-09-15T02:58:36Z; final failed/exit-code, ExecMainStatus=1, MainPID=0; Restart=no, bound 12h.
- Historical observed active process chain: main 202062 -> exact reviewed runner 202064 -> sudo 202547 -> Docker 202548 -> buildx 202651. The entry guard was behind the observed Docker child. Those PIDs are historical, not live ownership claims.
- Build started 2026-09-15T02:58:39Z, failed 2026-09-15T02:58:50Z. Failure is before compilation: checked helper `git apply --check --index` reported that src/llama-context.cpp and tools/server/server.cpp do not match index inside Docker COPY context.
- Runner build.state=FAILED_BUILD_OR_STORAGE; build.exit=1; job.exit=1. Runner final storage guards PASSED. No new IID/image proof exists.
- `/etc/local-ai-server` was absent immediately before launch and still absent at post-failure verification. No registry mutations by D3B.
- Preserve this run, partials and all build caches. No automatic retry, patch changes or bypass. A later invocation after registry-parent creation must refuse at ENTRY; a reviewed source/runner continuation is needed.
- Metadata correction: systemd transformed inline $$ to literal $, so job.pid initially contained `$`. The authoritative initial PID is recorded in evidence/unit-launch.txt as MainPID=202062; final status uses systemctl. No job restart. An earlier short-lived handoff described the observed active phase; this terminal update supersedes it.
