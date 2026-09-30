# HELD — future activation proposal, not currently executable

Root GO is already the authorized deployment trigger; no generic permission
roundtrip. Activation is HELD until a reviewed receipt-path/access correction,
full native qualification and an observed clean production owner exist.
Preserve /etc/ai-harness0700 and every existing child unchanged. Current source
hardcodes /etc/ai-harness/mimo-qualification.json, which the app cannot traverse.
A separate root-owned traversable directory for this nonsecret hash-pinned
receipt is preferred for later narrow source review; no scheme or source change
is implemented here. Neither the remote draft nor this packet may be activated.
The bundled activate-pair.sh exits78 unconditionally after its help option.
The remote task copy remains an unused draft governed by this HELD document.
Until corrected and reviewed, keep the app paused and production7143/9ef unchanged.
No manifest/new qualified image ID is available in this packet. Never substitute
the disabled6641 build image for the qualified image. Read NEEDED-FROM-W1.md.

The earlier build packet's adoption ACK/trial13:40 language (including descriptive
strings emitted by the unchanged staging helper) is superseded: one ordinary
supervisor must clean-launch production MiMo. W1 deploys that backend only later.
Its current serverInstance/generation must match the application qualification.
No source, node, owner, benchmark or engine edits belong to this prep.

Before switching, parent/W1 must actually observe the controlled production
owner RUNNING, exact native/proxy identities and selected MiMo intent, no old
benchmark owner, no uncertain request/dispatch ownership, and fresh canonical
node `mimo-v2.6-pro-rl` available/ready/unlatched. Props/slot capacity and static
qualification must match. Do not infer these facts from a manifest or an idle
slot. Preserve unknown activity/admission; no ledger clearing. Inspect the
current readbacks again at final switch, under the existing ownership assignment.

Initial131072/output65536 matches accepted profile migration. Any different
allocation outside131072/1048576 needs the minimal reviewed profile-tuple update
before activation.16K benchmark request size is not the allocated capacity.
Missing MiMo readiness remains a frontier-only failure; Qwen app startup survives.

## Config overlay and host finalization, after exact reviewed inputs arrive

Review-only command proposal: do not execute while HELD. The commands and
bundled activation script require later review after the receipt-path correction.
Input file/hash/IID values are deliberately not invented here.

```bash
set -euo pipefail
umask 077
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
H016_BUILD=/home/user/ai-harness-build/H016-MIMO-BUILD-20260927
H016_PREP=/home/user/ai-harness-build/H016-ACTIVATION-PREP-20260927
H016_NEW=/opt/ai-harness/releases/928b3b470058241f089a839367d4b30d5887a6e3-h016/ai-harness
: "${H016_MANIFEST:?exact reviewed W1 application document path}"
: "${H016_SHA:?root-reviewed document SHA256}"
H016_STAGE="$H016_PREP/qualified-stage"
python3 "$H016_BUILD/guard.py" > "$H016_PREP/private/pre-qualified.json"
node "$H016_BUILD/stage-qualified-config.mjs" "$H016_BUILD/source/ai-harness" "$H016_MANIFEST" "$H016_SHA" "$H016_STAGE"
podman build --pull=never --network none --format docker --file "$H016_STAGE/Containerfile" --iidfile "$H016_STAGE/qualified.iid" "$H016_STAGE"
python3 "$H016_BUILD/guard.py" > "$H016_PREP/private/post-qualified.json"
# Root reviews the resulting exact iid before paired promotion.
sudo -n install -o root -g root -m 644 "$H016_STAGE/config/active-frontier.json" "$H016_NEW/config/active-frontier.json"
sudo -n install -o root -g root -m 644 "$H016_STAGE/config/mimo-candidate.json" "$H016_NEW/config/mimo-candidate.json"
# HELD: receipt installation omitted pending the narrow path/access source review.
# Do not change /etc/ai-harness permissions or children.
```

Receipt placement/access commands are unresolved and intentionally absent.
Preserve any future prior receipt as private evidence before reviewed replacement.
Do not copy credentials into release, argv, image or report. Existing key paths,
LoadCredential and browser-approval-key directives are already preserved verbatim
in proposed units. The accepted run-engine launcher changes only its patchset
pin to a6dd7df; retaining the old pin would reject the new image. run-server,
frontier config and system registry remain byte-identical to7143.

Future pair proposal, HELD: after a reviewed path correction updates the source
and command proposal, plus W1/root current readback review, use a literal
qualified iid (not a tag) and approved manifest hash. The current bundled script
refuses execution; the following is not an executable activation instruction:

```bash
: "${H016_QUALIFIED_IID:?literal root-reviewed sha256 image ID}"
bash "$H016_PREP/activate-pair.sh" "$H016_SHA" "$H016_QUALIFIED_IID" --dry-run
# Following review of that exact dry-run and current W1 owner/node evidence:
bash "$H016_PREP/activate-pair.sh" "$H016_SHA" "$H016_QUALIFIED_IID" --apply
```

The retained draft body describes rechecking paused app, terminal queues/no ambiguous frontier, no owned
task container, exact7143 units/9ef tag, qualified-image layers on6641, protected
manifest validation/hash, exact host/image active-frontier byte identity and
unit entrypoint resolution before pairing tag+app/status paths. Root/W1's live
production identity review is an operator prerequisite, not automated or
replaced by this local script. No config alone proves readiness. After switching,
collect normal app/status readback and content/credential metadata preservation;
do not infer inference/workflow acceptance or add traffic without its scope.
Partial promotion failure stays held for review; no automatic backend rollback.

## Current restore and unused future rollback

Actual current state: production7143/9ef and all managed profiles never changed.
After W1 proves MiMo settlement, valid explicit GLM selection and GLM1M ready,
a later normal `systemctl --user start ai-harness.service` is sufficient.
No rollback helper, tag/unit rewrite, data restore or status restart is needed
for this current state. This preparation session does not start the app.

The following helper/commands are preserved solely for a future activation
that actually creates MiMo profiles. They were never run on production profiles.

First pause/settle app work through the existing reviewed procedure, retaining
request intent. W1 must prove exact MiMo native/PID/cgroup/GPU release, then
publish valid explicit GLM selection with new generation and original GLM bytes,
and observe GLM1M ready. Missing selection is not GLM. Do not start old app before
this proof. Keep current databases, files, history, AGENTS custom text and ledgers;
no snapshot restore or quarantine clearing.

Only after that proof and locally paused app/no owned container/queue ambiguity:

```bash
set -euo pipefail
umask 077
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
H016_PREP=/home/user/ai-harness-build/H016-ACTIVATION-PREP-20260927
H016_NEW=/opt/ai-harness/releases/928b3b470058241f089a839367d4b30d5887a6e3-h016/ai-harness
python3 /home/user/ai-harness-build/H016-MIMO-BUILD-20260927/guard.py > "$H016_PREP/private/pre-rollback.json"
node "$H016_PREP/rollback-profiles.mjs" "$H016_NEW/deploy/engine/configure-profile.mjs" /home/user/.local/share/ai-harness/profiles --dry-run
# Inspect the dry-run. Any custom conflict stops before writes.
node "$H016_PREP/rollback-profiles.mjs" "$H016_NEW/deploy/engine/configure-profile.mjs" /home/user/.local/share/ai-harness/profiles --apply
# Exact managed MiMo131072/1048576 -> GLM1048576/output65536 first.
# Existing old engine then normally refreshes ephemeral profile config.
cd "$H016_PREP"
printf '%s\n' 'eee8e1d7a3f370e3fcdbf5783f1b03df8672296abcf27726cdaca73c62b71b9c  private/ai-harness.service' 'e033a07a50b8c5f9f535909e1405c87f99f932a3c1506aa36c30a4647462ac16  private/30-h008-registry.conf' | sha256sum -c -
podman tag sha256:9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c localhost/ai-harness-engine:0.0.2-ae65651df5f9
install -m 600 private/ai-harness.service /home/user/.config/systemd/user/ai-harness.service.h016-rollback
mv /home/user/.config/systemd/user/ai-harness.service.h016-rollback /home/user/.config/systemd/user/ai-harness.service
sudo -n install -o root -g root -m 644 private/30-h008-registry.conf /etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf.h016-rollback
sudo -n mv /etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf.h016-rollback /etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf
systemctl --user daemon-reload
sudo -n systemctl daemon-reload
sudo -n systemctl restart ai-harness-status.service
systemctl --user start ai-harness.service
```

No MiMo profiles were created in the actual current state; use the simple
normal app start described above after W1 backend-ready proof. The helper is
unused/tested source only. Do not run the H013 1M-to480K helper. Retain the new release/image and
qualification as rollback evidence. Existing search/admin and all key paths stay.
