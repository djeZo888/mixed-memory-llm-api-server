#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

LLMCTL="scripts/llmctl"

[[ -f "$LLMCTL" ]] || fail "$LLMCTL missing"
[[ -x "$LLMCTL" ]] || fail "$LLMCTL is not executable"
"$LLMCTL" --help >/dev/null || fail "llmctl --help failed"

grep -q 'scripts/common/require-data-mounted.sh' "$LLMCTL" || fail "llmctl must reference require-data-mounted.sh"
grep -q 'scripts/common/root-disk-guard.sh' "$LLMCTL" || fail "llmctl must reference root-disk-guard.sh"
grep -q 'scripts/docker/verify-docker-storage.sh' "$LLMCTL" || fail "llmctl must reference verify-docker-storage.sh"
grep -q 'scripts/nvidia/verify-gpu-containers.sh' "$LLMCTL" || fail "llmctl must reference verify-gpu-containers.sh"

for path in /data/models /data/hf-cache /data/logs /data/build /data/services/llm-manager/state; do
  grep -q "$path" "$LLMCTL" docs/model-runtime-manager.md configs/compose/*.yml || fail "missing manager path reference: $path"
done

required_profiles=(
  configs/models/catalog.yaml
  configs/models/profiles/qwen3-0.6b-smoke.yaml
  configs/models/profiles/qwen3-30b-a3b-instruct-2507.yaml
  configs/models/profiles/qwen3-235b-a22b-instruct-2507.yaml
  configs/models/profiles/minimax-m3.yaml
  configs/models/profiles/glm-5.2.yaml
  configs/runtimes/sglang.yaml
  configs/runtimes/ktransformers.yaml
  configs/runtimes/ik-llama.yaml
  configs/runtimes/vllm.yaml
  configs/compose/compose.sglang.template.yml
  configs/compose/compose.ktransformers.template.yml
)

for file in "${required_profiles[@]}"; do
  [[ -f "$file" ]] || fail "required profile/template missing: $file"
done

if "$LLMCTL" activate qwen3-0.6b-smoke --runtime sglang >/tmp/llmctl-activate.out 2>/tmp/llmctl-activate.err; then
  fail "activate without --dry-run succeeded"
fi
grep -q -- '--dry-run' /tmp/llmctl-activate.err || fail "activate refusal did not mention --dry-run"

if "$LLMCTL" deactivate >/tmp/llmctl-deactivate.out 2>/tmp/llmctl-deactivate.err; then
  fail "deactivate without --dry-run succeeded"
fi
grep -q -- '--dry-run' /tmp/llmctl-deactivate.err || fail "deactivate refusal did not mention --dry-run"

if "$LLMCTL" download qwen3-0.6b-smoke >/tmp/llmctl-download.out 2>/tmp/llmctl-download.err; then
  fail "download command succeeded in M7B"
fi
grep -q 'reserved for later milestones' /tmp/llmctl-download.err || fail "download refusal did not mention later milestones"

if grep -RInE 'image:[[:space:]]*[^$].*:latest|0\.0\.0\.0|HF_TOKEN=|OPENAI_API_KEY=|GITHUB_TOKEN=' configs/compose; then
  fail "compose templates contain unsafe bind/image/token patterns"
fi

if grep -RInE '(BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY|HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,})' "$LLMCTL" configs docs/model-runtime-manager.md; then
  fail "hard-coded secret-like content found"
fi

LLMCTL_SKIP_HOST_CHECKS=1 "$LLMCTL" validate >/dev/null || fail "llmctl validate failed"
LLMCTL_SKIP_HOST_CHECKS=1 "$LLMCTL" plan-download qwen3-0.6b-smoke >/tmp/llmctl-plan-download.out || fail "plan-download smoke failed"
grep -q 'download_performed: false' /tmp/llmctl-plan-download.out || fail "plan-download did not confirm no download"

echo "PASS: llmctl static checks"
