#!/usr/bin/env bash
set -euo pipefail

GUARD="scripts/common/root-disk-guard.sh"
REPO_ROOT=$(pwd)
FIXTURE_PARENT="$REPO_ROOT/tests/fixtures"
FIXTURE_ROOT=$(mktemp -d "$FIXTURE_PARENT/root-disk-guard.XXXXXX")

cleanup() {
  if [[ -n "${FIXTURE_ROOT:-}" && "$FIXTURE_ROOT" == "$FIXTURE_PARENT"/root-disk-guard.* && -d "$FIXTURE_ROOT" ]]; then
    rm -rf "$FIXTURE_ROOT"
  fi
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

make_tree() {
  local root="$1"
  mkdir -p \
    "$root/home/user/.cache/huggingface" \
    "$root/home/user/codex-bootstrap" \
    "$root/var/lib/docker" \
    "$root/var/lib/containerd" \
    "$root/var/log" \
    "$root/tmp" \
    "$root/data/models"
}

run_guard() {
  local root="$1"
  local report="$2"
  "$GUARD" \
    --root-path "$root" \
    --data-path "$root/data" \
    --report "$report" \
    --skip-mount-check-for-tests \
    --no-sudo \
    --warn-root-free-gib 0 \
    --min-root-free-gib 0 \
    --warn-path-mib 2 \
    --fail-path-mib 2 \
    --large-file-mib 1
}

clean_root="$FIXTURE_ROOT/clean-root"
make_tree "$clean_root"
run_guard "$clean_root" "$FIXTURE_ROOT/clean-report.md" >/dev/null || fail "clean fake root should pass"

model_root="$FIXTURE_ROOT/model-root"
make_tree "$model_root"
dd if=/dev/zero of="$model_root/home/user/.cache/huggingface/model.gguf" bs=1M count=3 status=none
if run_guard "$model_root" "$FIXTURE_ROOT/model-report.md" >/dev/null 2>&1; then
  fail "large model-like file on fake root should stop"
fi

data_model_root="$FIXTURE_ROOT/data-model-root"
make_tree "$data_model_root"
dd if=/dev/zero of="$data_model_root/data/models/model.gguf" bs=1M count=3 status=none
run_guard "$data_model_root" "$FIXTURE_ROOT/data-model-report.md" >/dev/null || fail "large model-like file under fake data path should pass"

docker_root="$FIXTURE_ROOT/docker-root"
make_tree "$docker_root"
dd if=/dev/zero of="$docker_root/var/lib/docker/layer.dat" bs=1M count=3 status=none
if run_guard "$docker_root" "$FIXTURE_ROOT/docker-report.md" >/dev/null 2>&1; then
  fail "large fake Docker root path should stop"
fi

bootstrap_root="$FIXTURE_ROOT/bootstrap-root"
make_tree "$bootstrap_root"
printf 'small bootstrap file\n' > "$bootstrap_root/home/user/codex-bootstrap/README.md"
run_guard "$bootstrap_root" "$FIXTURE_ROOT/bootstrap-report.md" >/dev/null || fail "small codex bootstrap path should not stop"

[[ ! -e /tmp/root-disk-guard-fixture-real-root-marker ]] || fail "fixture touched unexpected real root marker"

echo "PASS: root-disk guard fixture checks"
