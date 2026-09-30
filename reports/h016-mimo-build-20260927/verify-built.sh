#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'Verify H016 final image offline; fresh private final fixture path required. No backend/tool execution.'; exit 0; fi
umask 077
cd /home/user/ai-harness-build/H016-MIMO-BUILD-20260927
python3 guard.py > pre-final-probes.json
H016_IMAGE=$(cat candidate.iid)
common=(--rm --pull=never --http-proxy=false --network none --userns keep-id --user 1000:1000 --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --tmpfs /tmp:rw,nosuid,nodev,size=512m,mode=1777)
timeout --kill-after=10 100 podman run "${common[@]}" --env HOME=/tmp --volume "$PWD/source/ai-harness/deploy/engine/configure-profile.test.mjs:/opt/ai-harness/engine/configure-profile.test.mjs:ro" --entrypoint node "$H016_IMAGE" --test /opt/ai-harness/engine/configure-profile.test.mjs > profile-final.log 2>&1
timeout --kill-after=10 60 podman run "${common[@]}" --env HOME=/tmp --volume "$PWD/estimator-probe.mjs:/estimator-probe.mjs:ro" --entrypoint node "$H016_IMAGE" /estimator-probe.mjs > estimator-final.json
timeout --kill-after=10 100 podman run "${common[@]}" --name h016-final-offline-roster --env HOME=/tmp/profile/home --env MINIMAX_DATA_DIR=/tmp/profile --env MCODE_DISABLE_TELEMETRY=1 --volume "$PWD/source/ai-harness:/h016:ro" --volume "$PWD/capture-production-roster.mjs:/capture.mjs:ro" --volume "$PWD/private:/output:rw" --entrypoint sh "$H016_IMAGE" -c 'mkdir -m700 /tmp/profile /tmp/workspace; cd /tmp/workspace; node /capture.mjs /opt/minimax/native-probes.mjs /output/mimo-production-fixture-final-65536.json' > roster-final.private.log 2>&1
python3 guard.py > after-final-probes.json
