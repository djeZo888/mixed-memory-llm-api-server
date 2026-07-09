#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

scripts=(
  scripts/large-models/plan-qwen35-mixed-memory.sh
  scripts/large-models/verify-qwen35-mixed-memory-plan.sh
)

for script in "${scripts[@]}"; do
  [[ -f "$script" ]] || fail "$script missing"
  [[ -x "$script" ]] || fail "$script is not executable"
  grep -q 'set -euo pipefail' "$script" || fail "$script missing strict shell mode"
  "$script" --help >/tmp/qwen35-mixed-memory-help.out || fail "$script --help failed"
  "$script" --help | grep -q -- '--dry-run' || fail "$script help must mention --dry-run"
done

if scripts/large-models/plan-qwen35-mixed-memory.sh >/tmp/qwen35-no-dry-run.out 2>/tmp/qwen35-no-dry-run.err; then
  fail "plan script succeeded without --dry-run"
fi
grep -q 'M9F supports planning only' /tmp/qwen35-no-dry-run.err || fail "plan refusal did not mention M9F planning only"

M9F_PLAN_SKIP_HOST_CHECKS=1 scripts/large-models/plan-qwen35-mixed-memory.sh --dry-run >/tmp/qwen35-plan-dry-run.out || fail "plan dry-run failed"
grep -q 'model_download_performed: false' /tmp/qwen35-plan-dry-run.out || fail "dry-run did not confirm no model download"
grep -q 'docker_image_pull_performed: false' /tmp/qwen35-plan-dry-run.out || fail "dry-run did not confirm no image pull"
grep -q 'runtime_install_performed: false' /tmp/qwen35-plan-dry-run.out || fail "dry-run did not confirm no install"
grep -q 'runtime_build_performed: false' /tmp/qwen35-plan-dry-run.out || fail "dry-run did not confirm no build"
grep -q 'model_backend_container_started: false' /tmp/qwen35-plan-dry-run.out || fail "dry-run did not confirm no backend container start"
grep -q 'current_active_model_stopped_or_restarted: false' /tmp/qwen35-plan-dry-run.out || fail "dry-run did not confirm 30B preservation"
grep -q 'public_bind_performed: false' /tmp/qwen35-plan-dry-run.out || fail "dry-run did not confirm no public bind"
grep -q 'next_candidate: Qwen/Qwen3.5-397B-A17B-FP8' /tmp/qwen35-plan-dry-run.out || fail "dry-run did not print Qwen3.5 candidate"

M9F_PLAN_SKIP_HOST_CHECKS=1 scripts/large-models/verify-qwen35-mixed-memory-plan.sh --dry-run >/tmp/qwen35-verify.out || fail "plan verifier dry-run failed"
grep -q 'PASS: Qwen3.5 mixed-memory plan verification passed' /tmp/qwen35-verify.out || fail "verifier did not report PASS"

for file in \
  docs/offline-resilience-goals.md \
  docs/mixed-memory-large-model-strategy.md \
  docs/memory-rag-architecture.md \
  docs/model-roles.md \
  docs/current-state.md \
  docs/model-matrix.md \
  ROADMAP.md \
  reports/m9f-offline-resilience-mixed-memory-plan.md; do
  [[ -f "$file" ]] || fail "$file missing"
done

if grep -RInE '^[[:space:]]*(sudo -n[[:space:]]+)?docker[[:space:]]+(pull|run|compose[[:space:]]+up)|^[[:space:]]*(huggingface-cli|hf)[[:space:]]+download|snapshot_download|pip[[:space:]]+install|apt(-get)?[[:space:]]+install' scripts/large-models/plan-qwen35-mixed-memory.sh scripts/large-models/verify-qwen35-mixed-memory-plan.sh tests/shell/test-qwen35-mixed-memory-plan-static.sh | grep -v 'grep -RInE'; then
  fail "M9F scripts/tests must not execute downloads, image pulls, container starts, or installs"
fi

if grep -RInE '(^|[[:space:]])0\.0\.0\.0(:[0-9]+)?|[0-9]+:30000:30000' scripts/large-models/plan-qwen35-mixed-memory.sh scripts/large-models/verify-qwen35-mixed-memory-plan.sh tests/shell/test-qwen35-mixed-memory-plan-static.sh | grep -v 'grep -RInE'; then
  fail "M9F scripts/tests contain public host bind pattern"
fi

secret_matches="$(grep -RInE '(HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,}|BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY)' scripts/large-models/plan-qwen35-mixed-memory.sh scripts/large-models/verify-qwen35-mixed-memory-plan.sh tests/shell/test-qwen35-mixed-memory-plan-static.sh docs/offline-resilience-goals.md docs/mixed-memory-large-model-strategy.md docs/memory-rag-architecture.md docs/model-roles.md reports/m9f-offline-resilience-mixed-memory-plan.md | grep -v 'grep -RInE' || true)"
if [[ -n "$secret_matches" ]]; then
  echo "$secret_matches" >&2
  fail "secret-like content found"
fi

echo "PASS: Qwen3.5 mixed-memory plan static checks"
