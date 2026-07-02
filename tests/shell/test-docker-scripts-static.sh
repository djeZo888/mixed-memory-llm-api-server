#!/usr/bin/env bash
set -euo pipefail

scripts=(
  scripts/docker/install-docker.sh
  scripts/docker/configure-docker-data-root.sh
  scripts/docker/verify-docker-storage.sh
)

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

for script in "${scripts[@]}"; do
  [[ -f "$script" ]] || fail "$script missing"
  [[ -x "$script" ]] || fail "$script is not executable"
  grep -q 'set -euo pipefail' "$script" || fail "$script lacks set -euo pipefail"
  "$script" --help >/dev/null || fail "$script --help failed"
done

scripts/docker/install-docker.sh --dry-run >/dev/null || fail "install dry-run failed"
scripts/docker/configure-docker-data-root.sh --dry-run >/dev/null || fail "configure dry-run failed"

if scripts/docker/install-docker.sh >/tmp/m4-install-no-flag.out 2>/tmp/m4-install-no-flag.err; then
  fail "install script did not refuse missing --yes-install-docker"
fi
grep -q -- '--yes-install-docker' /tmp/m4-install-no-flag.err || fail "install refusal did not mention --yes-install-docker"

if scripts/docker/configure-docker-data-root.sh >/tmp/m4-configure-no-flag.out 2>/tmp/m4-configure-no-flag.err; then
  fail "configure script did not refuse missing --yes-configure-docker-storage"
fi
grep -q -- '--yes-configure-docker-storage' /tmp/m4-configure-no-flag.err || fail "configure refusal did not mention --yes-configure-docker-storage"

for script in scripts/docker/install-docker.sh scripts/docker/configure-docker-data-root.sh scripts/docker/verify-docker-storage.sh; do
  grep -q 'scripts/common/require-data-mounted.sh' "$script" || fail "$script must call require-data-mounted.sh"
  grep -q 'scripts/common/root-disk-guard.sh' "$script" || fail "$script must call root-disk-guard.sh"
  grep -q '/data/docker' "$script" || fail "$script missing /data/docker policy"
  grep -q '/data/containerd' "$script" || fail "$script missing /data/containerd policy"
done

if grep -RInE 'get\.docker\.com|curl[[:space:]].*sh|bash[[:space:]]*<|sh[[:space:]]*<' "${scripts[@]}"; then
  fail "Docker convenience script reference found"
fi

if grep -RInE 'usermod[[:space:]].*docker|gpasswd[[:space:]].*docker|groupadd[[:space:]].*docker' "${scripts[@]}"; then
  fail "script attempts to add a user to docker group"
fi

if grep -RInE 'nvidia|nvidia-ctk|container-toolkit' "${scripts[@]}"; then
  fail "script references NVIDIA Container Toolkit work"
fi

if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "${scripts[@]}"; then
  fail "hard-coded secret-like content found"
fi

echo "PASS: Docker/containerd script static checks"
