#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'Root direct GO required for apply: activate-pair.sh REVIEWED_MANIFEST_SHA256 QUALIFIED_IMAGE_ID FINAL_SOURCE_COMMIT [--dry-run|--apply]. Default dry-run. Read ACTIVATION.md first; W1 current clean-owner/readiness proof is mandatory.'; exit 0; fi
# Prepared procedure only. Apply requires root direct pins/readiness GO.
umask 077
H018_SHA=${1:?exact root-reviewed qualification hash required}
H018_IID=${2:?exact root-reviewed qualified config image ID required}
H018_SOURCE=${3:?actual final reviewed source commit}
[[ $H018_SOURCE =~ ^[a-f0-9]{40}$ ]]
H018_MODE=${4:---dry-run}
[[ $H018_MODE == --dry-run || $H018_MODE == --apply ]]
[[ $H018_SHA =~ ^[a-f0-9]{64}$ && $H018_IID =~ ^sha256:[a-f0-9]{64}$ ]]
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
H018_PREP=/home/user/ai-harness-build/H018-HARNESS-PREP01-20260928
H018_GUARD=/home/user/ai-harness-build/H016-TIMEOUT-COMPILE-20260927/artifact-guard.py
H018_NEW=/opt/ai-harness/releases/${H018_SOURCE}-h018-prep01/ai-harness
H018_TAG=localhost/ai-harness-engine:0.0.2-ae65651df5f9
H018_UNIT=/home/user/.config/systemd/user/ai-harness.service
H018_STATUS=/etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf
cd "$H018_PREP"
printf '%s\n' "d84153e75b13c8f59a7a0c31c8a5cca2ac5cc8469ab3e1cc72ecc0f2220be496  $H018_GUARD" | sha256sum -c -
python3 "$H018_GUARD" > private/pre-activation.json
test "$(podman image inspect "$H018_TAG" --format '{{.Id}}')" = 9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c
printf '%s\n' 'eee8e1d7a3f370e3fcdbf5783f1b03df8672296abcf27726cdaca73c62b71b9c  /home/user/.config/systemd/user/ai-harness.service' 'e033a07a50b8c5f9f535909e1405c87f99f932a3c1506aa36c30a4647462ac16  /etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf' | sha256sum -c -
sha256sum -c proposed/SHA256SUMS
python3 - "$H018_IID" "$H018_SOURCE" <<'PY'
import json,subprocess,sys
def image(i):return json.loads(subprocess.check_output(['podman','image','inspect',i]))[0]
base=image('sha256:46feffff8fe00e5993a8e0d35f5a7932f82ee43ef91d87759f568c3a6029dc1e')['RootFS']['Layers']
new=image(sys.argv[1]);assert new['Id'].removeprefix('sha256:')==sys.argv[1].removeprefix('sha256:')
assert new['RootFS']['Layers'][:-1]==base
assert new['Labels']['org.opencontainers.image.ai-harness.patchset']=='38d7b6a7978e5e95e69db790cf2e3465a0e33ddd27124b1b7af387518e9722bf'
assert new['Labels']['org.opencontainers.image.ai-harness.native-source']=='b948889814648ad761f40a18260ddbe6351c6bbf'
assert new['Labels']['org.opencontainers.image.ai-harness.source']==sys.argv[2]
PY
podman run --rm --pull=never --http-proxy=false --network none --read-only --cap-drop ALL --security-opt no-new-privileges --entrypoint cat "$H018_IID" /opt/ai-harness/config/active-frontier.json > private/image-active-frontier.json
cmp "$H018_NEW/config/active-frontier.json" private/image-active-frontier.json
podman run --rm --pull=never --http-proxy=false --network none --read-only --cap-drop ALL --security-opt no-new-privileges --entrypoint cat "$H018_IID" /opt/ai-harness/engine/configure-profile.mjs > private/image-configure-profile.mjs
cmp "$H018_NEW/deploy/engine/configure-profile.mjs" private/image-configure-profile.mjs
node --input-type=module - "$H018_NEW" "$H018_SHA" <<'JS'
import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {createHash} from 'node:crypto';import {pathToFileURL} from 'node:url';
const [root,sha]=process.argv.slice(2);
const {readMimoEvidence,validateMimoIntegration}=await import(pathToFileURL(root+'/server/dist/mimo-frontier.js'));
const receipt=readMimoEvidence('/etc/sova-qualification/mimo.json');assert.equal(createHash('sha256').update(receipt.text).digest('hex'),sha);
const validated=validateMimoIntegration(receipt.value);const {qualification,capacity}=validated;
const {validateCapacity,PROFILE_SHA256}=await import(pathToFileURL(process.cwd()+'/driver/preflight.mjs'));validateCapacity(receipt.value,validated);
assert.equal(createHash('sha256').update(readFileSync(root+'/deploy/engine/configure-profile.mjs')).digest('hex'),PROFILE_SHA256);const active=JSON.parse(readFileSync(root+'/config/active-frontier.json','utf8'));const candidate=JSON.parse(readFileSync(root+'/config/mimo-candidate.json','utf8'));
assert.equal(active.model,'mimo-v2.6-pro-rl');assert.equal(active.mimoEnabled,true);assert.equal(active.mimoQualificationSha256,sha);assert.equal(active.mimoContextWindow,qualification.identity.actualSlotContext);assert.equal(active.mimoMaxOutputTokens,65536);assert([1000192,1000000,950000,917504].includes(active.mimoContextWindow));assert(candidate.enabled&&candidate.qualified&&candidate.model===active.model);
JS
systemd-analyze --user verify "$H018_PREP/proposed/ai-harness.service"
if [[ $H018_MODE == --dry-run ]]; then echo 'PASS local pair checks only; W1/root live owner review still required. No tag/unit/service change.'; exit 0; fi
# This is the H013 paired promotion; partial failure leaves app held for review.
podman tag "$H018_IID" "$H018_TAG"
install -m 600 proposed/ai-harness.service "$H018_UNIT.h016-new"
mv "$H018_UNIT.h016-new" "$H018_UNIT"
sudo -n install -o root -g root -m 644 proposed/30-h008-registry.conf "$H018_STATUS.h016-new"
sudo -n mv "$H018_STATUS.h016-new" "$H018_STATUS"
systemctl --user daemon-reload
sudo -n systemctl daemon-reload
python3 "$H018_GUARD" > private/post-activation.json
echo "Pair paths/tag applied; app remains stopped. Keep app paused for separately gated H009-derived acceptance; start status/app only after root review of acceptance."
