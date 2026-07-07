#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/large-models/verify-ktransformers-minimax-runtime.sh [--help]

Read-only import/help verification for the isolated M9E MiniMax-M3 runtime image.
This verifier does not download model weights, does not start a model backend,
does not modify active state, and does not expose an API.

Environment override:
  MINIMAX_RUNTIME_IMAGE   image tag to verify
USAGE
}

fail() {
  echo "STOP: $*" >&2
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

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

cd "$(repo_root)"

image_tag="${MINIMAX_RUNTIME_IMAGE:-local/minimax-m3-ktransformers:0.6.3-post1}"
record_root="${MINIMAX_BUILD_ROOT:-/data/build/ktransformers-minimax-m3}"
help_out="$record_root/sglang-launch-server-help.txt"
verify_record="$record_root/runtime-verify-latest.md"

[[ "$(hostname)" == "llmserver" ]] || fail "hostname is $(hostname), expected llmserver"
[[ "$(pwd)" == "/data/services/mixed-memory-llm-api-server" ]] || fail "unexpected repo path: $(pwd)"
sudo -n true || fail "sudo -n is not available"
sudo -n docker image inspect "$image_tag" >/dev/null 2>&1 || fail "runtime image not found: $image_tag"

scripts/common/require-data-mounted.sh
scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-before-minimax-runtime-verify.md
M4_REPORT_PATH=/tmp/minimax-runtime-verify-docker-storage.md scripts/docker/verify-docker-storage.sh

mkdir -p "$record_root"

host_gpu_summary="$(nvidia-smi --query-gpu=index,name,compute_cap,memory.total,driver_version --format=csv,noheader)"
printf '%s\n' "$host_gpu_summary"

if ! grep -q 'NVIDIA RTX PRO 6000 Blackwell Workstation Edition' <<<"$host_gpu_summary"; then
  fail "expected RTX PRO 6000 Blackwell GPUs not detected"
fi

if grep -q ', 12\.0,' <<<"$host_gpu_summary"; then
  cat <<'NOTE'
WARN: detected compute capability 12.0 / SM120 workstation Blackwell.
WARN: current MiniMax-M3 KTransformers tutorial explicitly lists SM90 Hopper and says upstream SGLang targets SM100 datacenter Blackwell so far.
WARN: kt-kernel PyPI metadata lists wheel CUDA examples through SM90 and does not explicitly list SM120.
NOTE
fi

container_script="$(cat <<'CONTAINER'
set -euo pipefail
python3 --version
python3 - <<"PY"
import importlib.metadata as metadata
for dist in ("kt-kernel", "sglang-kt"):
    print(f"{dist}={metadata.version(dist)}")
import kt_kernel
print(f"kt_kernel_module={getattr(kt_kernel, '__file__', 'unknown')}")
print(f"kt_kernel_version={getattr(kt_kernel, '__version__', 'unknown')}")
try:
    from kt_kernel import kt_kernel_ext
    cpu_infer = kt_kernel_ext.CPUInfer(1)
    print(f"kt_kernel_cuda_submit={hasattr(cpu_infer, 'submit_with_cuda_stream')}")
except Exception as exc:
    raise SystemExit(f"kt_kernel_ext_probe_failed={type(exc).__name__}: {exc}")
import sglang
print(f"sglang_module={getattr(sglang, '__file__', 'unknown')}")
import sglang.launch_server
print("sglang.launch_server=import-ok")
PY
python3 -m sglang.launch_server --help >/tmp/sglang-launch-server-help.txt 2>&1 || { cat /tmp/sglang-launch-server-help.txt; exit 20; }
for flag in --kt-weight-path --kt-method --kt-cpuinfer --kt-threadpool-count --kt-num-gpu-experts --quantization; do
  grep -F -- "$flag" /tmp/sglang-launch-server-help.txt >/dev/null || { echo "missing required flag: $flag"; exit 21; }
done
if grep -F -- "--tp-size" /tmp/sglang-launch-server-help.txt >/dev/null; then
  echo "tensor_parallel_flag=--tp-size"
elif grep -F -- "--tensor-parallel-size" /tmp/sglang-launch-server-help.txt >/dev/null; then
  echo "tensor_parallel_flag=--tensor-parallel-size"
else
  echo "missing tensor parallel flag: --tp-size or --tensor-parallel-size"
  exit 22
fi
for optional_flag in --kt-gpu-prefill-token-threshold --moe-runner-backend --chunked-prefill-size --cuda-graph-max-bs --tool-call-parser --reasoning-parser --served-model-name --mem-fraction-static --context-length; do
  if grep -F -- "$optional_flag" /tmp/sglang-launch-server-help.txt >/dev/null; then
    echo "optional_flag_present=$optional_flag"
  else
    echo "optional_flag_missing=$optional_flag"
  fi
done
nvidia-smi --query-gpu=index,name,compute_cap,memory.total,driver_version --format=csv,noheader
cat /tmp/sglang-launch-server-help.txt
CONTAINER
)"

tmp_help="$(mktemp)"
tmp_verify="$(mktemp)"
trap 'rm -f "$tmp_help" "$tmp_verify"' EXIT

if ! sudo -n docker run --rm --gpus all --entrypoint bash "$image_tag" -lc "$container_script" >"$tmp_help"; then
  cat "$tmp_help" >&2 || true
  fail "runtime import/help verification failed"
fi

cp "$tmp_help" "$help_out"

{
  echo "# M9E MiniMax-M3 Runtime Verification Record"
  echo
  echo "- Timestamp: \`$(date -u +%Y-%m-%dT%H:%M:%SZ)\`"
  echo "- Image: \`$image_tag\`"
  echo "- Result: PASS for import and required launch flags."
  echo
  echo "## Host GPU Summary"
  printf '%s\n' "$host_gpu_summary"
  echo
  echo "## Runtime Probe Output"
  sed -n '1,220p' "$tmp_help"
} >"$tmp_verify"

mv "$tmp_verify" "$verify_record"
chmod 0644 "$verify_record"

scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-after-minimax-runtime-verify.md
M4_REPORT_PATH=/tmp/minimax-runtime-verify-docker-storage-after.md scripts/docker/verify-docker-storage.sh

echo "PASS: runtime imports and required SGLang-KT flags verified"
echo "PASS: launch_server help saved: $help_out"
echo "PASS: verification record saved: $verify_record"
