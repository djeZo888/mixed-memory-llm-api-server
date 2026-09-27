# R4 terminal load failure and exact recovery

R4 mandatory telemetry continued across the old60second placement boundary. Last successful sample12:26:55.249771: owned swap0; OOM/oom_kill0; hostavailable383776641024B; cgroup533473447936B, predominantly531016941568B shmem; frontier57969MiB free/35C, all GPUs<=39C. These measurements precede the failure and do not prove later physical state.

The mandatory GPU query subsequently raised TimeoutExpired. This is unavailable mandatory GPU telemetry, not a demonstrated temperature or reserve breach. The guard interrupted the exact owner. Systemd records mainexit12:27:18 and ExecStopPost exit12:27:28; candidate stop completed later12:27:59.25659636, PID0, OOMKilledfalse. Original settlement timed out before asynchronous native stop completed, leaving GLM runtime suppression and no terminal owner receipt. No native readiness/identity/qualification/request receipt exists; inference body was not sent, and no4K ran.

At12:29 checkpoint unitMainPID0/ControlPID0; candidate exactID/image/start retained. Worker1 independently checked nativePIDabsence, originalcgroupempty and frontierGPUcomputeempty, then launched a bounded systemd recovery that invokes only the same hash-pinned r4 candidate_owner.py --settle. This uses the original guarded lifecycle and GLM unmask/restore path, with no owner reset, candidate recreation, source mutation or retry. Its exact invocation is in RECOVERY-LAUNCH.json.

The source correction remains narrowly reviewed and regression-tested. Large explicit loading had not reached ready; no viability or throughput conclusion is supported. Further loading attempts require a new root decision; none is running from this task.
