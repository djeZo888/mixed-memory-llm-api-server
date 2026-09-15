#!/usr/bin/env bash
set -euo pipefail
usage() {
  cat <<'EOF'
Usage: build-d3p-runtime.sh [--dry-run] RUN_DIR

Future separately authorized existing ai-vm Linux/CUDA build only; source-only here.
Requires RUN_DIR=/data/build/d3p-*/ with clean repo/, clean pinned source/,
existing tmp/ and evidence/. Docker BuildKit must support named build contexts.
--dry-run uses disposable Git scratch; no persistent source changes, build evidence or Docker.
Registered hosts require the exact protected L2 guard and a pre-created root-owned
/data/logs/<run basename>/ directory. Canonical D3 guards remain external preflight.
No model is loaded, no service is started, and D1 rollback evidence is untouched.
EOF
}
if [[ ${1:-} == --help ]]; then usage; exit 0; fi
DRY_RUN=0
if [[ ${1:-} == --dry-run ]]; then DRY_RUN=1; shift; fi
[[ $# == 1 ]] || { usage >&2; exit 2; }
REGISTERED=0
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
REGISTERED_GUARD=/usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py
# Only these two files are loaded by the reviewed registered guard/report path.
# Verify the installed closure, not imports from a user-owned checkout.
registered_guard() {
  local relative expected path ancestor mode
  while read -r expected relative; do
    path="/usr/local/lib/llm-server/control-api/$relative"
    [[ -f $path && ! -L $path && $(stat -c %h "$path") == 1 ]] || return 1
    ancestor=$path
    while [[ $ancestor != / ]]; do
      [[ ! -L $ancestor && $(stat -c %u "$ancestor") == 0 ]] || return 1
      mode=$(stat -c %a "$ancestor")
      (( (8#$mode & 8#022) == 0 )) || return 1
      ancestor=${ancestor%/*}
      [[ -n $ancestor ]] || ancestor=/
    done
    [[ $(sha256sum "$path") == "$expected  $path" ]] || return 1
  done <<'CLOSURE'
21cf082a841aeab9470bd6704b77104961b9d4afcaec696d90aa22b65f5b6f3d scripts/common/registered-storage.py
4f834e92d149ea1955e79d34c53c18bf8c5846a4121d779e135a50d31a615505 scripts/install/storage.py
CLOSURE
  sudo -n /usr/bin/python3 -I -B "$REGISTERED_GUARD" "$@"
}
storage_checks() {
  # Latch registration even if it appears during a legacy build. Its removal or
  # any guard error must never enable a fallback to historical UUIDs.
  if [[ -e /etc/local-ai-server || -L /etc/local-ai-server ]]; then REGISTERED=1; fi
  if [[ $REGISTERED == 1 ]]; then
    registered_guard --json | /usr/bin/python3 -I -B -c '
import json, sys
value = json.load(sys.stdin)
assert value["data"]["path"] == value["data"]["mount"] == "/data"
assert value["models"]["path"] == value["models"]["mount"] == "/data/models-large"
assert value["roots"]["logs"] == "/data/logs"
'
  else
    python3 "$GUARD" || return 1
    "$REPO/scripts/common/require-data-mounted.sh"
  fi
}
root_report() {
  storage_checks || return 1
  if [[ $REGISTERED == 1 ]]; then
    registered_guard --root-guard --report "/data/logs/${RUN##*/}/root-build-$1.json"
  else
    "$REPO/scripts/common/root-disk-guard.sh" --report "$RUN/evidence/root-build-$1.md"
  fi
}
storage_checks
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
  if ! root_report after; then exit 1; fi
  if [[ $rc == 0 ]]; then printf 'PASS_BUILD_ONLY\n' > "$RUN/build.state"; else printf 'FAILED_BUILD_OR_STORAGE\n' > "$RUN/build.state"; fi
  printf '%s\n' "$rc" > "$RUN/build.exit"
  date -u +%FT%TZ > "$RUN/build.finished"
  exit "$rc"
}
root_report before
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
