#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'Focused final-image layer, complete inventory, profile and CLI lineage checks; offline only.'; exit 0; fi
umask 077
cd /home/user/ai-harness-build/H017-SOURCE-PREP01-20260927
H017_IMAGE=$(cat final-stage/final-combined.iid)
H017_PRIOR=/home/user/ai-harness-build/H016-MIMO-BUILD-20260927
common=(--rm --pull=never --http-proxy=false --network none --userns keep-id --user 1000:1000 --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --tmpfs /tmp:rw,nosuid,nodev,size=512m,mode=1777)
podman image inspect "$H017_IMAGE" > private/final-inspect.json
podman image inspect sha256:46feffff8fe00e5993a8e0d35f5a7932f82ee43ef91d87759f568c3a6029dc1e > private/base-inspect.json
timeout --kill-after=10 120 podman run "${common[@]}" --volume "$H017_PRIOR/image-inventory.py:/inventory.py:ro" --entrypoint python3 "$H017_IMAGE" /inventory.py > private/final-inventory.json
python3 verify-image.py > private/IMAGE-CHECKS.json
timeout --kill-after=10 100 podman run "${common[@]}" --env HOME=/tmp --volume "$PWD/source/ai-harness/deploy/engine/configure-profile.test.mjs:/opt/ai-harness/engine/configure-profile.test.mjs:ro" --entrypoint node "$H017_IMAGE" --test --test-name-pattern='MiMo|H017|managed.frontier' /opt/ai-harness/engine/configure-profile.test.mjs > private/image-profile-tests.tap 2>&1
timeout --kill-after=10 60 podman run "${common[@]}" --env HOME=/tmp --env MCODE_DISABLE_TELEMETRY=1 --entrypoint node "$H017_IMAGE" /opt/minimax/cli.js --version > private/cli-version.txt 2>&1
