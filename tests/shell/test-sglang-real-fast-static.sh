#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

scripts=(
  scripts/sglang/plan-sglang-real-fast.sh
  scripts/sglang/verify-sglang-real-fast-plan.sh
)

for script in "${scripts[@]}"; do
  [[ -f "$script" ]] || fail "$script missing"
  [[ -x "$script" ]] || fail "$script is not executable"
  grep -q 'set -euo pipefail' "$script" || fail "$script missing strict shell mode"
  "$script" --help >/tmp/sglang-real-fast-help.out || fail "$script --help failed"
done

[[ -f configs/compose/compose.sglang-qwen3-30b.template.yml ]] || fail "real fast compose template missing"
[[ -f configs/sglang/qwen3-30b.env.example ]] || fail "real fast env example missing"
[[ -f docs/sglang-first-real-model.md ]] || fail "first real model doc missing"
[[ -f reports/m9a-first-real-fast-model-plan.md ]] || fail "M9A report missing"

if scripts/sglang/plan-sglang-real-fast.sh >/tmp/sglang-real-fast-no-dry-run.out 2>/tmp/sglang-real-fast-no-dry-run.err; then
  fail "plan script succeeded without --dry-run"
fi
grep -q 'M9A supports planning only' /tmp/sglang-real-fast-no-dry-run.err || fail "plan refusal did not mention M9A planning only"

SGLANG_REAL_FAST_PLAN_SKIP_HOST_CHECKS=1 scripts/sglang/plan-sglang-real-fast.sh --dry-run >/tmp/sglang-real-fast-dry-run.out || fail "plan dry-run failed"
grep -q 'smoke_stop_performed: false' /tmp/sglang-real-fast-dry-run.out || fail "plan dry-run did not confirm no smoke stop"
grep -q 'model_download_performed: false' /tmp/sglang-real-fast-dry-run.out || fail "plan dry-run did not confirm no download"
grep -q 'image_pull_performed: false' /tmp/sglang-real-fast-dry-run.out || fail "plan dry-run did not confirm no image pull"
grep -q 'container_started: false' /tmp/sglang-real-fast-dry-run.out || fail "plan dry-run did not confirm no container start"
grep -q 'api_exposed: false' /tmp/sglang-real-fast-dry-run.out || fail "plan dry-run did not confirm no API exposure"

scripts/sglang/verify-sglang-real-fast-plan.sh >/tmp/sglang-real-fast-verify.out || fail "plan verifier failed"
grep -q 'PASS: SGLang real fast plan verification passed' /tmp/sglang-real-fast-verify.out || fail "plan verifier did not report PASS"

compose="configs/compose/compose.sglang-qwen3-30b.template.yml"
grep -Fq '127.0.0.1:30001:30000' "$compose" || fail "compose template must bind localhost on 30001"
bad_port_bindings="$(grep -En '^[[:space:]]*-[[:space:]]*"?((0\.0\.0\.0:)?[0-9]+:[0-9]+)' "$compose" | grep -v '127.0.0.1:30001:30000' || true)"
if [[ -n "$bad_port_bindings" ]]; then
  echo "$bad_port_bindings" >&2
  fail "compose template has public or bare host port binding"
fi
for path in /data/models /data/hf-cache /data/logs /data/models/qwen3-30b-a3b-instruct-2507; do
  grep -Fq "$path" "$compose" || fail "compose template missing $path"
done

grep -Fq 'image: lmsysorg/sglang:v0.5.14-cu130' "$compose" || fail "compose image must be pinned"
if grep -RInE 'image:[[:space:]]*.*:latest($|[^[:alnum:]_.-])|SGLANG_IMAGE=.*latest|lmsysorg/sglang:latest' "$compose" configs/sglang/qwen3-30b.env.example docs/sglang-first-real-model.md reports/m9a-first-real-fast-model-plan.md; then
  fail "latest SGLang image tag found"
fi

secret_matches="$(grep -RInE '(HF_TOKEN=[A-Za-z0-9_./+:-]{8,}|OPENAI_API_KEY=[A-Za-z0-9_./+:-]{8,}|GITHUB_TOKEN=[A-Za-z0-9_./+:-]{8,}|BEGIN OPENSSH|BEGIN RSA|PRIVATE KEY)' "$compose" configs/sglang/qwen3-30b.env.example scripts/sglang docs/sglang-first-real-model.md reports/m9a-first-real-fast-model-plan.md | grep -v 'grep -RInE' || true)"
if [[ -n "$secret_matches" ]]; then
  echo "$secret_matches" >&2
  fail "secret-like content found"
fi

if grep -RInE '^[[:space:]]*(sudo -n[[:space:]]+)?docker[[:space:]]+(pull|run|compose[[:space:]]+up)|^[[:space:]]*(huggingface-cli|hf)[[:space:]]+download|snapshot_download' scripts/sglang/plan-sglang-real-fast.sh scripts/sglang/verify-sglang-real-fast-plan.sh tests/shell/test-sglang-real-fast-static.sh | grep -v 'grep -RInE'; then
  fail "static M9A tests must not execute download, image pull, or container start commands"
fi

echo "PASS: SGLang real fast static checks"
