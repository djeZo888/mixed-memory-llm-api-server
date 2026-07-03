#!/usr/bin/env bash
set -euo pipefail

install_script="scripts/nvidia/install-nvidia-container-toolkit.sh"
verify_script="scripts/nvidia/verify-gpu-containers.sh"
scripts=("$install_script" "$verify_script")

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

"$install_script" --dry-run >/dev/null || fail "install script dry-run failed"

if "$install_script" >/tmp/m6a-install-no-flag.out 2>/tmp/m6a-install-no-flag.err; then
  fail "install script did not refuse missing --yes-install-nvidia-container-toolkit"
fi
grep -q -- '--yes-install-nvidia-container-toolkit' /tmp/m6a-install-no-flag.err || fail "install refusal did not mention --yes-install-nvidia-container-toolkit"

grep -q 'scripts/common/require-data-mounted.sh' "$install_script" || fail "install script must call require-data-mounted.sh"
grep -q 'scripts/common/root-disk-guard.sh' "$install_script" || fail "install script must call root-disk-guard.sh"
grep -q 'scripts/docker/verify-docker-storage.sh' "$install_script" || fail "install script must call verify-docker-storage.sh"
grep -q 'apt-get -s install' "$install_script" || fail "install script must simulate apt before install"
grep -q 'FORBIDDEN_PACKAGE_PATTERN' "$install_script" || fail "install script must define forbidden package guard"
grep -q 'sudo -n nvidia-ctk runtime configure --runtime=docker' "$install_script" || fail "install script must reference nvidia-ctk runtime configure --runtime=docker"
grep -q '/etc/docker/daemon.json' "$install_script" || fail "install script must reference Docker daemon.json"
grep -q 'cp -a "$DOCKER_DAEMON_JSON" "$backup_path"' "$install_script" || fail "install script must back up daemon.json"
grep -q '/data/docker' "$install_script" || fail "install script must preserve Docker data-root /data/docker"
grep -q '"data-root"' "$install_script" || fail "install script must verify Docker data-root"
grep -q 'python3 -m json.tool' "$install_script" || fail "install script must validate Docker daemon JSON"
grep -q 'sha256sum "$CONTAINERD_CONFIG"' "$install_script" || fail "install script must verify containerd config is unchanged"

if grep -q 'runtime configure --runtime=containerd' "$install_script"; then
  fail "install script must not configure containerd NVIDIA runtime in M6"
fi
if grep -q 'systemctl restart containerd' "$install_script"; then
  fail "install script must not restart containerd in M6"
fi
if grep -q 'tee "$CONTAINERD_CONFIG"\|tee /etc/containerd/config.toml' "$install_script"; then
  fail "install script must not write containerd config in M6"
fi
if grep -nE 'apt-get install.*(cuda-toolkit|cuda-[0-9]|pytorch|torch|ktransformers|ik_llama)' "$install_script"; then
  fail "install script attempts to install CUDA Toolkit or backend packages"
fi
if grep -nE 'docker[[:space:]]+pull|docker[[:space:]]+run' "$install_script"; then
  fail "install script must not pull or run containers"
fi

grep -q 'DockerRootDir' "$verify_script" || fail "verify script must check Docker Root Dir"
grep -q '/data/containerd/root' "$verify_script" || fail "verify script must check containerd root"
grep -q 'tcp://' "$verify_script" || fail "verify script must check no Docker TCP socket exposure"
grep -q -- '--yes-run-cuda-test' "$verify_script" || fail "verify script must accept --yes-run-cuda-test for compatibility"
grep -q 'nvidia/cuda:13.2.1-base-ubuntu24.04' "$verify_script" || fail "verify script must use the proposed explicit CUDA test image tag"
grep -q 'latest' "$verify_script" || fail "verify script must reject latest tags"

if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "$install_script" "$verify_script"; then
  fail "hard-coded secret-like content found"
fi

echo "PASS: NVIDIA Container Toolkit static checks"
