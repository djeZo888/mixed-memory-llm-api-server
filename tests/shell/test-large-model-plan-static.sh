#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

scripts=(
  scripts/large-models/plan-large-model.sh
  scripts/large-models/verify-large-model-plan.sh
)

for script in "${scripts[@]}"; do
  [[ -f "$script" ]] || fail "$script missing"
  [[ -x "$script" ]] || fail "$script is not executable"
  grep -q 'set -euo pipefail' "$script" || fail "$script missing strict shell mode"
  "$script" --help >/tmp/large-model-help.out || fail "$script --help failed"
  "$script" --help | grep -q -- '--dry-run' || fail "$script help must mention --dry-run"
done

if scripts/large-models/plan-large-model.sh >/tmp/large-model-no-dry-run.out 2>/tmp/large-model-no-dry-run.err; then
  fail "plan script succeeded without --dry-run"
fi
grep -q 'M9D supports planning only' /tmp/large-model-no-dry-run.err || fail "plan refusal did not mention M9D planning only"

LARGE_MODEL_PLAN_SKIP_HOST_CHECKS=1 scripts/large-models/plan-large-model.sh --dry-run >/tmp/large-model-plan-dry-run.out || fail "plan dry-run failed"
grep -q 'large_model_download_performed: false' /tmp/large-model-plan-dry-run.out || fail "dry-run did not confirm no large model download"
grep -q 'docker_image_pull_performed: false' /tmp/large-model-plan-dry-run.out || fail "dry-run did not confirm no image pull"
grep -q 'runtime_install_performed: false' /tmp/large-model-plan-dry-run.out || fail "dry-run did not confirm no install"
grep -q 'model_backend_container_started: false' /tmp/large-model-plan-dry-run.out || fail "dry-run did not confirm no backend container start"
grep -q 'public_bind_performed: false' /tmp/large-model-plan-dry-run.out || fail "dry-run did not confirm no public bind"

grep -q 'recommended_first_large_model: MiniMaxAI/MiniMax-M3-MXFP8' /tmp/large-model-plan-dry-run.out || fail "dry-run did not print recommended model"
grep -q 'fallback_model: Qwen/Qwen3-235B-A22B-Instruct-2507-FP8' /tmp/large-model-plan-dry-run.out || fail "dry-run did not print fallback model"

LARGE_MODEL_PLAN_SKIP_HOST_CHECKS=1 scripts/large-models/verify-large-model-plan.sh --dry-run >/tmp/large-model-verify.out || fail "plan verifier dry-run failed"
grep -q 'PASS: large-model plan verification passed' /tmp/large-model-verify.out || fail "verifier did not report PASS"

for file in \
  reports/m9d-large-model-feasibility-plan.md \
  docs/large-model-feasibility.md \
  docs/model-matrix.md \
  docs/current-state.md \
  ROADMAP.md; do
  [[ -f "$file" ]] || fail "$file missing"
done

if grep -RInE '^[[:space:]]*(sudo -n[[:space:]]+)?docker[[:space:]]+(pull|run|compose[[:space:]]+up)|^[[:space:]]*(huggingface-cli|hf)[[:space:]]+download|snapshot_download|pip[[:space:]]+install|apt(-get)?[[:space:]]+install' scripts/large-models tests/shell/test-large-model-plan-static.sh | grep -v 'grep -RInE'; then
  fail "large-model scripts/tests must not execute downloads, image pulls, container starts, or installs"
fi

if grep -RInE '(^|[[:space:]])0\.0\.0\.0(:[0-9]+)?|[0-9]+:30000:30000' scripts/large-models; then
  fail "large-model scripts contain public bind pattern"
fi

secret_matches="$(grep -RInE '(HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,}|BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY)' scripts/large-models tests/shell/test-large-model-plan-static.sh docs/large-model-feasibility.md reports/m9d-large-model-feasibility-plan.md | grep -v 'grep -RInE' || true)"
if [[ -n "$secret_matches" ]]; then
  echo "$secret_matches" >&2
  fail "secret-like content found"
fi

echo "PASS: large-model plan static checks"
