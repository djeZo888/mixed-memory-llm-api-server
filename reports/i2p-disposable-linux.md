# I2P — disposable Linux validation environment

**PASS: actual hosted Ubuntu systemd/cgroup/flock and blank-loop primitives.**
**Installer, I1R watcher, I1S storage integration, apt, GPU and reboot acceptance:
NOT_TESTED.** Coordinator revision 1 selected ephemeral GitHub Actions Ubuntu
24.04 instead of a new Mac guest. No production server was accessed.

## Executed identity and evidence

- Branch: `milestone/i2p-disposable-linux`; approved coordination base
  `75a6bf915f30a1582348071eb733d05c33e10eb7`.
- Tested source: `781106406b9cc626756f83c3b063b8b15e9dcbb8`.
  The final documentation commit retains identical probe/workflow source.
- [Actual I2P run 34913638300, attempt 1](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34913638300):
  **success**, 2026-09-15 00:33:02–00:33:10 UTC. Probe duration 0.637 seconds.
- Artifact: `i2p-evidence-34913638300-1`, ID `10374813045`, 2,452 bytes,
  GitHub digest `sha256:e6a90a2a2d897be233950373a9483a035dd770eb9ba91b635ba7ce781079ef73`.
  Expires 2026-09-29 00:33:06 UTC. Contains only `evidence.json`,
  `source-manifest.json`, `plan.json`; collected privately outside Git.
- ImageOS `ubuntu24`, ImageVersion `20260907.300.1`;
  [observed image software manifest](https://github.com/actions/runner-images/blob/ubuntu24/20260907.300/images/ubuntu/Ubuntu2404-Readme.md)
  and [image release](https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20260907.300).

`ubuntu-24.04` is a **rolling image label, not an immutable full-VM checksum
pin**. This coordinator-selected route records actual image metadata and pins
actions/tested source to commits; it does not claim a reproducibly pinned Ubuntu
cloud-image disk. GitHub provisions a fresh x64 VM for each job; the container
label `ubuntu-slim` is not used.
[Runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[image lifecycle](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners).

## Real Linux observations

| Check | Actual result |
| --- | --- |
| OS / architecture | Ubuntu 24.04.5 LTS, x86_64 / dpkg amd64 |
| Kernel / VM | 6.17.0-1022-azure; systemd-detect-virt: microsoft; container gate refused containers |
| Privilege / resources | UID 0 inside disposable VM; 4 CPUs; 16,372,440 KiB RAM |
| systemd / cgroup | PID 1 systemd; systemd 255.4-1ubuntu8.17; cgroup v2 |
| Controllers | cpuset, cpu, io, memory, hugetlb, pids, rdma, misc, dmem |
| Temporary free space | 92,402,962,432 bytes before; 92,394,348,544 after |
| Launcher normal exit | Exit 0; descendant stayed in same owned service cgroup and retained exclusive flock |
| Launcher SIGKILL | Exit -9; launcher reaped; descendant retained cgroup membership and exclusive flock |
| Unit cleanup, both cases | Exact InvocationID, cgroup and MainPID start identity verified; owned cgroup removed; lock reacquired |
| Blank loop | Only newly allocated /dev/loop0, major:minor 7:0, backing path/inode/filesystem verified; root ancestry excluded |
| Sparse allocation | 67,108,864 logical bytes; 0 allocated before format; 8,531,968 allocated after format |
| Filesystem proof | Actual ext4 creation, identity/UUID-checked mount, marker write/read PASS |
| Loop cleanup | Exact owned mount unmounted and loop detached; backing preserved for job lifetime |

The generated filesystem UUID was `35ff4c17-6e69-4150-9353-0fe4d33ca448`,
mount ID 61. These are evidence from a discarded job, **never reusable device
selectors**. Run identity `i2p-3b3f059a78d74e38b09cef878169b4a5` named both
transient services and the private sparse file. Root/system disks were never
formatting candidates. No loop image or raw runner logs were committed/uploaded.

The fake-package probe deliberately keeps a harmless supervisor as MainPID.
A child launcher exits or self-SIGKILLs while its descendant holds flock.
It proves real Linux primitives, **not** I1R watcher survival, borrowed-lease
semantics, policy restoration or a service whose MainPID exits.

## Worker capability and scope decision

Read-only Mac-Worker2 metadata: macOS 26.6.2 arm64, 32 GiB RAM, 10 CPUs,
`kern.hv_support=1`, UID 502, initially 1,927,343,759,360 bytes free (about
1.75 TiB). QEMU, UTM, Lima, Multipass, Docker, Podman and alternative runners
were absent from PATH and bounded standard install locations. Homebrew installed
package inventory and application names confirmed no guest runner. A process-name
search matched only unrelated input-method names, not a running VM.

The task's `incoming.md` revision 1 superseded local guest creation and explicitly
prohibited local virtualization installation. No host package, disk image, SSH key,
QMP socket, forwarded port or persistent guest was created. Mac actions ran as
ordinary UID 502. Root-only test actions ran inside the disposable hosted VM;
no production-host container or host device/directory was exposed to a guest.
No auth files, raw environment or global app configuration were inspected.

Read AGENTS, current orchestration/installer plans and available I1/I1b/I1R
interface reports. L1/I1R/I1b and live F1D continued independently. No ai-vm access,
apt transaction, service enablement, boot change, model/runtime/GPU work or
installer/lifecycle/auth/controller/client edits occurred.

## Reusable interface and controls

[Launch, source copy/run, observe, collect and stop instructions](../scripts/validation/i2p/README.md).
A reviewed feature push launches the job; checkout copies its exact source SHA.
`runnerctl.py` verifies repository, workflow path, branch, event, run ID and SHA
before status/rerun/collection/cancellation. No interactive SSH endpoint exists.
The initial launch, status and evidence collection were exercised; cancellation
identity dry-run passed. Actual cancellation/rerun execution was not needed and
remains untested. There is **no running guest to stop** after this completed job.

The workflow uses a minimal explicit root environment, no secret inputs and
`persist-credentials: false`. It pins checkout v6.0.2 to
`de0fac2e4500dabe0009e67214ff5f5447ce83dd` and upload-artifact v7.0.1 to
`043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`. Job/probe timeouts are 10/4 minutes.
Each transient service has RuntimeMaxSec 60, KillMode control-group, private
network/devices, 64 MiB memory and eight-task bounds. Unit output is null and
helper environment is cleared. Directories/files are private 0700/0600.
[Ubuntu systemd execution documentation](https://manpages.ubuntu.com/manpages/noble/man5/systemd.exec.5.html).

Normal probe completion and caught failures use identity-checked cleanup.
Unknown/recycled ownership refuses destructive cleanup and fails the result.
Hard cancellation can bypass Python cleanup; runtime bounds and disposal of the
entire hosted VM contain those cases. Backing files are preserved until VM
teardown; only the three sanitized JSON files survive as a 14-day artifact.

## Checks and next action

| Check | Result |
| --- | --- |
| Local Mac safety/refusal suite | PASS: 36 tests; includes real temporary-file hardlink/symlink/inode tests and synthetic device/unit refusal cases |
| Local main/loop dry-run, Python syntax, owned Markdown links | PASS; no Mac Linux device operations |
| Independent source review | PASS after fixing helper path visibility, partition topology and unknown-allocation cleanup reporting |
| Actual hosted safety suite and both primitive probes | PASS at the exact tested source above |
| [General CI](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34913638214) | success at tested source |
| [D2 lifecycle regressions](https://github.com/djeZo888/mixed-memory-llm-api-server/actions/runs/34913638241) | success at tested source |
| Hosted source manifest versus local source | PASS: all four Python file SHA256 values match |
| Changed-file grep secret scan, ownership scope, whitespace, credential-free remote/helper | PASS before each feature push |
| Author and committer | CodexAIagent <133749519+djeZo888@users.noreply.github.com> |

Validation commands are in the linked interface. Final commit, full bundle hash,
remote verification and final documentation CI are recorded in taskroot handoff
files. No main push or production change is part of I2P.

**Next:** coordinator reviews/merges this harness, then I2R/I2S run reviewed actual
watcher and storage modules in a fresh bounded job. Retain capability and identity
gates. Actual installer/package integration and full fresh-host GPU installation,
inference and reboot remain **NOT_TESTED**. Successful environment readiness is
not installer or full-host acceptance.
