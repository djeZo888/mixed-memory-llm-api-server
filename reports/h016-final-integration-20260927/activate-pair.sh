#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'HELD, NOT EXECUTABLE: activate-pair.sh REVIEWED_MANIFEST_SHA256 QUALIFIED_IMAGE_ID [--dry-run|--apply]. Default dry-run. Read ACTIVATION.md first; W1 current clean-owner/readiness proof is mandatory.'; exit 0; fi
echo 'HELD: native qualification, current clean production owner, root GO and application acceptance are absent. No activation action permitted by this draft.' >&2
exit 78
# Retained review-only draft body; revise only through the later narrow root review.
umask 077
H016_SHA=${1:?exact root-reviewed qualification hash required}
H016_IID=${2:?exact root-reviewed qualified config image ID required}
H016_MODE=${3:---dry-run}
[[ $H016_MODE == --dry-run || $H016_MODE == --apply ]]
[[ $H016_SHA =~ ^[a-f0-9]{64}$ && $H016_IID =~ ^sha256:[a-f0-9]{64}$ ]]
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
H016_PREP=/home/user/ai-harness-build/H016-FINAL-INTEGRATION-20260927
H016_BUILD=/home/user/ai-harness-build/H016-MIMO-BUILD-20260927
H016_NEW=/opt/ai-harness/releases/df0702412b1a8f594db7d3211ca63f6aafe8a026-h016/ai-harness
H016_TAG=localhost/ai-harness-engine:0.0.2-ae65651df5f9
H016_UNIT=/home/user/.config/systemd/user/ai-harness.service
H016_STATUS=/etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf
cd "$H016_PREP"
python3 "$H016_BUILD/guard.py" > private/pre-activation.json
test "$(podman image inspect "$H016_TAG" --format '{{.Id}}')" = 9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c
printf '%s\n' 'eee8e1d7a3f370e3fcdbf5783f1b03df8672296abcf27726cdaca73c62b71b9c  /home/user/.config/systemd/user/ai-harness.service' 'e033a07a50b8c5f9f535909e1405c87f99f932a3c1506aa36c30a4647462ac16  /etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf' 'e8cdf8f8015fb25bea744fc036405b0e7ad0c8692170791f4d66995582ccccde  proposed/ai-harness.service' '45fcd10bad42bb903ced6b32d8621e34377e06077b1ca3c5536056da19a4be79  proposed/30-h008-registry.conf' | sha256sum -c -
python3 - "$H016_IID" <<'PY'
import json,subprocess,sys
def image(i):return json.loads(subprocess.check_output(['podman','image','inspect',i]))[0]
base=image('sha256:6641df04cf4e8375029639a67c22da7c3ff4719d2b8e58748572f049de8fb022')['RootFS']['Layers']
new=image(sys.argv[1]);assert new['Id'].removeprefix('sha256:')==sys.argv[1].removeprefix('sha256:')
assert new['RootFS']['Layers'][:-1]==base
assert new['Labels']['org.opencontainers.image.ai-harness.source']=='928b3b470058241f089a839367d4b30d5887a6e3'
PY
podman run --rm --pull=never --http-proxy=false --network none --read-only --cap-drop ALL --security-opt no-new-privileges --entrypoint cat "$H016_IID" /opt/ai-harness/config/active-frontier.json > private/image-active-frontier.json
cmp "$H016_NEW/config/active-frontier.json" private/image-active-frontier.json
podman run --rm --pull=never --http-proxy=false --network none --read-only --cap-drop ALL --security-opt no-new-privileges --entrypoint cat "$H016_IID" /opt/ai-harness/deploy/engine/configure-profile.mjs > private/image-configure-profile.mjs
cmp "$H016_NEW/deploy/engine/configure-profile.mjs" private/image-configure-profile.mjs
node --input-type=module - "$H016_NEW" "$H016_SHA" <<'JS'
import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {createHash} from 'node:crypto';import {pathToFileURL} from 'node:url';
const [root,sha]=process.argv.slice(2);
const {readMimoEvidence,validateMimoIntegration}=await import(pathToFileURL(root+'/server/dist/mimo-frontier.js'));
const receipt=readMimoEvidence('/etc/sova-qualification/mimo.json');assert.equal(createHash('sha256').update(receipt.text).digest('hex'),sha);
const validated=validateMimoIntegration(receipt.value);const {qualification,capacity}=validated;
const {validateCapacity,PROFILE_SHA256}=await import(pathToFileURL(process.cwd()+'/driver/preflight.mjs'));validateCapacity(receipt.value,validated);
assert.equal(createHash('sha256').update(readFileSync(root+'/deploy/engine/configure-profile.mjs')).digest('hex'),PROFILE_SHA256);const active=JSON.parse(readFileSync(root+'/config/active-frontier.json','utf8'));const candidate=JSON.parse(readFileSync(root+'/config/mimo-candidate.json','utf8'));
assert.equal(active.model,'mimo-v2.6-pro-rl');assert.equal(active.mimoEnabled,true);assert.equal(active.mimoQualificationSha256,sha);assert.equal(active.mimoContextWindow,qualification.identity.actualSlotContext);assert.equal(active.mimoMaxOutputTokens,65536);assert([1000000,917504].includes(active.mimoContextWindow));assert(candidate.enabled&&candidate.qualified&&candidate.model===active.model);
JS
systemd-analyze --user verify "$H016_PREP/proposed/ai-harness.service"
if [[ $H016_MODE == --dry-run ]]; then echo 'PASS local pair checks only; W1/root live owner review still required. No tag/unit/service change.'; exit 0; fi
# This is the H013 paired promotion; partial failure leaves app held for review.
podman tag "$H016_IID" "$H016_TAG"
install -m 600 proposed/ai-harness.service "$H016_UNIT.h016-new"
mv "$H016_UNIT.h016-new" "$H016_UNIT"
sudo -n install -o root -g root -m 644 proposed/30-h008-registry.conf "$H016_STATUS.h016-new"
sudo -n mv "$H016_STATUS.h016-new" "$H016_STATUS"
systemctl --user daemon-reload
sudo -n systemctl daemon-reload
echo "Pair paths/tag proposed only. Keep app paused for separately gated H009-derived acceptance; start status/app only after root review of acceptance."
