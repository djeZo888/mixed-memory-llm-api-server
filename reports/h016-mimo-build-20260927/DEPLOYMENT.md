# H016 exact artifact staging and rollback proposal (not executed)

Source928b3b470058241f089a839367d4b30d5887a6e3 remains GLM/default; MiMo disabled/unqualified. Final compiled image:
`sha256:6641df04cf4e8375029639a67c22da7c3ff4719d2b8e58748572f049de8fb022`.
Retained rollback release7143c17/image9ef885 is untouched. No production tag, unit, active profile or backend changed.

Build root on ai-harness is `/home/user/ai-harness-build/H016-MIMO-BUILD-20260927`.
`source/ai-harness` contains the exact archived source, copied lock-matching installed server/web graphs and compiled dist trees. `server-web-artifacts.tar.gz` contains dist/config/package/lock artifacts. `release/minimax-code-0.5.1.tar.gz` is the newly compiled native application package; it is not a model runtime. `inputs-artifacts.SHA256SUMS`, `artifacts.SHA256SUMS`, `source-files.SHA256SUMS`, `overlay-manifest.json` and `overlay-verification.json` freeze identities. Image source labels and pins now agree with the compiled a6dd7df patchset.

After W1 qualification and root review, prepare the small config overlay with the shipped staging script. The manifest must pass the existing compiled validation; its approved hash and actual allocated slot choose the context. Output65536 is mandatory. The current exact-content migration admits only the reviewed131072/1048576 tuples; another selected capacity needs a root-reviewed source update before activation. No131072 readiness is implied. These commands only prepare/build an isolated candidate:

```bash
set -euo pipefail
umask 077
H016_TASK=/home/user/ai-harness-build/H016-MIMO-BUILD-20260927
H016_STAGE="$H016_TASK/qualified-stage"
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
# Set H016_MANIFEST and H016_APPROVED_SHA to the exact root-reviewed W1 file/hash.
: "${H016_MANIFEST:?reviewed W1 manifest path required}"
: "${H016_APPROVED_SHA:?reviewed SHA256 required}"
cd "$H016_TASK"
python3 guard.py > pre-qualified-stage.json
node stage-qualified-config.mjs "$H016_TASK/source/ai-harness" "$H016_MANIFEST" "$H016_APPROVED_SHA" "$H016_STAGE"
podman build --pull=never --network none --format docker --file "$H016_STAGE/Containerfile" --iidfile "$H016_STAGE/trial.iid" "$H016_STAGE"
python3 guard.py > post-qualified-stage.json
```

The activation worker must create a fresh immutable host release from the checked artifacts, then copy the **same** `qualified-stage/config/active-frontier.json` into that release and the config-overlay image. Stage `mimo-candidate.json` only into the new host release. Install the manifest as protected root-owned `/etc/ai-harness/mimo-qualification.json` with no writable ancestry/links, preserving prior evidence. Verify image/host active config SHA256 equality and manifest SHA256 before activation. The config-overlay changes no code/tools/dependencies. The server uses the current root-reviewed native build/template/path identity plus authenticated props/slots; static receipt and fresh observations are distinct.

Persistent W1 owner adoption is mandatory before activation: the present trial owner otherwise auto-restores GLM at13:40UTC. Root/W1 must establish exact prior-process settlement, retained request/dispatch intent, one physical frontier owner, and fresh canonical `mimo-v2.6-pro-rl` node availability (freshness/available/ready/hardware fields). No independent second queue or implicit replay. Do not clear unresolved records to force activation. The overall13:48:08UTC and13:25settlement reserve remain unchanged.

Only the later authorized activation worker may pair the new host app/status release with the reviewed trial image under the existing launcher tag. Use the established H013 paired-unit deployment procedure, substituting exact old/new release/image identities and preserving every credential directive. Keep search/admin, data/history, private keys and backups unchanged. App activation and native Sova acceptance are outside this build session.

Rollback after W1 confirms exact MiMo-process settlement: leave/start with the reviewed GLM1M selection, use H016's exact-content managed MiMo131072/1048576-to-GLM1M migration, preserve custom conflicts and history, and restore the7143c17 release/9ef885 image and original unit paths. Do not restore database snapshots, clear quarantine, restart an unadopted owner or infer backend settlement from an idle slot. Old7143c17 profile code alone does not understand MiMo; run the H016 exact migration before returning engines to9ef885.
