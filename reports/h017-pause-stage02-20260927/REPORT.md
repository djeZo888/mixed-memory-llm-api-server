# H017 W2 PAUSE-STAGE02

Original Sova paused normally at **2026-09-27 19:29:09 UTC**. Idle and
preservation proof completed at19:29:11; task-root `QUIET.json` was written
immediately, before staging readback or report packaging. App inactive/dead,
MainPID0, enabled unchanged. Search/status/admin retained PIDs190181/301728/66185,
states, enablement and release identities. No current owned app/task engine
container, active run, frontier request, active image job or uncertain image job.

Fresh counts:26sessions,133messages,62files,48terminal runs,25359events,
19terminal image jobs and1historical interrupted/quarantined workspace. The
workspace is distinct from image uncertainty0. Protected table hashes match
before/after. The ordinary stop changed only the image-lane row, from idle to
quarantined; image ownership uncertainty remained0 and all image jobs remained
terminal. No manual lane clear was performed. All17597regular non-DB files retain SHA256
`1e262519cde8059973b23a2fc2a2838e2a15cb4429269fe18e57cc4adb906f51`.
SQLite/transient exclusions changed161→160 through normal stop. No owner.sqlite
read, restore/reset, quarantine/ledger clear, cancellation, replay or deletion.
This is upper-app quiet evidence, **not atomic native GPU idle**.

The only service mutation was:

```sh
ssh ai-harness 'systemctl --user stop ai-harness.service'
```

Rollback is ONLY the following command, after W1/root authenticated GLM-ready GO:

```sh
ssh ai-harness 'systemctl --user start ai-harness.service'
```

Original rollback pair remains release
`7143c17d73173db9364b77956679c86d7026a4ae`, image
`9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c`,
tag `localhost/ai-harness-engine:0.0.2-ae65651df5f9`.
App unit SHA256 `eee8e1d7a3f370e3fcdbf5783f1b03df8672296abcf27726cdaca73c62b71b9c`;
status drop-in SHA256 `e033a07a50b8c5f9f535909e1405c87f99f932a3c1506aa36c30a4647462ac16`.
Installed launcher/config hashes, credential metadata and protected parent
ownership/modes/inodes matched before/after. No profile/unit/tag writes.
`/etc/ai-harness` remains root0700; `/etc/sova-qualification` root0755 and its
existing nonsecret `mimo.json` root0644.

The reviewed H010 `summary`, `inventory`, `units`, `container_summary` and
`require_idle` functions were imported inertly; its old main was never run.
The thin mechanical command is retained at task-root `pause-original.py`;
its SHA256 and private snapshot hashes are in [PRESERVATION.json](PRESERVATION.json).
Private BEFORE/AFTER snapshots are under task-root `private/` and on ai-harness
at `/home/user/ai-harness-build/H017-PAUSE-STAGE02-20260927/`, mode0700/0600.
No protected contents or credentials enter Git.

Task18 staged input readback PASS: host
`/opt/ai-harness/releases/6c4b5869d9bc7658fcaf565b642bd951ad0f5752-h016-final18/ai-harness`
and accepted image
`46feffff8fe00e5993a8e0d35f5a7932f82ee43ef91d87759f568c3a6029dc1e`
exist. Source marker and three relevant host file pins match retained Task18
closure; all26local H017 prep01 source pins match. No expensive full inventory
was repeated. Initial all-container check was intentionally conservative and
rejected non-search entries; scoped readback identified12historical H003
containers (11exited,1created), all untouched. No current app/task engine remains.

Future staging uses `reports/h017-source-prep01-20260927` and retained Task18
`/home/user/ai-harness-build/H016-FINAL-BUILD-ACTIVATE-20260927` inputs. It is
limited to2image files/3host files over46fe, preserving compiled payload.
Actual950000 props/slots/reserve and qualified receipt remain **PENDING_W1**.
The existing receipt SHA256
`f03120cf00356e0d1992129aac81ae37959677519f9cc2c463ab6f98a0867455`
is historical1M provenance and was not relabeled. No overlay/copy/build,
activation, deployment, inference, backend/BMC contact or acceptance dispatch.

Native ID `01a0e455-5a1c-7a10-824c-79d68271740a`; start19:26:33.933554UTC,
unchanged15-minute deadline19:41:33.933554UTC. Global21:07:11 and later acceptance
20:49:30stop/20:50hard settlement do not extend this task. Returning early after
packaging; the existing wrapper records actual exit code/time in task-root
`exit-code` / `finished-utc`. No paid waiting or W1 readiness polling.

Validation consisted of actual before/after preservation, unit/container/image
readback, targeted retained artifact hash checks and mechanical-command AST
parsing. No extra test suite/framework. Public evidence: [QUIET.json](QUIET.json),
[PRESERVATION.json](PRESERVATION.json), [STAGED-INPUTS.json](STAGED-INPUTS.json),
[SESSION.json](SESSION.json). Commit and named delta bundle over45287e2 are
recorded in task-root STATUS/HANDOFF after commit; no push.
