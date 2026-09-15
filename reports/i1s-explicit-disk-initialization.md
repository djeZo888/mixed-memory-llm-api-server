# I1S — explicit generic blank-disk transaction

Date: 2026-09-15. Status: **SOURCE PASS; REAL LINUX LOOP NOT_TESTED**.
Full fresh-installer readiness remains pending I1b integration and independent I2
execution. No ai-vm access, SSH, real disk access, formatting, package installation,
service/driver changes, model operations or reboot was performed by this task.

Base: `722050fdcb6de4a9f56a5488b705998a1d82ce85`.
Branch: `milestone/i1s-explicit-disk-initialization`.
Author and committer: `CodexAIagent <133749519+djeZo888@users.noreply.github.com>`.

## Implementation and integration contract

[Full API, journal schema, recovery and commands](../docs/install/disk-initialization.md).

- New `scripts/install/disk_init.py`: `plan(storage, *, io=None)` is read-only;
  `initialize(storage, *, io=None)` returns the actual registered storage snapshot.
- Existing source changes are confined to `Storage._disk_plan` and the initialize
  branch at the start of `Storage.adopt`. Runner, main stages, package/inhibitor,
  anchored storage writes, acquisition/runtime and lifecycle modules are untouched.
- Saved exact by-id/serial/WWN/byte-size/config/shape plan; explicit basename
  confirmation; fixed protected `/etc/local-ai-server/disk-initialization.json`.
  Schema1 contains transaction ID, full plan, plan/config hashes, intended disk GUID,
  PARTUUID, filesystem UUID/label and stage. Intent is durable before GPT/mkfs.
- Stages: prepared → gpt_intent → gpt_done → fs_intent → fs_done → mount_intent →
  mounted → complete. Only blank media may be initialized. Full-device zero scans,
  dual raw GPT CRC/identity checks, exact ext4 metadata and read-only fsck govern
  reconciliation. Foreign/partial metadata stops; no wipe/force recovery exists.
- One aligned GPT/ext4 filesystem, explicit UUID/label,4096-byte blocks, `-m 0`;
  nested models share it. Separate models require existing/UUID mode.
- Stable UUID mounting, protected underlying mountpoint, unchanged existing-mode
  adoption for directories/registration, byte-prefix-preserving fstab append.
  Completed replay verifies mount/registration/fstab and never reformats.
- Disk-local child commands retain the transaction flock and device descriptors;
  timeouts terminate/reap the process group before failure. No success receipt is
  granted for failed or surviving-child outcomes.

## Checks and evidence

| Check | Result |
| --- | --- |
| All installer source tests: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/install -p 'test_*.py' -q` | PASS —125 tests |
| Dedicated transaction suite | PASS —31 tests, including subcases for all8 stages and GPT/mkfs/mount pre-receipt crashes |
| Regular-file raw GPT/ext4 parser fixtures | PASS —4 tests, 512/4096-byte GPT, both copies/CRC/IDs, middle foreign bytes, ext4 UUID/label/size/reserved fields |
| Fstab preservation and completed no-op | PASS —old bytes, credentials/payload preservation, entry conflicts/removal, unchanged journal/registry/fstab on replay |
| Root/boot, serial/size/config/plan drift, holders, LVM/RAID, foreign/ambiguous IDs, symlinks and journal protection | PASS —synthetic refusals |
| Inherited-child lock and exited-leader/grandchild timeout fixtures | PASS —ordinary local Python processes only |
| Linux loop wrapper Bash syntax, Python AST, help and companion dry-run | PASS —static/read-only checks |
| Loop wrapper prerequisite dry-run on Mac | EXPECTED STOP —`NOT_TESTED: Linux is required.` |
| Real GPT/ext4/mount execution | **NOT_TESTED** |
| Exact storage.py seam AST check and diff whitespace check | PASS |
| Local grep-based staged secret scan; credential-free remote URL check | PASS |

The old blank-disk checkpoint tests were replaced with dedicated transaction
coverage and narrow dispatch tests; unrelated storage tests remain intact.
No mocked formatting result is evidence of actual ext4/GPT behavior.

## Warnings and next action

1. I1b must integrate the helper by removing its currently frozen
   `main.run_boundary()` initialize-only Pending check under the canonical L1
   lease. The main full-apply readiness gate is unchanged. Public CLI initialization
   remains blocked at this base until that integration occurs.
2. Bootstrap availability of util-linux/e2fsprogs/udevadm belongs to I1R/I1b.
   I1S checks prerequisites and installs nothing. New scoped disk commands live in
   DiskIO, without expanding the generic read-only Runner boundary.
3. Run `sudo ./tests/install/loop_disk_transaction.sh --apply` only in an approved
   disposable Linux environment after its `--dry-run`. It creates and guards its
   own sparse backing, loop, namespace, mount, journal and cleanup. Its explicit
   loop/serial/container-root adapters do not prove production host exclusion.
4. Exclusive kernel-use prechecks must be released before tools acquire their own
   claims. No force/in-use bypass is used. A privileged concurrent administrator
   remains outside this transaction lock; honor an exclusive maintenance window.
   Kernel-uninterruptible I/O may outlast a timeout while ownership is retained.
5. Whole-device zero scans are intentionally conservative and bounded to3600s per
   scan. Slow/nonzero "blank" media is refused. Interrupted malformed GPT/ext4
   requires review; the helper never guesses or force-repairs it.
6. Existing Storage.adopt directory-write anchoring is an I1b-owned integration
   responsibility. This source task does not claim to solve that separate race.

Deliverable: incremental `../I1S.bundle`, excluding the base history. Apply the
milestone branch over the stated I1 base, reconcile only the frozen seam with
I1b, and retain the NOT_TESTED evidence boundary until I2 has executed the fixture.
