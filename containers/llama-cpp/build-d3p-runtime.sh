#!/usr/bin/env bash
set -euo pipefail
usage() {
  cat <<'EOF'
Usage: build-d3p-runtime.sh [--dry-run] RUN_DIR

Future separately authorized legacy ai-vm Linux/CUDA build only; not run during source D3P.
Requires RUN_DIR=/data/build/d3p-*/ with clean repo/, clean pinned source/,
existing tmp/ and evidence/. Docker BuildKit must support named build contexts.
--dry-run uses disposable Git scratch; no persistent source changes, build evidence or Docker.
Registered fresh hosts require a reviewed storage/report runner integration first.
No model is loaded, no service is started, and D1 rollback evidence is untouched.
EOF
}
if [[ ${1:-} == --help ]]; then usage; exit 0; fi
DRY_RUN=0
if [[ ${1:-} == --dry-run ]]; then DRY_RUN=1; shift; fi
[[ $# == 1 ]] || { usage >&2; exit 2; }
if [[ -e /etc/local-ai-server || -L /etc/local-ai-server ]]; then
  echo 'STOP: this runner retains legacy ai-vm storage guards; registered-host integration is a separate review seam' >&2
  exit 1
fi
RUN=$(realpath -e "$1")
[[ $RUN == /data/build/d3p-* && -d $RUN/evidence && -d $RUN/tmp ]] || exit 2
for directory in repo source tmp evidence; do
  [[ $(realpath -e "$RUN/$directory") == "$RUN/$directory" ]]
  [[ $(stat -c %d "$RUN/$directory") == "$(stat -c %d /data)" ]]
done
export TMPDIR="$RUN/tmp"
REPO="$RUN/repo"
RECIPE="$REPO/containers/llama-cpp"
[[ $(realpath -e "$0") == "$RECIPE/build-d3p-runtime.sh" ]]
[[ -z $(git -C "$REPO" status --porcelain=v1 --untracked-files=all --ignored=matching) ]]
GUARD="$REPO/scripts/d1/storage_guard.py"
python3 "$GUARD"
"$REPO/scripts/common/require-data-mounted.sh"
python3 "$RECIPE/prepare-d3p-source.py" "$RUN/source" --check-only
PATCH_SHA256=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["patch_sha256"])' "$RECIPE/d3p-source.json")
DERIVED_TREE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["derived_tree"])' "$RECIPE/d3p-source.json")
IMAGE="local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-${PATCH_SHA256:0:12}"
if [[ $DRY_RUN == 1 ]]; then
  printf 'PASS_SOURCE_PREFLIGHT_ONLY\nImage tag planned: %s\nDerived Git tree: %s\n' "$IMAGE" "$DERIVED_TREE"
  exit 0
fi
# Storage checks precede build logs/service data and run again on every exit.
exec 9>"$RUN/build.lock"
flock -n 9 || { echo 'Build already running' >&2; exit 1; }
[[ ! -e $RUN/evidence/image.iid ]]
finish() {
  local rc=$?
  trap - EXIT
  # Never write completion evidence through a failed/missing data mount.
  if ! python3 "$GUARD"; then exit 1; fi
  if ! "$REPO/scripts/common/require-data-mounted.sh"; then exit 1; fi
  if ! "$REPO/scripts/common/root-disk-guard.sh" --report "$RUN/evidence/root-build-after.md"; then exit 1; fi
  if [[ $rc == 0 ]]; then printf 'PASS_BUILD_ONLY\n' > "$RUN/build.state"; else printf 'FAILED_BUILD_OR_STORAGE\n' > "$RUN/build.state"; fi
  printf '%s\n' "$rc" > "$RUN/build.exit"
  date -u +%FT%TZ > "$RUN/build.finished"
  exit "$rc"
}
"$REPO/scripts/common/root-disk-guard.sh" --report "$RUN/evidence/root-build-before.md"
trap finish EXIT
export TMPDIR="$RUN/tmp" XDG_CACHE_HOME="$RUN/tmp/xdg" DOCKER_CONFIG="$RUN/tmp/docker-client"
mkdir -p "$DOCKER_CONFIG" "$XDG_CACHE_HOME"
[[ $(sudo -n env DOCKER_CONFIG="$DOCKER_CONFIG" TMPDIR="$TMPDIR" docker info --format '{{.DockerRootDir}}') == /data/docker ]]
[[ $(sudo -n awk '/^root =/ {gsub(/"/, "", $3); print $3}' /etc/containerd/config.toml) == /data/containerd/root ]]
[[ $(df -B1 --output=avail /data | tail -1) -gt 107374182400 ]]
# Build evidence is for this new run only; never overwrite a completed image proof.
git -C "$REPO" rev-parse HEAD > "$RUN/evidence/build-repository-commit.txt"
(cd "$RECIPE" && sha256sum Dockerfile.d3p Dockerfile.d3p.dockerignore prepare-d3p-source.py build-d3p-runtime.sh d3p-source.json strict-model-chat.patch) > "$RUN/evidence/build-recipe-sha256.txt"
python3 "$RECIPE/prepare-d3p-source.py" "$RUN/source" --check-only > "$RUN/evidence/source-preflight.json"
printf '%s\n' "$IMAGE" > "$RUN/evidence/image-tag.txt"
date -u +%FT%TZ > "$RUN/build.started"
printf 'BUILDING\n' > "$RUN/build.state"
sudo -n env DOCKER_CONFIG="$DOCKER_CONFIG" TMPDIR="$TMPDIR" docker build --progress=plain --platform linux/amd64 \
  --build-context "d3p=$RECIPE" \
  --build-arg "D3P_PATCH_SHA256=$PATCH_SHA256" --build-arg "D3P_DERIVED_TREE=$DERIVED_TREE" \
  --build-arg CUDA_ARCHITECTURES=120a-real --build-arg BUILD_JOBS=8 \
  --build-arg UBUNTU_SNAPSHOT=20260914T000000Z \
  --iidfile "$RUN/evidence/image.iid" -t "$IMAGE" \
  -f "$RECIPE/Dockerfile.d3p" "$RUN/source"
IID=$(cat "$RUN/evidence/image.iid")
[[ $IID =~ ^sha256:[0-9a-f]{64}$ ]]
sudo -n env DOCKER_CONFIG="$DOCKER_CONFIG" TMPDIR="$TMPDIR" docker image inspect "$IID" \
  --format '{{.Id}} {{.Architecture}} {{.Os}} {{json .Config.Labels}}' > "$RUN/evidence/image-identity.txt"
printf 'BUILD_COMPLETE_AWAITING_FINAL_GUARDS\n' > "$RUN/build.state"
