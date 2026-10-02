# Protected publication and generic original capture — UNAPPROVED

These helpers prepare finite root operations. This source worker performed no Linux writes, signing/publication, service action, inference, or live qualification. The helper creates no key, baseline approval, native receipt, global generation proof, frontier proof, or PASS. Existing key bytes never appear in command arguments, output, or an archive. Run any future publication as the existing app UID using its existing protected ordinary key; `reviewedBy: root` describes the signed root review, not the executing UID.

Current prerequisite: root's bounded read-only observation found no configured `AI_HARNESS_CODEX_ORDINARY_ENTRY_FILE` or discovered genuine ordinary baseline. Discover and review the genuine existing approval, launch, settlement, protocol ACK, optional complete original legacy transport/raw protocol, retained native binary and all retained baseline source paths. Missing evidence stops preparation. There is no baseline creation/fabrication fallback. Native/UI/research/MiMo/image/manual compact/auto400K/live activation remain NOT_TESTED.

The staging sequence is **separate STAGE_COMPILED_ONLY GO → separate ordinary sidecar publication GO → separate RESTART_STAGED GO → create one blank ordinary UI chat → separate exact generation ticket publication GO → separately approved one UI dispatch**. This helper neither stages nor restarts. Publication requires final source already staged, so its graph refers to the sealed final commit and actual immutable release paths. Existing sidecar/ticket targets refuse replacement; discovering one is a distinct root prerequisite. A publication GO does not authorize UI dispatch or model work.

## Preparation commands

All paths below are placeholders, not current approved locations. `prepare-*` prints an unsigned BODY to stdout. Root should capture it privately with mode 0600. It grants nothing and is not a GO. Source/output paths must be canonical, non-aliased and protected; private inputs and packet parents are app-owned, files 0600/single-link, directories private with safe root/app-owned ancestry. No network/SSH command exists in either helper.

```text
python3 protected_publication.py prepare-ordinary \
  --baseline <genuine-ordinary-approval> --key <existing-private-key> \
  --server-dir <final-immutable-release/server> \
  --deployment-dir <final-immutable-release/deploy> \
  --source-commit <sealed-final-40hex-commit> --profile generation \
  --reviewed-at <actual-root-review-UTC-ISO-time>

python3 protected_publication.py prepare-generation \
  --baseline <same-genuine-ordinary-approval> --key <same-existing-key> \
  --sidecar <genuine-ordinary-approval>.sources.json \
  --ticket-id <new-UUID> --session-id <exact-blank-normal-UI-session-UUID> \
  --app-pid <fresh-current-app-PID> --issued-at-ms <integer> --expires-at-ms <integer>
```

Ordinary preparation requires exact sibling paths `/opt/ai-harness/releases/<sealed-final-commit>-<reviewed-suffix>/ai-harness/{server,deploy}` and exact same-commit `ai-harness/source-commit.txt` bytes. It verifies the existing HMAC baseline, original evidence/binary hashes and original baseline file graph, then invokes the final compiled actual launch/settlement and no-generation validators. Source sidecar files are EXACTLY recursively imported `dist/main.js` + `dist/codex-preview-main.js`, their `.ts` partners, server package lock, current receipt profile sources and `deploy/engine/validate-image-overlays.py`. An unimported startup/deployment helper is excluded from this exact sidecar; root separately binds it in release/GO manifests. Profile receipt names match `codexReceiptSourceProfile`; generation has 12, technical-generation 14. This does not turn technical host preprocessing into a qualified native technical profile.

Generation preparation invokes the actual final `loadCodexOrdinaryEntry` and `assertSourcesCurrent`, requires its returned authority to equal the computed sidecar body/source hashes, and observes `/proc` for the current PID birth/UID/boot/cgroup. It emits the exact consumer `codex-normal-generation-acceptance-v1` body with 1 native run, 1 generation job, 1920x1080 and expiry at most 30 minutes after issuance. It contains no edit/reference/child authority. Root must choose an earlier expiry consistent with its live window/reserve.

## Publication GO schema

The root supplies a private `{body,seal}` GO envelope. `seal` is lowercase HMAC-SHA256 of the canonical GO BODY with the **same existing ordinary key**. The helper does not issue a GO. Canonical JSON uses recursively sorted object keys with JavaScript UTF-16 key ordering, exact array order, UTF-8 and compact separators; signed numbers are safe integers, never floats. No extra GO keys are accepted.

```json
{
  "body": {
    "schema": "h046-protected-publication-go-v1",
    "reviewedBy": "root",
    "id": "UNSET_NEW_UUID",
    "operation": "ordinary-current-sources OR generation-ticket",
    "issuedAtMs": "UNSET_INTEGER",
    "expiresAtMs": "UNSET_INTEGER_AT_MOST_30_MINUTES_AFTER_ISSUANCE",
    "maxInvocations": 1,
    "sourceCommit": "UNSET_FINAL_40HEX_COMMIT",
    "bodySha256": "UNSET_SHA256_CANONICAL_UNSIGNED_PACKET_BODY",
    "receiptSourcesSha256": "UNSET_SHA256_CANONICAL_CURRENT_RECEIPT_SOURCES",
    "helperSha256": "UNSET_SHA256_FINAL_protected_publication.py_BYTES",
    "baselinePath": "UNSET_CANONICAL_GENUINE_BASELINE",
    "keyPath": "UNSET_CANONICAL_EXISTING_PRIVATE_KEY",
    "targetPath": "UNSET_CANONICAL_NEW_PACKET_PATH",
    "claimsDir": "UNSET_CANONICAL_PRIVATE_APP_OWNED_DIRECTORY",
    "owner": {"pid": "UNSET_INTEGER", "startTicks": "UNSET_DIGITS", "uid": "UNSET_INTEGER", "bootId": "UNSET_UUID", "cgroupPath": "UNSET_ABSOLUTE_CGROUP"},
    "ownerObservationPath": "UNSET_PRIVATE_CURRENT_ROOT_OBSERVATION",
    "ownerObservationSha256": "UNSET_ORIGINAL_OBSERVATION_SHA256",
    "configFiles": {"UNSET_EXACT_CURRENT_CONFIG_PATH": "UNSET_CURRENT_CONFIG_SHA256"}
  },
  "seal": "UNSET_ROOT_HMAC"
}
```

The deliberately invalid template above is not signable authority. Ordinary target is fixed to `<baselinePath>.sources.json`. The generation target is the protected path root passes to the normal launch. Its owner equals the current `/proc` identity. `receiptSourcesSha256` is SHA256(canonical current sidecar `receiptSources`), and ticket source authority is EXACTLY final `sourceCommit`, admitted `profile`, SHA256(canonical sidecar BODY), SHA256(canonical receipt sources).

`ownerObservationPath` is a fresh private root review record with EXACT fields below, no broader authority. The helper checks its exact original SHA, age at most 15 seconds, zero integer active counts, current `/proc` owner, read-only `systemctl --user show ai-harness.service`'s exact MainPID/InvocationID/ControlGroup and the complete actual config hash map. The launcher intentionally uses `env -i`, so the app's inherited environment is not used as a unit identity proof. The original read-only logs stay private outside Git; root must make a genuine observation, never fill an invented idle result.

```text
schema: h046-root-app-observation-v1
owner: exact {pid,startTicks,uid,bootId,cgroupPath}
observedAtMs: integer actual observation time
unit: exact current *.service unit
invocationId: actual systemd 32 lowercase hex ID
sourceCommit: actual current owner's 40hex commit
configSha256: SHA256(canonical GO.configFiles)
activeRuns: 0
activeImageJobs: 0
activeVisionJobs: 0
originalLogSha256: SHA256(original private read-only observation log)
```

```text
python3 protected_publication.py publish \
  --body-file <private-prepared-BODY> --go <fresh-private-signed-GO> \
  --baseline <same-genuine-baseline> --key <same-existing-key> \
  --target <exact-GO-target> --claims-dir <exact-GO-private-claims-directory>
```

Publication revalidates the body, current sources/baseline/owner, GO deadline/helper/config/idle observation; exclusively creates `<claimsDir>/<GO-id>.claim.json`; then rechecks source/owner/GO. The claim remains spent on **every** subsequent failure, with no retry/refund or overwrite. Generation publication exclusively creates `<ticket-parent>/<ticket-id>/` mode 0700 for the consumer's future binding/run/job claims, then creates the 0600 single-link packet. Ordinary publication creates the fixed sidecar and invokes actual final `loadCodexOrdinaryEntry`. Failed published bytes remain private and unqualified; the application consumer fails closed. A successful publication result explicitly says `nativePassClaim:false` and `settlementClaim:false`. Root captures original stdout/stderr and actual integer process exit; exit 2 is refused, never success. No global generation flag is changed.

## Generic original reader

`capture_originals.py` is only a generic, read-only full-byte reader. The independent frontier driver owns workflow-specific native capture and acceptance. It takes a private `h046-original-capture-binding-v1` BODY with EXACT fields: `schema`, `sessionId`, `runId`, `nativeThreadId`, `nativeTurnId`, `profileDir`, `codexHome`, `databaseSnapshotPath`, `databaseSnapshotSha256`, `launchReceiptPath`, `launchReceiptSha256`. The snapshot is root's closed private SQLite backup, not the live database. The launch record binds exact session/run/profile; persisted session/run/events must contain the exact thread and native turn. No turn ID is inferred. This validates capture identity, not native receipt attestation; the genuine ordinary loader remains the qualification gate.

```text
python3 capture_originals.py --binding-file <private-exact-persisted-binding> \
  --child-thread <exact-original-parent-dispatched-child-UUID>
```

Only the approved `<profileDir>/codex-home` is searched, for unique exact original `sessions`/`archived_sessions` JSONL. The first `session_meta` must match exact thread, native 0.158.0 and `sova`; parent `turn_context` and `task_complete` must match the persisted turn. Child capture requires original parent spawn begin/end call chain, original child parent identity and its own current root-turn `turn_context`/`task_complete`, plus parent wait records. Whole original bytes, SHA256 and exact line indexes are emitted in a private base64 JSON envelope. Missing/duplicate/paginated originals fail explicitly; metadata-only output cannot substitute. Missing completion/wait is reported with exit 3. Hard capture failure exits 2. Capture neither fabricates `provider_finish` nor claims authorship/completion semantics/PASS. Stdout contains private transcript content: root must capture outside Git, avoid printing it into prompts/reports, and preserve its original exit/stderr.

## Source checks

20 focused unit checks passed: 14 publication and 6 generic capture checks. They cover canonical compatibility against Node, missing baseline, final release commit metadata/sibling paths, exact graph exclusions, signatures, unsafe paths/links/modes, source/helper/config/owner/idle/expiry/scope failures, immutable one-shot claims, bounded generation body, and original full bytes/chain/missing/foreign/incomplete/version records. Fixtures are source checks only. They do not qualify any live ordinary baseline or native/UI/image workflow.
