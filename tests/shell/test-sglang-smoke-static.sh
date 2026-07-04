#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

scripts=(
  scripts/sglang/plan-sglang-smoke.sh
  scripts/sglang/verify-sglang-smoke-plan.sh
  scripts/api/smoke-openai-chat.sh
)

for script in "${scripts[@]}"; do
  [[ -f "$script" ]] || fail "$script missing"
  [[ -x "$script" ]] || fail "$script is not executable"
  grep -q 'set -euo pipefail' "$script" || fail "$script missing strict shell mode"
  "$script" --help >/tmp/sglang-smoke-help.out || fail "$script --help failed"
done

[[ -f configs/compose/compose.sglang-smoke.template.yml ]] || fail "compose smoke template missing"
[[ -f configs/sglang/smoke.env.example ]] || fail "smoke env example missing"
[[ -f docs/sglang-smoke-deployment.md ]] || fail "deployment doc missing"
[[ -f reports/m8a-sglang-smoke-plan.md ]] || fail "M8A report missing"

if scripts/sglang/plan-sglang-smoke.sh >/tmp/sglang-plan-no-dry-run.out 2>/tmp/sglang-plan-no-dry-run.err; then
  fail "plan script succeeded without --dry-run"
fi
grep -q 'M8A supports dry-run planning only' /tmp/sglang-plan-no-dry-run.err || fail "plan refusal did not mention dry-run planning"

SGLANG_SMOKE_PLAN_SKIP_HOST_CHECKS=1 scripts/sglang/plan-sglang-smoke.sh --dry-run >/tmp/sglang-plan-dry-run.out || fail "plan dry-run failed"
grep -q 'model_download_performed: false' /tmp/sglang-plan-dry-run.out || fail "plan dry-run did not confirm no download"
grep -q 'image_pull_performed: false' /tmp/sglang-plan-dry-run.out || fail "plan dry-run did not confirm no image pull"
grep -q 'container_started: false' /tmp/sglang-plan-dry-run.out || fail "plan dry-run did not confirm no container start"

scripts/api/smoke-openai-chat.sh --dry-run >/tmp/sglang-api-dry-run.out || fail "API dry-run failed"
grep -q 'DRY-RUN: no API request sent' /tmp/sglang-api-dry-run.out || fail "API dry-run did not stay dry"
grep -q 'http://127.0.0.1:30000/v1/chat/completions' /tmp/sglang-api-dry-run.out || fail "API dry-run target mismatch"

scripts/sglang/verify-sglang-smoke-plan.sh >/tmp/sglang-verify-plan.out || fail "plan verifier failed"
grep -q 'PASS: SGLang smoke plan verification passed' /tmp/sglang-verify-plan.out || fail "plan verifier did not report PASS"

compose="configs/compose/compose.sglang-smoke.template.yml"
grep -Fq '127.0.0.1:30000:30000' "$compose" || fail "compose template must bind localhost"
if grep -En '"30000:30000"|0\.0\.0\.0:30000:30000' "$compose"; then
  fail "compose template has public external port binding"
fi
for path in /data/models /data/hf-cache /data/logs; do
  grep -Fq "$path" "$compose" || fail "compose template missing $path"
done
grep -Fq '/data/models/qwen3-0.6b-smoke' "$compose" || fail "compose template must use local model path"
grep -Fq 'profiles: ["sglang-smoke"]' "$compose" || fail "compose template missing profile"
grep -Fq 'image: ${SGLANG_IMAGE_TAG}' "$compose" || fail "compose image must remain env-selected"
if grep -En 'lmsysorg/sglang:(latest|latest-runtime)$|SGLANG_IMAGE_TAG=.*latest' "$compose" configs/sglang/smoke.env.example; then
  fail "latest SGLang image tag found"
fi

grep -Fq 'lmsysorg/sglang:v0.5.14-cu130-runtime' reports/m8a-sglang-smoke-plan.md || fail "report must document proposed pinned image"
secret_matches="$(grep -RInE '(HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,}|BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY)' configs/compose/compose.sglang-smoke.template.yml configs/sglang/smoke.env.example scripts/sglang scripts/api docs/sglang-smoke-deployment.md reports/m8a-sglang-smoke-plan.md | grep -v 'grep -RInE' || true)"
if [[ -n "$secret_matches" ]]; then
  echo "$secret_matches" >&2
  fail "secret-like content found"
fi

if grep -RInE 'docker[[:space:]]+(pull|run|compose[[:space:]]+up)' tests/shell/test-sglang-smoke-static.sh; then
  fail "static test must not execute forbidden container commands"
fi

echo "PASS: SGLang smoke static checks"
