# D3CAP — root storage STOP before native1M attempt

**STOP_ROOT_STORAGE_BEFORE_TARGET_PREFLIGHT. Native1M capacity and sanity NOT_TESTED.**

Fresh mac-worker1 Codex session; exact reviewed base
`dad2d58b57ab2367dee254cff1a885567b0c76f4`. Installer STOPPED. No Worker2 request.

## Actual result

At `2026-09-15T04:41:05.270493+00:00`, fresh root filesystem available capacity
was **3,632,226,304 bytes**, below the **4,294,967,296-byte (4 GiB)** stop threshold.
The authoritative installed registered guard returned exit 1:

> STOP: registered storage identity, ownership, layout or capacity guard failed

The first admission command also failed at this guard. Root's subsequently read
`coordination-input.md` independently ordered no stop/select/start/allocation or
generation. Dependent actions stopped. This task made no AI VM state changes.
The existing N76/32K deployment and retained D1 assets were untouched by D3CAP;
current backend identity/readiness were not independently reverified after STOP.

| Stage | Evidence |
| --- | --- |
| Installed registered guard and dependency | Exact supplied SHA256, root ownership, protected ancestry and modes 0755/0644 passed before first guard invocation |
| Registered storage/root guard | FAIL; no fallback used |
| Target Manager.prepare_start | NOT_REACHED |
| Full pretransition PSS | NOT_REACHED |
| Canonical lifecycle lease | Never acquired |
| Stop/select/start/allocation | Zero attempts |
| Load telemetry, actual 1M/F16/fusion/cache/compute/PID | NOT_TESTED |
| Tiny ordinary smoke | Zero requests; NOT_TESTED |
| Occupied 1M/client/boot acceptance | NOT_TESTED |

Only the explicitly permitted read-only diagnosis followed the failed admission:
registered root guard, statvfs root capacity, and file metadata under
`/var/lib/systemd/coredump`, `/var/tmp`, `/tmp`, `/var/log`. The scan included
regular files at least 64 MiB with mtime in the preceding 7200 seconds, without
following directory symlinks or reading file contents. It returned no matches.
This does not establish the cause of root consumption. No deletion or remediation
was attempted. No report parent or task file was created on ai-vm because the
first guard failed before those operations.

## Intended contract; not measured by this task

The authorized target remains the already-staged
`glm-5.3-ud-q4-k-xl-n76-native1m`, one 1,048,576-token slot, N76, split 1:1,
manual/restart=no, loopback 127.0.0.1:30002, alias glm-5.3. Its source readiness
budget is 7200 seconds. Runtime `llama-cpp-v0.4.1-d3br` is bound to Docker/OCI index
`sha256:86feba4c82a8ec083d8da31fb8d1648f7b221b724a48eca571f5dd277a0caab9`.
These are reviewed inputs, not live allocation evidence. No installed source,
closure, registry, instance, key, network, service or boot intent was changed.

D3PERFVM's durable release records 04:32:17.515611Z, zero owned processes and
unchanged 32K identity. This task did not reach its planned fresh quiescence check;
that prior receipt is not presented as current evidence. No full PSS, sampler,
request, tunnel or transition process was started here. Both bounded read-only
SSH processes completed.

## Ownership and next action

Sole request/lifecycle task ownership RELEASED at `2026-09-15T04:43:31.246982+00:00`,
after both SSH processes completed. The diagnosis timestamp is separate.
See `d3cap-evidence/lease-release.md`. No automatic VM action or retry is scheduled.
The allocation allowance is unconsumed. Root coordinates storage diagnosis and
remediation; a fresh passing registered guard and root's release/reassignment
are required before dependent work resumes.

No rollback was needed or invoked. Existing N76/32K and stopped D1 containers,
profiles, source and evidence remain untouched by this task. The established D1
rollback command remains in the sibling D3N32 final report; no fallback settings
were invented here.

## Verification and retained evidence

Report-only change; no source/framework/installer implementation and no test
suite. Relevant source/handoff review, exact-base check, bounded live guard and
metadata observations, report diff/whitespace review, quiet grep secret scan,
author/committer verification and bundle verification are the applicable checks.
No model weights, key, body or raw prompt is included. Task-local preparation and
failed-admission stderr remain outside Git for continuation.
