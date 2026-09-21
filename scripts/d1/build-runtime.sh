#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then
  echo 'Usage: build-runtime.sh RUN_DIR'
  echo 'Requires RUN_DIR/{repo,source,tmp,evidence}; source must be clean pinned upstream Git. No service is launched.'
  exit 0
fi
[[ $# == 1 ]] || { echo 'Use --help' >&2; exit 2; }
RUN=$(realpath -e "$1")
[[ $RUN == /data/build/d1-* && -d $RUN/evidence && -d $RUN/tmp ]] || exit 2
cd "$RUN/repo"
python3 "$RUN/repo/scripts/d1/storage_guard.py"
export TMPDIR="$RUN/tmp" XDG_CACHE_HOME="$RUN/tmp/xdg" DOCKER_CONFIG="$RUN/tmp/docker-client"
mkdir -p "$DOCKER_CONFIG" "$XDG_CACHE_HOME"
exec 9>"$RUN/build.lock"
flock -n 9 || { echo 'Build already running' >&2; exit 1; }
GUARD="$RUN/repo/scripts/d1/storage_guard.py"
finish() {
  local rc=$?
  trap - EXIT
  if ! python3 "$GUARD" --report "$RUN/evidence/root-build-after.md" > "$RUN/evidence/storage-build-after.json"; then rc=1; fi
  if [[ $rc == 0 ]]; then printf 'PASS_BUILD_CUDA_CLI_ONLY\n' > "$RUN/build.state"; else printf 'FAILED_BUILD_OR_STORAGE\n' > "$RUN/build.state"; fi
  printf '%s\n' "$rc" > "$RUN/build.exit"
  date -u +%FT%TZ > "$RUN/build.finished"
  exit "$rc"
}
trap finish EXIT
printf 'VALIDATING\n' > "$RUN/build.state"
python3 "$GUARD" --report "$RUN/evidence/root-build-before.md" > "$RUN/evidence/storage-build-before.json"
[[ $(sudo -n env DOCKER_CONFIG="$DOCKER_CONFIG" TMPDIR="$TMPDIR" docker info --format '{{.DockerRootDir}}') == /data/docker ]]
[[ $(sudo -n awk '/^root =/ {gsub(/"/, "", $3); print $3}' /etc/containerd/config.toml) == /data/containerd/root ]]
[[ $(git -C "$RUN/source" rev-parse HEAD) == b29c606e28a01b1bc8c1351026a0fa6e616bf6c4 ]]
[[ -z $(git -C "$RUN/source" status --porcelain) ]]
git -C "$RUN/source" merge-base --is-ancestor ae9afff8d2c012ca760eb9c2adf41961cf6f6232 HEAD
[[ $(df -B1 --output=avail /data | tail -1) -gt 107374182400 ]]
echo $$ > "$RUN/build.pid"
date -u +%FT%TZ > "$RUN/build.started"
printf 'BUILDING\n' > "$RUN/build.state"
IMAGE=local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d1
sudo -n env DOCKER_CONFIG="$DOCKER_CONFIG" TMPDIR="$TMPDIR" docker build --progress=plain --platform linux/amd64 \
  --build-arg LLAMA_COMMIT=b29c606e28a01b1bc8c1351026a0fa6e616bf6c4 \
  --build-arg CUDA_ARCHITECTURES=120a-real --build-arg BUILD_JOBS=8 \
  --build-arg UBUNTU_SNAPSHOT=20260914T000000Z \
  --iidfile "$RUN/evidence/image.iid" -t "$IMAGE" \
  -f "$RUN/repo/containers/llama-cpp/Dockerfile" "$RUN/source"
printf 'BUILT_CHECKING\n' > "$RUN/build.state"
IID=$(cat "$RUN/evidence/image.iid")
sudo -n env DOCKER_CONFIG="$DOCKER_CONFIG" TMPDIR="$TMPDIR" docker image inspect "$IID" --format '{{.Id}} {{.Architecture}} {{.Os}} {{json .Config.Labels}}' > "$RUN/evidence/image-identity.txt"
for mode in version help list-devices; do
  timeout 120 sudo -n env DOCKER_CONFIG="$DOCKER_CONFIG" TMPDIR="$TMPDIR" docker run --rm --network none --read-only --gpus all \
    --log-driver none --tmpfs /tmp:rw,size=64m --cap-drop ALL \
    --security-opt no-new-privileges "$IID" "--$mode" > "$RUN/evidence/llama-server-$mode.txt" 2>&1
done
grep -q b29c606 "$RUN/evidence/llama-server-version.txt"
for option in cpu-moe n-cpu-moe device tensor-split split-mode jinja api-key-file no-webui load-mode alias host port parallel ctx-size; do
  grep -q -- "--$option" "$RUN/evidence/llama-server-help.txt"
done
grep -q 'CUDA0' "$RUN/evidence/llama-server-list-devices.txt"
grep -q 'CUDA1' "$RUN/evidence/llama-server-list-devices.txt"
# Copy only compiler/package/build evidence, not weights; no container is started.
CID=$(sudo -n env DOCKER_CONFIG="$DOCKER_CONFIG" TMPDIR="$TMPDIR" docker create --network none "$IID")
for file in CMakeCache.txt build-packages.tsv nvcc-version.txt source-commit.txt; do
  sudo -n env DOCKER_CONFIG="$DOCKER_CONFIG" TMPDIR="$TMPDIR" docker cp "$CID:/opt/llama/$file" "$RUN/evidence/$file"
done
sudo -n env DOCKER_CONFIG="$DOCKER_CONFIG" TMPDIR="$TMPDIR" docker rm "$CID" >/dev/null
printf 'CHECKS_COMPLETE_AWAITING_FINAL_GUARD\n' > "$RUN/build.state"
