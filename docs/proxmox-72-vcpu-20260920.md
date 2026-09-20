# VM120: proposed 72-vCPU Proxmox configuration

**Reviewed manual proposal / NOT_EXECUTED — manual instructions only. Nothing here was executed.** Based on the user's topology/configuration attachment, not a fresh host observation. Worker1 completes cleanup/publication and the separately authorized graceful guest shutdown first. No further model benchmark, host automation or pinning hook is part of this proposal.

## Exact proposed topology

Retain VM120's **896 GiB RAM = 917504 MiB**, `balloon: 0`, `cpu: host`, `machine: q35`, both GPU passthrough entries, every disk and network setting. Change only affinity and CPU/NUMA topology:

```text
affinity: 0-63,72-79
sockets: 1
cores: 72
numa: 1
numa0: cpus=0-15,hostnodes=6,memory=114688,policy=preferred
numa1: cpus=16-23,hostnodes=0,memory=114688,policy=preferred
numa2: cpus=24-31,hostnodes=2,memory=114688,policy=preferred
numa3: cpus=32-39,hostnodes=4,memory=114688,policy=preferred
numa4: cpus=40-47,hostnodes=1,memory=114688,policy=preferred
numa5: cpus=48-55,hostnodes=7,memory=114688,policy=preferred
numa6: cpus=56-63,hostnodes=3,memory=114688,policy=preferred
numa7: cpus=64-71,hostnodes=5,memory=114688,policy=preferred
```

The selected mask contains **72 host logical CPUs across all 64 physical cores**, including eight additional SMT siblings on host node6. Both GPUs are attached to host node6 in the supplied output. The guest gets 72 virtual cores, not 72 physical cores. Eight allocations of114688MiB equal917504MiB; guestnode0 gets16vCPUs and each other node gets8.

**What the settings actually guarantee:** `affinity` limits the host CPU set eligible for VM vCPU execution. `numaN.cpus` describes guest CPU membership; `hostnodes` and `policy` configure the corresponding memory allocation. `preferred` permits memory fallback to other host nodes, matching the existing policy. This does **not** pin guest CPUs0–15 to physical CPUs8–15/72–79, reserve host cores exclusively, or guarantee GPU-local execution/memory. No such guarantee is claimed. [Official resource-limit documentation](https://pve.proxmox.com/pve-docs/chapter-qm.html#qm_cpu_resource_limits), [NUMA option definitions](https://pve.proxmox.com/pve-docs/qm.conf.5.html).

One socket with72cores and eight custom NUMA nodes is supported by the current Proxmox configuration model: the official implementation emits explicit NUMA CPU lists independently of socket count; its socket-based layout is the fallback when custom nodes are absent. All proposed guest CPU IDs cover0–71 exactly once. This is source/documentation validation, **not a successful start on the installed version**. [Official NUMA implementation](https://github.com/proxmox/qemu-server/blob/master/src/PVE/QemuServer/Memory.pm).

## Check the installed host before applying

Run these manually on the Proxmox host. No credentials or host address were inferred:

```bash
pveversion -v
qm help set
qm status 120
qm config 120 --current 1
qm pending 120
qm listsnapshot 120
```

Confirm VMID/name, current disk/network/GPU entries, 917504MiB/balloon0, unchanged physical CPU/node enumeration, no unrelated pending edits, no active migration/backup/HA operation and the installed syntax. The pasted excerpt omitted disks/network and the installed Proxmox/QEMU version, so it cannot establish those current facts. Preserve them from the full current configuration. Do not bypass an existing lock or disable HA automatically.

**`vcpus`:** absent in the supplied configuration, so the default proposal leaves it absent. Proxmox uses `cores × sockets` as the maximum CPU count; an explicit `vcpus` can start fewer CPUs. If a current `vcpus` line exists, stop for review: retaining112 exceeds the new maximum and retaining a smaller value may start fewer than72. For an explicitly reviewed all72 configuration, set it to72 in the same command, or remove it deliberately; never silently preserve an incompatible value. [Official CPU/hotplug documentation](https://pve.proxmox.com/pve-docs/chapter-qm.html), [configuration reference](https://pve.proxmox.com/pve-docs/qm.conf.5.html).

## Manual change sequence

Use a root Bash shell, one block at a time. A full VM power-off/start applies topology; an in-guest reboot alone is insufficient for this sequence. If Worker1 has already shut down VM120, skip the shutdown command and verify it is stopped. Otherwise only after the authorized guest drain/cleanup:

```bash
qm shutdown 120 --timeout 300 --forceStop 0
qm status 120
```

If shutdown times out or status is not `stopped`, **stop here**. Do not escalate to `qm stop`, force-stop, kill, or `--skiplock`. [Official shutdown command](https://pve.proxmox.com/pve-docs/qm.1.html).

Back up the full configuration privately, including snapshot sections, only after confirming the stopped state:

```bash
set -euo pipefail
test "$(qm status 120)" = 'status: stopped' || { printf '%s\n' 'STOP: VM120 is not stopped'; exit 1; }
umask 077
vm72_backup="$(mktemp -d /root/vm120-before72.XXXXXX)"
cp /etc/pve/qemu-server/120.conf "$vm72_backup/120.conf"
qm config 120 --current 1 > "$vm72_backup/qm-config-before.txt"
qm pending 120 > "$vm72_backup/qm-pending-before.txt"
pveversion -v > "$vm72_backup/pveversion.txt"
sha256sum "$vm72_backup/120.conf"
printf '%s\n' "$vm72_backup"
```

Keep the printed backup path. Once its configuration/pending-state review is complete, apply all topology fields in **one `qm set` call**; no disk, network, passthrough, CPU type, machine, RAM or balloon field is rewritten:

```bash
test "$(qm status 120)" = 'status: stopped' || { printf '%s\n' 'STOP: VM120 is not stopped'; exit 1; }
qm set 120 \
  --affinity '0-63,72-79' --sockets 1 --cores 72 --numa 1 \
  --numa0 'cpus=0-15,hostnodes=6,memory=114688,policy=preferred' \
  --numa1 'cpus=16-23,hostnodes=0,memory=114688,policy=preferred' \
  --numa2 'cpus=24-31,hostnodes=2,memory=114688,policy=preferred' \
  --numa3 'cpus=32-39,hostnodes=4,memory=114688,policy=preferred' \
  --numa4 'cpus=40-47,hostnodes=1,memory=114688,policy=preferred' \
  --numa5 'cpus=48-55,hostnodes=7,memory=114688,policy=preferred' \
  --numa6 'cpus=56-63,hostnodes=3,memory=114688,policy=preferred' \
  --numa7 'cpus=64-71,hostnodes=5,memory=114688,policy=preferred'
```

If `qm set` fails, leave the VM stopped and inspect the current configuration; do not assume transactional rollback or retry automatically. Review before starting:

```bash
qm config 120 --current 1
qm pending 120
qm showcmd 120 --pretty
diff -u "$vm72_backup/120.conf" /etc/pve/qemu-server/120.conf || test "$?" -eq 1
qm status 120
```

The diff should contain only the reviewed affinity/sockets/cores/NUMA changes. Confirm memory917504, balloon0, both original `hostpci` entries, disks and network are unchanged. `showcmd` must render72 CPUs, all eight guest NUMA ranges and eight114688MiB memory backends with the intended preferred host nodes. It previews the launch command; it does not prove runtime placement. A normal nonzero `diff` exit indicates differences to review. [Official `qm config`, `pending`, `set` and `showcmd` reference](https://pve.proxmox.com/pve-docs/qm.1.html).

After that manual review, start separately:

```bash
test "$(qm status 120)" = 'status: stopped' || { printf '%s\n' 'STOP: unexpected VM120 state'; exit 1; }
qm start 120
qm status 120
```

Then ordinary guest read-only checks should confirm CPUs0–71 online, eight NUMA nodes, expected memory and both GPUs; RAM and PCIe behavior remain unverified until these observations. No inference/benchmark request is part of this check. The existing guest model boot/resume intent must be decided before shutdown; this Proxmox-only change neither alters nor suppresses it.

## Rollback

The saved `120.conf` is a **configuration backup, not a disk/VM snapshot**. For a failed start, keep the VM stopped, inspect the failure, and restore only the original topology values from that backup after verifying there were no intervening edits. The supplied prior values were affinity`8-63,72-127`, sockets7/cores16 and seven131072MiB NUMA nodes; the added `numa7` must be removed. Review a reverse `qm set` against the actual backup instead of overwriting unknown newer settings.

If a real pre-change Proxmox snapshot exists, inspect its date/configuration and disk coverage before considering `qm rollback 120 SNAPSHOT`; rollback can revert guest disk data and is not needed merely to undo CPU topology. A config copy cannot restore disk data, GPU state or an earlier running RAM state. No snapshot rollback, snapshot creation or forced shutdown is included or executed. [Official snapshot/rollback commands](https://pve.proxmox.com/pve-docs/qm.1.html).

Evidence status: **PROPOSED / NOT_EXECUTED**. Installed-version validation, stopped-state checks, configuration backup/change, VM start, actual guest topology, NUMA placement and performance are **NOT_TESTED** here.
