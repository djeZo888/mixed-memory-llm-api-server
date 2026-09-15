# B1S: current ai-vm staging handoff

**SOURCE ONLY.** These are later B1VM owner checks, not work executed by B1S.
Installer work is stopped. No general provisioning, ai-vm requests or reboot are
part of this handoff. Worker1 current-VM validation is a separate gate.

## Owned asset manifest

Verify from the reviewed B1S checkout with:

```sh
sha256sum -c reports/b1s-owned-assets.sha256
```

The manifest hashes only these owned assets:

| Source | Existing-host destination/use |
| --- | --- |
| `scripts/lifecycle/llmctl.conf` | `/etc/tmpfiles.d/llmctl.conf`, root:root 0644 |
| `scripts/control/llm-control.service.in` | Render only `@REGISTERED_DATA_ROOT@` from protected registration; `/etc/systemd/system/llm-control.service`, root:root 0644 |
| `scripts/lifecycle/boot_unit.py` | Existing `render_boot_unit(binding, source_root, instance_path)` produces `/etc/systemd/system/llmctl-boot.service`, root:root 0644 |

`llmctl-boot.service` in the source directory is documentation, not an installable
unit. Generated host unit hashes are not known here; B1VM records them after
rendering with refreshed host facts. Never enable a placeholder.

## Required inputs before existing-host apply

- Freeze the final reviewed normal source, explicit two-model profile file set,
  measured image binding and real receipts from **D3TR + D3PD + context acceptance
  owners**. These inputs are **PENDING**. Preserve GLM-5.3 UD-Q4_K_XL and
  Qwen3.8-27B-FP8 identities; existing test context names are not final selections.
  Do not blindly copy every deployment or turn configured context into acceptance.
- Refresh `/etc/local-ai-server/storage.json`, exact data/model mounts, root
  filesystem device, installed source roots, instance path, unit/drop-in state,
  canonical lease, saved intent and stopped receipts. No historical UUID/path
  observation is authority for apply. No registration overrides or disk changes.
- Retain the L2 protected control root `/usr/local/lib/llm-server/control-api`,
  its reviewed `scripts/control/source-closure.json` contract and separate normal
  resources. Keep its final Manager/profile bytes equal to the final protected
  data release. Preserve `/etc/llm-server/control.json` and the existing dedicated
  root control key `/etc/llm-server/control-api-key`; no regeneration, disclosure,
  key hashes or substitution with an inference key.
- The boot stop root is separately `/usr/local/lib/local-ai-server`. Its exact
  file set must equal `boot_unit.RECOVERY_FILES` (11 files), with byte equality to
  the same final data release. Do not put manifests inside it or add Q38 fixtures.
  Validate its actual isolated `boot-stop --help` import with cwd `/`, `-I -B`.
  Refresh normal imports against the final owner-supplied closure separately.

## Exact existing-host checks, in the coordinated idle slot

B1VM must stop on any failed check or missing owner input. Before and after
staging/deployment run the reviewed source's two existing guards, with output
recorded only under verified registered data logs:

```sh
scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh
```

Inspect actual units and drop-ins; preserve N1 transport/firewall/socket files:

```sh
systemctl cat llm-control.service llmctl-boot.service
systemctl show llm-control.service llmctl-boot.service \
  -p FragmentPath -p DropInPaths -p UnitFileState -p ActiveState -p SubState \
  -p After -p Requires -p Wants -p BindsTo -p RequiresMountsFor
namei -l /run/llmctl /usr/local/lib/local-ai-server /usr/local/lib/llm-server/control-api
namei -l /etc/llm-server/control-api-key /etc/tmpfiles.d/llmctl.conf
```

An absent boot unit/rule/directory is an inventory result before staging, not a
pass for activation. Reject symlinks, unexpected mounts, writable ancestors,
non-root owners, hardlinked/nonordinary source files and unexpected tree entries.
Use `lstat`/`namei`, Linux `stat` and `findmnt --target` to verify the *files*, not
just their top directory. Both root source trees and source key must have the
same `st_dev` as `/`; directories root-owned and not group/other writable,
source/unit/rule files root:root single-link, key root:root 0600 single-link.
Preserve the final reviewed source's per-file Git modes: Python/JSON read files
tracked as `100644` remain `0644`; declared executable entrypoints tracked as
`100755` retain `0755`. Unit and tmpfiles rule files remain `0644`. In the already
declared file sets, this includes `0755` for `scripts/common/require-data-mounted.sh`,
`scripts/common/root-disk-guard.sh`, `scripts/common/registered-storage.py` and
`scripts/llmctl`. Do not flatten source modes to `0644`: directly invoked shell
guards require executable permission. This does not expand any source closure.
The instance stays protected root0600 on its exact registered services path.
`render_boot_unit` checks protection/byte equality but does not prove root-device
placement. Recheck the final launch timeout is below the rendered 3h budget.

Before adopting `/run/llmctl`, require a real root:root 0700 directory on `/run`,
protected ancestors, and existing lock/recovery records accepted by the canonical
lease/Manager readers. Record directory and `lifecycle.lock` device/inode, private
modes, recovery bytes and persisted intent. Do not repair an unsafe path in place.
Under the existing held canonical lease, install only the verified directory rule
as root:root 0644 and run the same explicit command twice:

```sh
systemd-tmpfiles --create /etc/tmpfiles.d/llmctl.conf
systemd-tmpfiles --create /etc/tmpfiles.d/llmctl.conf
```

Verify exact rule bytes `d /run/llmctl 0700 root root -` plus newline. After each
call the directory/held lock inode, recovery record and journal must be unchanged;
a nonblocking competing canonical lease must still report busy. Release the lease
before any service start/stop (those operations acquire it themselves). Never use
`--clean`, `--remove`, a lock/journal tmpfiles rule, cleanup age, replacement, or
`RuntimeDirectory=`. An unsafe existing rule/conflict requires owner review.

Once all final closures are protected, render the boot unit with the existing
renderer and control with only the registered data root substitution. Review the
actual unit diff, including drop-ins, before installation. Then check on Linux:

```sh
systemd-analyze verify /etc/systemd/system/llm-control.service /etc/systemd/system/llmctl-boot.service
systemctl daemon-reload
systemctl show llm-control.service llmctl-boot.service \
  -p After -p Requires -p Wants -p BindsTo -p RequiresMountsFor -p ExecStart -p ExecStop
```

Require both units after `systemd-tmpfiles-setup.service`; control has no data
mount or boot-oneshot dependency. Boot retains Docker/exact registered mount
ordering and binds, protected data start/root stop, `RemainAfterExit=yes`,
`restart=no` containers and original budgets. Compare pre/post saved intent
byte-for-byte during staging. B1VM may enable these **validated actual units** in
the idle slot using `systemctl enable llm-control.service llmctl-boot.service`
without `--now`; do not alter unrelated sockets or boot owners by assumption.

Any controlled start/restart acceptance is a separate idle-slot action. For an
active validated control unit, verify its installed credential binding without
printing credentials or sending an inference request:

```sh
cd /
/usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/control/serve.py --check-binding
```

This must report `binding_validated` / `listener_started:false`; the existing
validator checks the protected source key against the systemd credential copy.
It does not prove sandbox access or backend readiness. Check shared inode/journal
continuity across controlled control restart, mount-loss recovery and both final
models with Worker1 acceptance; do not interrupt D3TR/V3 live clients.

## Intent and rollback checks

- Control switches currently select **manual** boot policy. Enabling units changes
  neither that policy nor saved running/stopped intent and proves no reboot recovery.
  Only selected + desired running + resume replays at boot; empty selection,
  manual/running and stopped/resume do not. Unit activation does not make a
  stopped/failed backend Ready. Control remains `Restart=no`.
- `boot-stop` needs a coordinated idle slot: it stops the selected trusted owned
  container even under manual policy, while preserving intent. Disable-only changes
  future activation. `disable --now`, stop or restart can invoke `ExecStop` now;
  never use them blindly during inference. Rollback must preserve the shared
  directory/lock/journal, credentials and intended selection.
- `/run` stopped receipts are volatile. A `state_persisted:false` stop must be
  repeated through the existing stop path after registered storage returns, with
  persistence confirmed before reboot. Power loss destroys volatile recovery;
  missing storage after cold boot cannot reconstruct a trusted identity from it.
- Actual tmpfiles/systemd runtime and reboot recovery: **NOT_TESTED by B1S**.
  Later Linux validation and an explicitly authorized reboot are distinct gates.
