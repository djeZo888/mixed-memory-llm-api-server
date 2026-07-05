#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/sglang/verify-sglang-real-fast-plan.sh [--help]

Read-only verification for the M9A first real SGLang fast-model plan.
USAGE
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

for arg in "$@"; do
  case "$arg" in
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $arg"
      ;;
  esac
done

required_files=(
  configs/models/profiles/qwen3-30b-a3b-instruct-2507.yaml
  configs/models/profiles/qwen3.6-35b-a3b.yaml
  configs/models/profiles/qwen3-30b-a3b-thinking-2507.yaml
  configs/compose/compose.sglang-qwen3-30b.template.yml
  configs/sglang/qwen3-30b.env.example
  scripts/sglang/plan-sglang-real-fast.sh
  docs/sglang-first-real-model.md
  reports/m9a-first-real-fast-model-plan.md
)

for path in "${required_files[@]}"; do
  [[ -f "$path" ]] || fail "$path missing"
  echo "PASS: exists: $path"
done

compose="configs/compose/compose.sglang-qwen3-30b.template.yml"
env_example="configs/sglang/qwen3-30b.env.example"
doc="docs/sglang-first-real-model.md"
report="reports/m9a-first-real-fast-model-plan.md"
primary_profile="configs/models/profiles/qwen3-30b-a3b-instruct-2507.yaml"

scripts/llmctl validate >/tmp/sglang-real-fast-llmctl-validate.out || {
  cat /tmp/sglang-real-fast-llmctl-validate.out >&2
  fail "llmctl validate failed"
}

grep -Fq 'image: lmsysorg/sglang:v0.5.14-cu130' "$compose" || fail "compose template must use pinned lmsysorg/sglang:v0.5.14-cu130"
grep -Fq '127.0.0.1:30001:30000' "$compose" || fail "compose template must bind 127.0.0.1:30001:30000"

bad_port_bindings="$(grep -En '^[[:space:]]*-[[:space:]]*"?((0\.0\.0\.0:)?[0-9]+:[0-9]+)' "$compose" | grep -v '127.0.0.1:30001:30000' || true)"
if [[ -n "$bad_port_bindings" ]]; then
  echo "$bad_port_bindings" >&2
  fail "public or bare host port binding found"
fi

for path in /data/models /data/hf-cache /data/logs /data/models/qwen3-30b-a3b-instruct-2507; do
  grep -Fq "$path" "$compose" "$env_example" "$doc" "$report" "$primary_profile" || fail "missing local /data reference: $path"
done

if grep -RInE 'image:[[:space:]]*.*:latest($|[^[:alnum:]_.-])|SGLANG_IMAGE=.*latest|lmsysorg/sglang:latest' "$compose" "$env_example" "$doc" "$report"; then
  fail "floating latest image tag found"
fi

secret_matches="$(grep -RInE '(HF_TOKEN|OPENAI_API_KEY|GITHUB_TOKEN|password|passwd|PRIVATE KEY|BEGIN OPENSSH|BEGIN RSA|auth\.json|ai-vm\.sudo)' "$compose" "$env_example" "$doc" "$report" scripts/sglang/plan-sglang-real-fast.sh tests/shell/test-sglang-real-fast-static.sh | grep -Ev 'outside git|Do not commit real secrets|grep -RInE|secret scan|intentional|safety|If Hugging Face authentication|No real secret' || true)"
if [[ -n "$secret_matches" ]]; then
  echo "$secret_matches" >&2
  fail "secret-like content found"
fi

if grep -RInE '^[[:space:]]*(sudo -n[[:space:]]+)?docker[[:space:]]+(pull|run|compose[[:space:]]+up)|^[[:space:]]*(huggingface-cli|hf)[[:space:]]+download|snapshot_download' scripts/sglang/plan-sglang-real-fast.sh scripts/sglang/verify-sglang-real-fast-plan.sh tests/shell/test-sglang-real-fast-static.sh | grep -v 'grep -RInE'; then
  fail "plan/verifier/static test contains executable download, image pull, or container start command"
fi

grep -Fq 'PASS for planning only' "$report" || fail "report must include PASS for planning only"
grep -Fq 'STOP for actual download/deployment until human review' "$report" || fail "report must include STOP for actual deployment"

echo "PASS: SGLang real fast plan verification passed"
