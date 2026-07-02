#!/usr/bin/env bash
set -euo pipefail

VERIFIER="scripts/storage/verify-data-mount.sh"
FIXTURE_ROOT=$(mktemp -d tests/fixtures/storage-verifier-docker-permissions.XXXXXX)

cleanup() {
  if [[ -n "${FIXTURE_ROOT:-}" && "$FIXTURE_ROOT" == tests/fixtures/storage-verifier-docker-permissions.* && -d "$FIXTURE_ROOT" ]]; then
    rm -rf "$FIXTURE_ROOT"
  fi
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

make_fixture() {
  rm -rf "$FIXTURE_ROOT"
  mkdir -p "$FIXTURE_ROOT/docker" "$FIXTURE_ROOT/containerd/root"
  chmod 0711 "$FIXTURE_ROOT/docker"
  chmod 0711 "$FIXTURE_ROOT/containerd"
  chmod 0700 "$FIXTURE_ROOT/containerd/root"
}

run_fixture() {
  "$VERIFIER" --permission-fixture-root "$FIXTURE_ROOT" >/dev/null
}

make_fixture
run_fixture || fail "pre-Docker placeholder permissions should pass"

make_fixture
chmod 0710 "$FIXTURE_ROOT/docker"
run_fixture || fail "Docker-managed /data/docker mode 0710 should pass"

make_fixture
chmod 0777 "$FIXTURE_ROOT/docker"
if run_fixture; then
  fail "world-writable Docker data-root fixture should fail"
fi

make_fixture
chmod 0700 "$FIXTURE_ROOT/containerd/root"
run_fixture || fail "containerd root mode 0700 should pass"

make_fixture
chmod 0704 "$FIXTURE_ROOT/containerd/root"
if run_fixture; then
  fail "world-readable containerd root fixture should fail"
fi

make_fixture
chmod 0702 "$FIXTURE_ROOT/containerd/root"
if run_fixture; then
  fail "world-writable containerd root fixture should fail"
fi

echo "PASS: storage verifier Docker-managed permission fixtures"
