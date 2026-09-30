#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'Retry only exact H013 engine build with locked dependency network access; no activation'; exit 0; fi
umask 077
H013_TASK=/home/user/ai-harness-build/H013-SOVA-1M-20260927
cd "$H013_TASK"
H013_SOURCE=$(cat source.commit)
[[ "$H013_SOURCE" =~ ^[a-f0-9]{40}$ ]]
python3 preservation.py pre-retry.json --compare before.json
sha256sum -c source.SHA256SUMS
trap 'rc=$?; trap - EXIT; printf "%s\n" "$rc" > "$H013_TASK/engine-retry.exit"; date -u +%FT%TZ > "$H013_TASK/engine-retry.finished"; exit "$rc"' EXIT
cd source/ai-harness
cache_root=/home/user/ai-harness-h003-engine-mcp-build-20260923
timeout --signal=TERM --kill-after=30s 600s podman --remote=false build --layers --format docker --pull=never --network slirp4netns --target runtime --volume "$H013_TASK/artifact-cache:/build/minimax/.cache/artifacts:rw,rprivate" --volume "$cache_root/native-deps-cache:/tmp/ai-harness-native-deps-cache:ro,rprivate" --build-arg AI_HARNESS_NATIVE_DEPS_CACHE=1 --file deploy/Containerfile --jobs=1 --tag "localhost/ai-harness-engine:h013-$H013_SOURCE" --iidfile "$H013_TASK/candidate.iid" . > "$H013_TASK/engine-retry.log" 2>&1
image_id=$(cat "$H013_TASK/candidate.iid")
timeout --signal=TERM --kill-after=15s 120s podman run --rm --name h013-offline-profile-probe --pull=never --http-proxy=false --network none --userns keep-id --user 1000:1000 --cap-drop ALL --security-opt no-new-privileges --read-only --pids-limit 128 --tmpfs /tmp:rw,nosuid,nodev,size=128m,mode=1777 --env HOME=/tmp --entrypoint sh "$image_id" -c 'node /opt/minimax/cli.js --version && cat /opt/minimax/patched-source-revision.txt && node --test /opt/ai-harness/engine/configure-profile.test.mjs && sha256sum /opt/ai-harness/engine/configure-profile.mjs /opt/minimax/cli.js /opt/minimax/native-probes.mjs /opt/minimax/source-pnpm-lock.yaml' > "$H013_TASK/candidate-probe.log" 2>&1
find server/dist web/dist -type f -print0 | sort -z | xargs -0 sha256sum > "$H013_TASK/artifacts.SHA256SUMS"
python3 "$H013_TASK/preservation.py" "$H013_TASK/after.json" --compare "$H013_TASK/before.json"
