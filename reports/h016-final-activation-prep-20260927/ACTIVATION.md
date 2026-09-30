# HELD final single-layer / paired-host procedure

Preparation only. Root reviews this source once with the actual W1 protected
qualification, native17 acceptance, final winner/affinity/capacity and clean
production identity. The existing review/activation manifest is reused; no new
GO file, receipt schema, lease or per-mechanical-step approval is introduced.
Unconditional source holds remain until that review. No final image, final
qualification hash, active config or production readiness is claimed here.

The exact compiled native source is b948889814648ad761f40a18260ddbe6351c6bbf;
patchset38d7b6a7978e5e95e69db790cf2e3465a0e33ddd27124b1b7af387518e9722bf.
Reuse minimal compile14 payload0d34ca656248d8293ee4098ef1ba0202fc02353ac35a515870220e8fcc805d17
from /home/user/ai-harness-build/H016-TIMEOUT-COMPILE-20260927 (local private copy
in sibling task). Its19 compiled/metadata changes,97 output graph and unchanged
dependencies are prior validated evidence; do not recompile/rebuild native,
inference or dependency images, download, or rerun native acceptance here.

Actual usable props/slot is authoritative:1000192 is allowed only with matching
native readback and7% reserve PASS; otherwise target1000000, fallback917504 only
on actual reserve failure. capacity.allocated==identity.actualSlotContext means
USABLE. Physical padding stays separate W1 evidence. General numeric schema is
unchanged.65536 is the requested output ceiling; short output is expected.
The estimator remains estimated; native admission is exact. No occupied1M claim.
Final runtime pins come from protected qualification, not16/64/GOMP0 best-so-far;
8-thread affinity remains pending. Ordinary proxyad7fea4cbf9fd2b6583c87530325136c858d94c1e28318b71bed682965972a56
is pending root review, not deployed by this packet. W1 owns proxy/native changes.

Run existing installed registered-storage/root-disk guards around future writes;
retain the canonical lifecycle lease and W1 ownership. Refresh installed guard
identities from root's current handoff; never fall back to a historical helper
merely because this document references its accepted procedure. No host commands
below were run. Uppers remain stopped until actual isolated acceptance PASS.

1. Root/W1 establishes actual native17/strict/serial/65536 acceptance, exact
   owner/node/source/props/slot/reserve proof and writes the existing nonsecret
   qualification at /etc/sova-qualification/mimo.json (root directory0755,
   root file0644). /etc/ai-harness0700 stays unchanged. Keep exact readMimoEvidence
   guard; no new capacityDecision or qualification fields. Select canonical
   MiMo V2.6 Pro-RL from actual qualifier only. Both registry rows stay visible;
   GLM is dormant/manual rollback, excluded from required selected-frontier
   health; Qwen main/default/limits remain unchanged.
2. Prepare the final source release and one combined image context. The checked
   stage helper consumes that protected qualification and current profile,
   deriving host/image active config from actual qualified context/65536.
   The assembler verifies the retained archive and every payload hash, preserves
   executable CLI mode, replaces only the profile, adds active config, and emits
   ONE COPY layer over exact6641df04cf4e8375029639a67c22da7c3ff4719d2b8e58748572f049de8fb022.
   It also emits the paired host delta: canonical launcherb315d97a, profile045d0ed2,
   exact reviewed deploy/engine/pins.json and canonical deploy/patches metadata,
   registry configa2d69b9b, gateway6757fc31 and registry89386529 JS/declarations.
   Retain active-frontier.js3a4b7f6a and all other accepted host artifacts.

Held command skeleton after the existing review (all variables are actual values,
not synthetic qualification; helpers currently refuse before any action):

```bash
set -euo pipefail
: "${H016_SOURCE:?reviewed final source commit}" "${H016_SHA:?actual qualification SHA256}"
H016_PREP=/home/user/ai-harness-build/H016-FINAL-ACTIVATION-PREP-20260927
H016_BASE=/opt/ai-harness/releases/df0702412b1a8f594db7d3211ca63f6aafe8a026-h016/ai-harness
H016_NEW=/opt/ai-harness/releases/${H016_SOURCE}-h016-final15/ai-harness
H016_STAGE=$H016_PREP/final-stage
H016_REPO=$H016_PREP/source
node "$H016_PREP/stage-qualified-config.mjs" "$H016_BASE" /etc/sova-qualification/mimo.json "$H016_SHA" "$H016_STAGE" "$H016_REPO/ai-harness/deploy/engine/configure-profile.mjs"
python3 "$H016_PREP/assemble-final.py" "$H016_STAGE" /home/user/ai-harness-build/H016-TIMEOUT-COMPILE-20260927/timeout14-payload.tar.gz "$H016_REPO" "$H016_SOURCE"
cd "$H016_STAGE"
sha256sum -c FINAL.SHA256SUMS
podman build --pull=never --network none --layers --format docker --jobs=1 --file Containerfile --iidfile final-combined.iid .
H016_IID=$(cat final-combined.iid)
```

3. Before pairing, offline image checks: compare actual RootFS layers with exact
   base plus exactly one; match source/native-source/patchset labels, every
   payload file hash (FINAL.SHA256SUMS paths stripped of payload/), engine pins,
   patch manifest and CLI lineage. Compare image
   /opt/ai-harness/engine/configure-profile.mjs and
   /opt/ai-harness/config/active-frontier.json byte-for-byte with host delta.
   Use no-network, read-only, no-new-privileges/cap-drop ALL containers. Reuse
   verify-built.sh's tmpfs/user flags and mount the current profile test at
   /opt/ai-harness/engine/configure-profile.test.mjs; run only the focused
   MiMo/H016/managed-frontier tests against the actual image profile. Reuse the
   accepted compiled offline probe if a further image identity concern exists;
   no inference. Do not treat prior mounted6641 probe as this final-image check.
4. While uppers stopped, create the new release from retained df070241 with
   `cp -a --reflink=auto` into the previously absent H016_NEW; install only the
   exact staged host delta as root-owned files (launcher executable). Do not
   modify the original release or staged base. Hash unchanged active-frontier.js
   against3a4b7f6a2563fd1c123cc14532fdd29c1ba3613544c87f7a3056b17bfefa0c35.
   Reuse saved proposed app/status units, substituting only their old df070241
   release path with H016_NEW; preserve data/key/environment references. Record
   their actual hashes in proposed/SHA256SUMS and existing activation manifest;
   inspect diff and systemd-analyze verify. No fabricated final unit hashes.
   Run held activate-pair.sh H016_SHA H016_IID H016_SOURCE --dry-run, then its
   --apply under that same reviewed procedure. It pairs tag/unit/status paths,
   validates protected receipt and host/image bytes, and never starts the app.
   Partial failure stays held; no automatic rollback or quarantine clearing.
5. Existing root review binds the actual final source/image/host/driver/qualification
   hashes and current W1 owner; no old hardcoded runtime winner. Dispatch only
   this packet's fresh Linux systemd wrapper. It owns preflight and every client,
   saves streams/logs/IDs/intent, and does not rely on a foreground native CLI.
   Parent Qwen delegates once to MiMo; approved combined bash reads/edits/checks,
   paired real MiMo tool results and continuation, changed edge/unchanged check,
   then parent independent check and exact final markers/native IDs are required.
   All17 production schemas are advertised unchanged; this does NOT assert all17
   tools executed. No fixtures/results injected into the live backend.
6. On reviewed application PASS plus exact W1 native idle/owner proof, normal
   `systemctl --user start ai-harness.service` and root-owned status restart/readback
   may restore normal service. Ambiguous EOF/cancel/process/socket closure stays
   HELD/UNKNOWN; local deadline does not prove GPU/native settlement. Coordinate
   exact owner with root/W1 before release, rollback or further requests.

BUSY16 retiming supersedes the held PREP15 deadline under the explicit45-minute
foreground extension. Global end18:33:08UTC; local hard settlement18:30:00UTC.
Timing: root permits later launch from actual remaining time, with no static
full-envelope admission block. Supervisor includes measured preflight in1380s total;
work=min(1200, remaining monotonic total/absolute time minus180 cleanup).
After measured preflight (including the live driver's repeated preflight), under
720s work refuses before inference.720s is a12-minute attempt budget, NOT a
predicted PASS; incomplete means NOT_QUALIFIED and native UNKNOWN. The theoretical
latest inference admission is18:14:30 with zero extra overhead; latest launch is
earlier by actual dispatch/preflight time. Supervisor records actual work budget
and deadline. Local cleanup target18:29:30; independent fixed systemd calendar
stop then grants30s stop grace, fixed LOCAL hardend18:30. Runtime cap dynamically
min(1470, seconds to18:29:30), plus30<=1500. No timer extends18:30. Exact native/GPU
settlement remains separate W1 proof. Systemd scheduling/live cleanup NOT_TESTED.

For envelope arithmetic only,18:05+1500=18:30 leaves ONLY3m08 before global18:33:08 for final data/restoration
contingency AND the separately owned final near1M background start proof. Tight,
unproven; this packet cannot promise both fit. Root should reserve more time by
starting acceptance earlier or hold final dispatch. The last occupied near1M8h
request happens ONLY after native/production/Sova acceptance as the final task;
then all paid workers close and the user nudges later. The LAST client must not
impose a global app pause: keep parent Qwen, Sova UI and image up; the production
proxy serializes its chat lane nonblockingly through drain. This differs from
the existing exact-app-owner stop for foreground acceptance/paired promotion.
The frozen LAST client pause requirement and unsafe BUSY handling need W1 fixes
before deployment (see ../h016-final-window-busy-20260927/REVIEW.md).
No such job or automation is created,
launched or monitored here.

Rollback on concrete failure/root coordination: stop admission, retain intent and
current data/quarantine, establish exact W1 native settlement and explicit ready
GLM1M selection. Validate all managed profiles before writes using this packet's
rollback-profiles.mjs CURRENT_REVIEWED_PROFILE PROFILES_ROOT --dry-run, then
--apply under the same reviewed recovery. Exact five managed MiMo contexts revert
to GLM1048576/65536; custom edits stop before writes. Never restore a userdata
snapshot or clear quarantine. Restore saved original unit pair (app SHAeee8e1d7a3f370e3fcdbf5783f1b03df8672296abcf27726cdaca73c62b71b9c;
status SHAe033a07a50b8c5f9f535909e1405c87f99f932a3c1506aa36c30a4647462ac16),
original release7143c17d73173db9364b77956679c86d7026a4ae and
image9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c tag
localhost/ai-harness-engine:0.0.2-ae65651df5f9. Reuse the exact install/mv/daemon-reload
commands in the accepted h016-activation-prep/ACTIVATION.md, with this packet's
current rollback helper. Original data paths/credentials/histories/files remain.
Start original app only after ready GLM and root coordination. If no promotion
occurred, existing original pair needs only normal start after that readiness;
no profile/tag/unit restoration is necessary. No rollback was executed here.
