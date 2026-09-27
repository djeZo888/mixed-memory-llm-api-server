# H016 final integration: staged, activation held

Latest root steering (14:59UTC): global window extends to **17:48:08UTC**;
this native session still ends by **15:05:48.133723UTC**. MiMo is intended as
PRIMARY frontier replacing GLM only after full Sova acceptance; preserve both
Qwens and image service. Initial131072 promotion is superseded pending final
capacity qualification. Root proposes F16 about917504 (896K), 7% GPU reserve,
a short allocation test and a new4K/16K/64K ladder in a separate W1 task.
None of that is dispatched here. Current profile tuples/config are unchanged.
A minimal managed-profile allowlist/rollback delta for917504 may be needed in
that separate task. This packet's131072 driver/config proposal is now HELD,
not permission to promote131072; preflight refuses before any contacts.
Full17/native qualification flags remain missing/false; no qualified receipt.


This packet changes production source by exactly two lines: the server receipt
literal and Docker `GOMP_SPINCOUNT=0`. Source commit is
`df0702412b1a8f594db7d3211ca63f6aafe8a026`. Server-only compilation changed
`server/dist/active-frontier.js` to SHA256
`3a4b7f6a2563fd1c123cc14532fdd29c1ba3613544c87f7a3056b17bfefa0c35`.
The new inert release is:
`/opt/ai-harness/releases/df0702412b1a8f594db7d3211ca63f6aafe8a026-h016/ai-harness`.
All native engine, web, tool and dependency bytes are unchanged; engine remains
`sha256:6641df04cf4e8375029639a67c22da7c3ff4719d2b8e58748572f049de8fb022`.
No qualified overlay was built. The earlier 928b3b4 release remains intact.

The only new host configuration directory is `/etc/sova-qualification`,
root:root0755. It is EMPTY. `/etc/ai-harness` remains0700; all existing child
metadata was compared before/after without reading secret contents.

## Required root/W1 qualification before any further host writes

Reuse the exact required schema in
`../h016-activation-prep-20260927/NEEDED-FROM-W1.md`, with only its obsolete
receipt path replaced by `/etc/sova-qualification/mimo.json`. W1 supplies the
protected production manifest, actual full17 and strict schema qualification,
65536 requested-ceiling acceptance with a short successful response, serial
completion, exact current clean supervised production owner, native props/slot
and canonical fresh node DTO. Count9461 alone is not qualification.

Root must bind the actual deployed owner SHA256 to
`ee5d623f3334afba341e1539383ca672f7f4db096cf329adf1c69d2b871ec814`, its
source closure/manifest digest and Docker readback to `GOMP_SPINCOUNT=0`,
`OMP_NUM_THREADS=1`, unchanged image/argv/thread/pinning/no-host settings.
The owner code's existing source preflight pins its bytes; the app schema does
not itself attest Docker environment. Do not infer that mapping from a boolean.
W1 alone contacts/deploys ai-vm. No app inference until W1 lane handoff/root GO.

Capacity facts are separate: published1048576, allocated/configured131072,
output ceiling65536, occupied tested65536. Preserve actual completed output
length independently. Do not reinterpret a requested ceiling as generated output.

## Future config and receipt proposal — not executed

The following requires the exact reviewed protected W1 application document;
there is no template filled with invented qualification and no placeholder IID.
The helper validates the actual document, then makes an overlay on exact6641.
Its source is copied from the previous helper with stale path/owner prose fixed.
No native rebuild occurs.

```bash
set -euo pipefail
umask 077
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
H016_TASK=/home/user/ai-harness-build/H016-FINAL-INTEGRATION-20260927
H016_NEW=/opt/ai-harness/releases/df0702412b1a8f594db7d3211ca63f6aafe8a026-h016/ai-harness
: "${H016_MANIFEST:?actual root-reviewed W1 application document}"
: "${H016_SHA:?exact reviewed SHA256}"
python3 /home/user/ai-harness-build/H016-MIMO-BUILD-20260927/guard.py > "$H016_TASK/private/pre-qualified.json"
node "$H016_TASK/stage-qualified-config.mjs" "$H016_NEW" "$H016_MANIFEST" "$H016_SHA" "$H016_TASK/qualified-stage"
podman build --pull=never --network none --format docker --file "$H016_TASK/qualified-stage/Containerfile" --iidfile "$H016_TASK/qualified-stage/qualified.iid" "$H016_TASK/qualified-stage"
python3 /home/user/ai-harness-build/H016-MIMO-BUILD-20260927/guard.py > "$H016_TASK/private/post-qualified.json"
# Root reviews exact IID, sole config layer and current W1 identity before pairing.
sudo -n test ! -e /etc/sova-qualification/mimo.json
sudo -n test ! -L /etc/sova-qualification/mimo.json
# Directory root:root0755, canonical trusted ancestry already required; recheck.
test "$(stat -c '%u:%g:%a' /etc/sova-qualification)" = 0:0:755
sudo -n install -o root -g root -m 0644 "$H016_TASK/qualified-stage/mimo-qualification.json" /etc/sova-qualification/mimo.json
sudo -n install -o root -g root -m 0644 "$H016_TASK/qualified-stage/config/active-frontier.json" "$H016_NEW/config/active-frontier.json"
sudo -n install -o root -g root -m 0644 "$H016_TASK/qualified-stage/config/mimo-candidate.json" "$H016_NEW/config/mimo-candidate.json"
# Re-read through unchanged readMimoEvidence as user1000, hash-match and validate.
# Host and qualified-image active-frontier.json must be byte-identical.
```

The paired proposal `activate-pair.sh` has the corrected path/release/unit hashes
but still exits78 unconditionally. It must not be unlocked by this session.
After separate root GO, a reviewed follow-up can apply its existing exact pair
checks to the real receipt/IID, then pair tag/unit paths while keeping app paused
for the isolated H009-derived acceptance below. No late activation merely to use
remaining time. The source-label928b3b4 on the unchanged engine is intentional;
df07024 is the host receipt-path release. Status/app normal start follows actual
acceptance and root review. No ledger clear, replay or second frontier owner.

## Thin native application acceptance proposal — NOT RUN

`driver/` derives directly from the existing H009 native driver (see
`prepare-app-driver.py`). It retains `createApp`, `createEngine`, `createGateway`,
`FrontierLedger`, protected credentials, passive node observer, native ACP graph,
owned workspace/container settlement, and the original edge/check fixture.
It removes the old full-count-only request, roster projection, overlap request,
and GLM-specific gateway configuration. This is a proposal with syntax, hook
fixtures and absent-gate refusal checked, not a live-qualified runner.

One actual Qwen parent delegates exactly one foreground task to native MiMo.
The child reads/fixes edge.mjs and runs immutable check.mjs. The parent independently
runs check.mjs and produces its final answer. The full actual17 production tools
must hash to `80e7a1e12e073ac57638e86638cf571158711ff821c96605135627777ce44e8c`;
no schema substitution, reduced roster or native tool execution during preparation.
Every MiMo request must use fewer than16384 input tokens and requested65536 output,
with allocated131072. Prompt asks for a short result; wall time bounds actual work.

Root issues a private, hash-pinned `ROOT_GO_H016_NATIVE_APP_ACCEPTANCE` gate only
after current lane handoff. `driver/preflight.mjs` lists all required real gate
fields and receipts; no gate is manufactured here. Its qualified image ID must
be a real config overlay on6641, never6641 itself. The activation manifest and
all driver/release hashes are pinned. Expiry must be no later than17:38:08UTC,
leaving10minutes for final recovery. Native work cap480s; supervisor cap600s,
including settlement; no second attempt. Owned data root is new
`H016-FINAL-INTEGRATION-20260927/live-acceptance-01`, never production userdata.

Exact future entrypoint after the separate capacity/driver/root-GO review is
`bash "$H016_TASK/launch-app-acceptance.sh"`. The concrete script is currently
HELD with exit78; its retained body uses only independent Linux
`systemd-run --user --unit=h016-final-app-acceptance`, RuntimeMaxSec660,
TimeoutStopSec30, KillMode=control-group, append-only task log output and the
existing bounded `supervise.py`. No --wait/--pipe/--pty and no foreground live
client. The supervisor runs preflight inside the job, saves live-process.log,
supervisor-result.json and exact owned-container settlement. Native update
contents stream to private events.jsonl with periodic/boundary fsync; complete
request histories and final snapshots are retained. Dispatch intent is not proof.
Verify invocation/PID/status from a new SSH session after launch, then close the
paid CLI while the owned bounded job runs. Never SIGINT a CLI/supervisor while
its child owns a live request; preserve and inspect job/request disposition
before any recovery. The earlier W1 foreground stream-loss incident motivates
this requirement. No such request or client ran in this packet.

PASS requires actual Qwen and MiMo wire/model/route IDs; exactly one native task
call and ACP parent/child mapping; child's assistant tool call paired with a real
tool result in a subsequent MiMo request; successful child final result; parent's
independent bash verification; immutable check file and actual edge-file change;
parent final answer; all native requests settled and frontier idle; exact owned
container release. Root reviews semantics. Any ambiguity stays held; no replay
or quarantine clear. Recheck original production data identities afterwards.

## Recovery in either outcome

Actual state remains original7143c17/image9ef885, paused app. After W1 proves exact
MiMo settlement, valid explicit GLM selection and original GLM1M readiness, normal
`systemctl --user start ai-harness.service` is sufficient; no profiles migrated.
This session does not start it. Original units, tag, image, release and private
rollback copies in H016-ACTIVATION-PREP-20260927 remain unchanged.

If a later MiMo activation actually migrates managed profiles, use the existing
`rollback-profiles.mjs` with the new release's unchanged configure-profile.mjs,
first dry-run then the reviewed apply, after app/owner settlement and W1's explicit
ready GLM selection. Then restore exact original tag/unit pair using
`../h016-activation-prep-20260927/ACTIVATION.md` recovery commands. Preserve current
user data/history/files/custom profiles; never snapshot-restore user data or clear
quarantine. Global deadline is now17:48:08UTC; this native cap remains15:05:48.133723UTC.
