#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'Build reviewed two-file H013 overlay from exact deployed engine, no activation'; exit 0; fi
umask 077
H013_TASK=/home/user/ai-harness-build/H013-SOVA-1M-20260927
cd "$H013_TASK"
python3 preservation.py pre-overlay.json --compare before.json
python3 - <<'PY'
import json,pathlib,hashlib
r=json.loads(pathlib.Path('engine-source-comparison.json').read_text())
assert r['base_image']=='c328dac0e6ede1dfb890a0657ebafd6f6fd4a1f2281f4e1c664ab95db7dcaa20'
assert [d['source'] for d in r['deltas']]==['deploy/engine/configure-profile.mjs','deploy/engine/configure-profile.test.mjs']
for d in r['entries']:
 assert hashlib.sha256((pathlib.Path('source/ai-harness')/d['source']).read_bytes()).hexdigest()==d['sha256']
PY
mkdir -m 700 profile-overlay
cp source/ai-harness/deploy/engine/configure-profile.mjs source/ai-harness/deploy/engine/configure-profile.test.mjs profile-overlay/
cp Containerfile.profile-overlay profile-overlay/Containerfile
podman --remote=false build --format docker --pull=never --network none --tag localhost/ai-harness-engine:h013-7143c17-profile --iidfile candidate-overlay.iid profile-overlay > overlay-build.log 2>&1
image_id=$(cat candidate-overlay.iid)
timeout --signal=TERM --kill-after=15s 90s podman run --rm --name h013-profile-overlay-probe --pull=never --http-proxy=false --network none --userns keep-id --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges --read-only --pids-limit 128 --tmpfs /tmp:rw,nosuid,nodev,size=128m,mode=1777 --env HOME=/tmp --entrypoint sh "$image_id" -c 'node /opt/minimax/cli.js --version && cat /opt/minimax/patched-source-revision.txt && node --test /opt/ai-harness/engine/configure-profile.test.mjs && sha256sum /opt/ai-harness/engine/configure-profile.mjs /opt/ai-harness/engine/configure-profile.test.mjs /opt/minimax/cli.js /opt/minimax/native-probes.mjs /opt/minimax/source-pnpm-lock.yaml' > overlay-probe.log 2>&1
(cd source/ai-harness; find server/dist web/dist -type f -print0 | sort -z | xargs -0 sha256sum) > artifacts.SHA256SUMS
python3 preservation.py after.json --compare before.json
printf '0\n' > overlay.exit
