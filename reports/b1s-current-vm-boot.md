# B1S — current-VM volatile directory and boot ordering

**PASS: bounded source preparation. Live apply and reboot NOT_TESTED.**

Baseline: `5e713441d9ea164b81860ee795c5ef35972ee8e3`; branch:
`milestone/b1s-current-vm-boot`. Read AGENTS.md/current scope and supplied B1
review-plan; ownership/progress recorded outside Git at session start, incoming
checked at phase boundaries. No ai-vm contact, installer tasks/workflows, service
activation, model/image/native build/download, or contact with D3TR/V3 clients.

## Source result

- One tracked `scripts/lifecycle/llmctl.conf` contains exactly
  `d /run/llmctl 0700 root root -` plus newline; destination
  `/etc/tmpfiles.d/llmctl.conf`.
- Existing boot renderer and control template explicitly order after
  `systemd-tmpfiles-setup.service`. No Manager/lifecycle behavior, control
  dependency, lock/journal ownership, credential or recovery-closure change.
- [Owned asset hashes](b1s-owned-assets.sha256) contain only the rule, renderer
  and control template. [Existing-host staging checks](../docs/lifecycle/b1s-current-vm-staging.md)
  retain the exact 11-file root stop tree, protected L2 root control tree and
  separate existing credentials. No generated host unit or final profile/image
  identity is asserted here.

## Focused verification

[Selected checks and result](b1s-focused-tests.json): **35 PASS**, zero failures,
errors or skips, Worker2 Darwin. The initial 17 changed-test checks also passed.
One expanded invocation initially failed to import an existing test helper because
`tests` was absent from the runner path; fixing the invocation yielded 35 PASS,
with no production correction needed. No full repository/installer suite ran.

| Check | Evidence boundary |
| --- | --- |
| Exact rule bytes; both unit orderings; no removable runtime directory ownership or control data/model-load dependency | Source/unit parsing, not Linux unit validation |
| Manual/running, stopped/resume, empty selection do not replay; running/resume starts once across repeated boot-start under one borrowed canonical lease | Actual Manager with synthetic storage/Docker/probe fixtures |
| Control switch returns to manual policy; stop/restart receipts preserve intent | Actual control/Manager over worker loopback HTTP and synthetic backend observations |
| Fresh directory creation is private; repeated create-if-absent acquisition cannot bypass held lock; directory/lock/recovery inode and bytes plus durable journal survive controlled application restart | Real worker filesystem/flock and production lease directory semantics; **not a tmpfiles emulator or actual systemd restart** |
| Both GLM and Q38 trusted identity labels stop only the owned ID with registry/data/models/config/key absent; boot-stop retains running/resume intent with `state_persisted:false` | Existing synthetic identity fixtures; no final model/context/image acceptance claim |
| Isolated actual 11-file boot-stop CLI and separate L2 recovery/normal imports | Copied source imports only, no native execution or fabricated real receipt |
| False volatile stopped receipt wins over stale primary; missing recovery refuses; failed/exited backend never becomes Ready | Existing persistence/readiness regressions |
| Fixed control credential/source binding and mismatch rejection | Disposable fixture credentials and protected local files; installed binding NOT_TESTED |

Reproduce only the selected checks from the checkout (Python standard library):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=scripts:tests:tests/lifecycle python3 -m unittest -v $(python3 -c 'import json; print(" ".join(json.load(open("reports/b1s-focused-tests.json"))["selectors"]))')
```

`git diff --check` and the three-asset hash check passed before commit. The final
committed source and full `B1S.bundle` receive the same selected checks, scope,
metadata, filename-only credential scan, whitespace and clean-tree gates; their
commit/bundle identities and post-commit results are in the external source
handoff to avoid a self-referential committed report.

## Remaining inputs and next action

- **PENDING:** D3TR corrections, D3PD measured image binding, final accepted GLM/Q38
  context profiles and real receipt closure from their owners. The normal data
  release and root control Manager/profile bytes must match that final review.
- **NOT_TESTED:** actual `systemd-tmpfiles`, Linux units/sandbox/credential runtime,
  cold `/run` recreation, host service restart/mount loss, final two-model live
  acceptance and actual reboot. Worker2 has no suitable existing Linux runtime;
  none was installed or manufactured. Unit enablement is not reboot proof.
- B1VM/Worker1 later refreshes host facts, validates protection and actual units,
  stages final closures and enables in a coordinated idle slot. Boot-stop also
  needs that slot and preserves intent; disable-only differs from disable--now.
  Control switches currently select manual policy. Volatile stopped receipts do
  not survive power loss without confirmed persistent recovery after storage returns.

Next: hand off committed source/bundle first; D3TR/V3 continue independently.
