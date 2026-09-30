# ACTIVATE19 recovery preparation only

Session `01a0e40c-c959-7110-bb9e-605ca8b80b61` started 18:07:17 UTC; hard ceiling 18:30:00 UTC.
Closed work at 2026-09-27T18:09:32.273791+00:00. Source `c71813e216813c618b4a83f8953d3d6639e6d2fa`.

Direct root hold: W1 ordinary production failed at 18:04:45 UTC with LeaseBusy;
proxy never started, state HELD, native settlement unknown. Root reported other
three ready. No ai-vm contact or backend request was made here.

One ai-harness read-only SSH command exited 0 at 18:08:42 UTC. Original release
7143c17 and image 9ef885 remain selected; app and status unit hashes match the
original pair exactly (full values in STATE.json). App inactive/dead, PID 0.
Search/status/admin remain active with PIDs 190181/301728/66185. Only searxng
container is running. No final18 acceptance unit/timer, intent or run directory.
No gate, apply, acceptance, rollback or remote mutation. Data, profiles, histories
and quarantine were neither inspected nor changed. This does not establish native
settlement or GLM readiness.

After Worker1 actual GLM 1M readiness and exact settlement receipt, plus root
normal-start authorization, the existing original pair needs only:

```sh
ssh -o BatchMode=yes ai-harness 'systemctl --user start ai-harness.service'
```

Command prepared only, NOT EXECUTED. No rollback helper/profile writes required.
Task18 staged source/image/qualifier identities remain recorded in STATE.json;
no source, schema, build or test work. Raw evidence is private outside Git at
`../private/harness-recovery-readonly.txt`. No paid wait. Existing wrapper writes
actual native exit to `../exit-code` and finish UTC to `../finished-utc` after exit.
