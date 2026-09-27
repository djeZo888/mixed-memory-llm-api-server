# H016 Worker1 phase2 immediate notice — 11:30:17 UTC

Fresh native session `01a0e2a0-51da-7153-8b13-ebee943bc8f8`, CLI `0.158.0-alpha.2.1`; wrapper start 11:29:12 UTC, hard session deadline 12:04:12 UTC. Source 943d21c0b8d249a9f72a8b80a3b8de5031ace17a.

First compact actual read: initial unit invocation `2ce0a1b765cd47cfa6df437483612e4f` is FAILED, MainPID=0, Result=exit-code. OWNER error `loaded_build_model_template_mismatch`. Native loaded at elapsed 47.951s with one 131072 slot, listening only 127.0.0.1:30012. No TEXT/TOOL/WARM4K/BENCH4096/qualification results. No duration projection is supported.

Exact candidate `0b6ba7cefa9bec95e6d7cb5793a827fae0f5aa42b1f4a68a4f5f135b1089a992`, native PID1699112, StartedAt11:26:21.501071502Z, exited at11:27:15.133325754Z, PID0/OOMKilled=false. Owner saved cgroup-empty/GPU-compute-empty settlement at11:27:15.343605Z, GLM restored at11:28:36.991013Z. Actual GLM service loaded/active/exited; runtime mask removed. Supervisor PID1695832 absent and unit cgroup gone. The persistent supervisor performed validation and cleanup AFTER prior CLI exit11:26:56; it is no longer running. This is post-exit execution/settlement evidence, not alive-now survival.

No retry, rebuild, download, new request, ladder or live adoption. Investigating exact failure evidence for a narrow root-reviewed fix; source-only persistent owner and passive node preparation continues.

## Root-approved r2 dispatch packet — 11:39 UTC

Approved exact effective-template repair and fresh namespace only. New BASE `/data/build/H016-20260927/worker1-r2`, LOG `/data/logs/H016-20260927/worker1-r2`, candidate `llm-h016-mimo-pro-r2`, unit `h016-mimo-initial-20260927-r2.service`. Original sources, stopped container and owner/log receipts retained. Three focused repair checks + syntax/whitespace PASS. No adoption/node draft is included in this launch. Immutable image and native argv unchanged. Original verified receipt is read directly; no rehash. Production17 fixture shape/native count only; no production-size generation. Deadline13:25 admission/13:40settle unchanged.

Material diff in `repo/reports/h016-20260927/worker1/phase2/REPAIR.diff`; added `native_identity.py` and `test_repair.py`. Exact staged-source hashes:
```json
{
  "candidate_owner.py": "621d8eb04cd9aeac12b9769b3bc7b00c2269928cb2f8f7bb14a7a77bbd2bcde5",
  "benchmark.py": "8cd27c4839328c5ba3187d58d270e7504cb7fecc75b3827b4ce8cd233325702b",
  "private_proxy.py": "82d88ed7e13de4a4a36b1a74a4186927e7e03a5380e109860e4e076f3baeb50c",
  "telemetry.py": "df2c572fba760c963886a80a4a534c12b3c817465efc4a54aa85e01a72c7f39f",
  "verify_retained.py": "dfb4479239129f7909ce54827cdd15a14215cebdc60da6e4e5939a995ead250f",
  "native_identity.py": "0ba1f5781585ba887bd639e950870976e0ecb159caa674cb72dfa41cc48d3518",
  "inspect_gguf.py": "bc76625dc1e370db29036fc8218eac82bea414e73dce6daa2b3bd43e650acba4",
  "LAUNCH.json": "9f96098b3c491b9e22602144c5fa2f3ac7d706e7f41103a8f3539171e19bb211"
}
```

## R2 dispatched; post-dispatch SSH-exit proof

"2026-09-27T11:39:29.967671+00:00" UTC launch.

```json
{
  "observed_utc": "2026-09-27T11:39:47.678679+00:00",
  "owner": {
    "candidate_id": "dff50683e03a6568a711bc15219be0190115066aa7ff2360919814e1df44c813",
    "glm_suppressed": true,
    "memory_limit_bytes": 759135469568,
    "native_cgroup": "/sys/fs/cgroup/system.slice/docker-dff50683e03a6568a711bc15219be0190115066aa7ff2360919814e1df44c813.scope",
    "native_pid": 1921878,
    "native_started_at": "2026-09-27T11:39:45.479666175Z",
    "old_glm_settled_utc": "2026-09-27T11:39:44.708937+00:00",
    "pid": 1918783,
    "post_glm_baseline": {
      "MemAvailable": 918780424192,
      "MemTotal": 946820976640,
      "SwapFree": 3104305152,
      "SwapTotal": 3157258240
    },
    "started_utc": "2026-09-27T11:39:31.876403+00:00",
    "status": "LOADING"
  },
  "unit": "MainPID=1918783\nControlGroup=/system.slice/h016-mimo-initial-20260927-r2.service\nActiveState=active\nSubState=running\nInvocationID=c2f28671f5de4674b526a2fe92e0fba3\n",
  "supervisor_proc_exists": true,
  "container": {
    "Id": "dff50683e03a6568a711bc15219be0190115066aa7ff2360919814e1df44c813",
    "Image": "sha256:cdb6efd75f53a8b453f866f30511b0f5c8d19440d3adaaf419e97bde1c2bf21e",
    "Name": "/llm-h016-mimo-pro-r2",
    "State": {
      "Status": "running",
      "Running": true,
      "Paused": false,
      "Restarting": false,
      "OOMKilled": false,
      "Dead": false,
      "Pid": 1921878,
      "ExitCode": 0,
      "Error": "",
      "StartedAt": "2026-09-27T11:39:45.479666175Z",
      "FinishedAt": "0001-01-01T00:00:00Z"
    }
  }
}
```
No native qualification or first4K result yet claimed.
