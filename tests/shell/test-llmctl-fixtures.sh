#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/configs/models/profiles" "$tmp/configs/runtimes" "$tmp/data" "$tmp/state"

cat >"$tmp/configs/models/catalog.yaml" <<'YAML'
version: 1
policy: one_active_model_backend
model_profiles:
  - fixture-smoke
runtime_profiles:
  - fixture-runtime
YAML

cat >"$tmp/configs/models/profiles/fixture-smoke.yaml" <<'YAML'
name: fixture-smoke
provider: Fixture
hf_repo: fixture/smoke
family: fixture
role: smoke
model_type: dense
total_params: 1B
active_params: 1B
context_window: 4096
license: test
expected_precision: none
expected_storage_gb: 1
expected_min_vram_gb: 1
expected_min_system_ram_gb: 1
recommended_runtimes:
  - fixture-runtime
preferred_runtime: fixture-runtime
allowed_first_download: true
notes: Fixture model.
source_urls:
  - https://example.invalid/model
YAML

cat >"$tmp/configs/runtimes/fixture-runtime.yaml" <<'YAML'
name: fixture-runtime
kind: docker
status: planned
openai_compatible: true
localhost_bind_default: true
gpu_required: true
heterogeneous_ram_vram: false
config_template: none
healthcheck_path: /health
default_port: 18000
risks:
  - fixture risk
source_urls:
  - https://example.invalid/runtime
YAML

env_prefix=(
  LLMCTL_CONFIG_ROOT="$tmp/configs"
  LLMCTL_DATA_ROOT="$tmp/data"
  LLMCTL_STATE_DIR="$tmp/state"
  LLMCTL_SKIP_HOST_CHECKS=1
)

env "${env_prefix[@]}" scripts/llmctl validate >/tmp/llmctl-fixture-validate.out || fail "fixture validate failed"
grep -q 'PASS: validated' /tmp/llmctl-fixture-validate.out || fail "validate did not report PASS"

env "${env_prefix[@]}" scripts/llmctl list-models | grep -q 'fixture-smoke' || fail "list-models missing fixture"
env "${env_prefix[@]}" scripts/llmctl list-runtimes | grep -q 'fixture-runtime' || fail "list-runtimes missing fixture"
env "${env_prefix[@]}" scripts/llmctl show-model fixture-smoke | grep -q 'hf_repo: fixture/smoke' || fail "show-model failed"
env "${env_prefix[@]}" scripts/llmctl show-runtime fixture-runtime | grep -q 'default_port: 18000' || fail "show-runtime failed"

env "${env_prefix[@]}" scripts/llmctl plan-activate fixture-smoke --runtime fixture-runtime >/tmp/llmctl-fixture-plan-activate.out || fail "plan-activate failed"
grep -q 'writes_planned: none for plan-activate' /tmp/llmctl-fixture-plan-activate.out || fail "plan-activate did not stay dry"

env "${env_prefix[@]}" scripts/llmctl activate fixture-smoke --runtime fixture-runtime --dry-run >/tmp/llmctl-fixture-activate.out || fail "activate dry-run failed"
grep -q 'DRY-RUN' /tmp/llmctl-fixture-activate.out || fail "activate did not report dry-run"

if env "${env_prefix[@]}" scripts/llmctl activate fixture-smoke --runtime fixture-runtime >/tmp/llmctl-fixture-bad-activate.out 2>/tmp/llmctl-fixture-bad-activate.err; then
  fail "activate without --dry-run succeeded"
fi
grep -q -- '--dry-run' /tmp/llmctl-fixture-bad-activate.err || fail "bad activate did not mention --dry-run"

env "${env_prefix[@]}" scripts/llmctl plan-download fixture-smoke >/tmp/llmctl-fixture-plan-download.out || fail "plan-download failed"
grep -q 'download_performed: false' /tmp/llmctl-fixture-plan-download.out || fail "plan-download performed work"

cat >"$tmp/configs/models/profiles/bad-model.yaml" <<'YAML'
name: bad-model
provider: Fixture
hf_repo: fixture/bad
family: fixture
role: invalid
model_type: dense
total_params: 1B
active_params: 1B
context_window: 4096
license: test
expected_precision: none
expected_storage_gb: 1
expected_min_vram_gb: 1
expected_min_system_ram_gb: 1
recommended_runtimes:
  - fixture-runtime
preferred_runtime: fixture-runtime
allowed_first_download: true
notes: Invalid fixture model.
source_urls:
  - https://example.invalid/model
YAML

if env "${env_prefix[@]}" scripts/llmctl validate >/tmp/llmctl-fixture-invalid-model.out 2>/tmp/llmctl-fixture-invalid-model.err; then
  fail "invalid model profile passed validation"
fi
grep -q 'invalid role' /tmp/llmctl-fixture-invalid-model.err || fail "invalid model failure was not specific"
rm -f "$tmp/configs/models/profiles/bad-model.yaml"

cat >"$tmp/configs/runtimes/bad-runtime.yaml" <<'YAML'
name: bad-runtime
kind: docker
status: broken
openai_compatible: true
localhost_bind_default: true
gpu_required: true
heterogeneous_ram_vram: false
config_template: none
healthcheck_path: /health
default_port: 18001
risks:
  - fixture risk
source_urls:
  - https://example.invalid/runtime
YAML

if env "${env_prefix[@]}" scripts/llmctl validate >/tmp/llmctl-fixture-invalid-runtime.out 2>/tmp/llmctl-fixture-invalid-runtime.err; then
  fail "invalid runtime profile passed validation"
fi
grep -q 'invalid status' /tmp/llmctl-fixture-invalid-runtime.err || fail "invalid runtime failure was not specific"

if find "$tmp/data" -mindepth 1 -print -quit | grep -q .; then
  fail "fixture commands wrote under fixture data root"
fi

echo "PASS: llmctl fixture checks"
