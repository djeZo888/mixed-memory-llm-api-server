#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/large-models/verify-ktransformers-minimax-runtime.sh [--help]

Read-only import/help/common_ops verification for the isolated M9E-R1 MiniMax-M3
runtime image. This verifier does not download model weights, does not start a
model backend, does not modify active state, and does not expose an API.

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

image_tag="${MINIMAX_RUNTIME_IMAGE:-local/minimax-m3-ktransformers:0.6.3-post1-r1}"
record_root="${MINIMAX_BUILD_ROOT:-/data/build/ktransformers-minimax-m3}"
help_out="$record_root/sglang-launch-server-help.txt"
verify_record="$record_root/runtime-verify-latest.md"
ldd_out="$record_root/sgl-kernel-common-ops-ldd.txt"

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

echo "=== python ==="
python3 --version

echo "=== libnuma lookup ==="
ldconfig -p | grep -E 'libnuma\.so\.1' || { echo "missing libnuma.so.1"; exit 30; }
find / -name 'libnuma.so*' 2>/dev/null | sort | head -20 || true

echo "=== imports and common_ops ==="
python3 - <<"PY"
import glob
import importlib
import importlib.metadata as metadata
import importlib.util
import os
import pathlib
import sys

for dist in ("kt-kernel", "sglang-kt"):
    print(f"{dist}={metadata.version(dist)}")

for module_name in ("kt_kernel", "sglang", "sglang.launch_server"):
    module = importlib.import_module(module_name)
    print(f"{module_name}=import-ok file={getattr(module, '__file__', 'unknown')}")

import kt_kernel
print(f"kt_kernel_version={getattr(kt_kernel, '__version__', 'unknown')}")
try:
    from kt_kernel import kt_kernel_ext
    cpu_infer = kt_kernel_ext.CPUInfer(1)
    print(f"kt_kernel_cuda_submit={hasattr(cpu_infer, 'submit_with_cuda_stream')}")
except Exception as exc:
    raise SystemExit(f"kt_kernel_ext_probe_failed={type(exc).__name__}: {exc}")

if importlib.util.find_spec("ktransformers") is None:
    print("ktransformers=not-installed; sglang-kt plus kt-kernel wheel path is active")
else:
    ktransformers = importlib.import_module("ktransformers")
    print(f"ktransformers=import-ok file={getattr(ktransformers, '__file__', 'unknown')}")

import torch
print(f"torch_cuda_available={torch.cuda.is_available()}")
for idx in range(torch.cuda.device_count()):
    print(f"torch_gpu_{idx}_compute_capability={torch.cuda.get_device_capability(idx)}")

import sgl_kernel
print(f"sgl_kernel=import-ok file={getattr(sgl_kernel, '__file__', 'unknown')}")

common_ops = []
for p in [p for p in sys.path if p]:
    common_ops.extend(glob.glob(os.path.join(p, "sgl_kernel", "**", "common_ops*.so"), recursive=True))
common_ops = sorted(set(common_ops))
if not common_ops:
    raise SystemExit("common_ops_shared_objects=missing")
for path in common_ops:
    print(f"common_ops_file={path}")
pathlib.Path("/tmp/sgl-kernel-common-ops-files.txt").write_text("\n".join(common_ops) + "\n")
if any("/sm120/" in path for path in common_ops):
    support = "native-sm120-common_ops-present"
elif any("/sm100/" in path for path in common_ops):
    support = "sm100-common_ops-present; SM120 import succeeded through package loader fallback/compatibility path"
else:
    support = "no-sm120-or-sm100-common_ops; unresolved fallback status"
print(f"sm120_common_ops_status={support}")
pathlib.Path("/tmp/sgl-kernel-sm120-status.txt").write_text(support + "\n")
PY

echo "=== launch_server help flags ==="
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

echo "=== gpu compute capability ==="
nvidia-smi --query-gpu=index,name,compute_cap,memory.total,driver_version --format=csv,noheader

echo "=== common_ops ldd ==="
torch_ld_path="$(python3 - <<'PY'
import glob
import os
import torch
paths = [os.path.join(os.path.dirname(torch.__file__), "lib")]
paths.extend(glob.glob("/opt/minimax-m3-runtime/lib/python*/site-packages/nvidia/*/lib"))
print(":".join(path for path in paths if os.path.isdir(path)))
PY
)"
export LD_LIBRARY_PATH="${torch_ld_path}:${LD_LIBRARY_PATH:-}"
while IFS= read -r common_ops_so; do
  [[ -n "$common_ops_so" ]] || continue
  echo "common_ops_ldd_file=$common_ops_so"
  ldd "$common_ops_so"
done </tmp/sgl-kernel-common-ops-files.txt | tee /tmp/sgl-kernel-common-ops-ldd.txt
if grep -F 'libnuma.so.1 => not found' /tmp/sgl-kernel-common-ops-ldd.txt >/dev/null; then
  echo "libnuma_missing_after_r1"
  exit 31
fi

echo "=== launch_server help ==="
cat /tmp/sglang-launch-server-help.txt
CONTAINER
)"

tmp_help="$(mktemp)"
tmp_verify="$(mktemp)"
trap 'rm -f "$tmp_help" "$tmp_verify"' EXIT

if ! sudo -n docker run --rm --gpus all --entrypoint bash "$image_tag" -lc "$container_script" >"$tmp_help"; then
  cat "$tmp_help" >&2 || true
  fail "runtime import/common_ops/help verification failed"
fi

cp "$tmp_help" "$help_out"
awk '/^=== common_ops ldd ===/{capture=1; next} /^=== launch_server help ===/{capture=0} capture{print}' "$tmp_help" >"$ldd_out"

{
  echo "# M9E-R1 MiniMax-M3 Runtime Verification Record"
  echo
  echo "- Timestamp: \`$(date -u +%Y-%m-%dT%H:%M:%SZ)\`"
  echo "- Image: \`$image_tag\`"
  echo "- Result: PASS for libnuma, sgl_kernel/common_ops import, runtime imports, and required launch flags."
  echo "- Common ops ldd record: \`$ldd_out\`"
  sm120_status="$(grep -m1 '^sm120_common_ops_status=' "$tmp_help" | sed 's/^sm120_common_ops_status=//')"
  if [[ -n "$sm120_status" ]]; then
    echo "- SM120/common_ops status: \`$sm120_status\`"
  fi
  echo
  echo "## Host GPU Summary"
  printf '%s\n' "$host_gpu_summary"
  echo
  echo "## Runtime Probe Output"
  sed -n '1,260p' "$tmp_help"
} >"$tmp_verify"

mv "$tmp_verify" "$verify_record"
chmod 0644 "$verify_record"

scripts/common/root-disk-guard.sh --report /tmp/root-disk-guard-after-minimax-runtime-verify.md
M4_REPORT_PATH=/tmp/minimax-runtime-verify-docker-storage-after.md scripts/docker/verify-docker-storage.sh

echo "PASS: runtime imports, libnuma, sgl_kernel/common_ops, and required SGLang-KT flags verified"
echo "PASS: launch_server help saved: $help_out"
echo "PASS: common_ops ldd saved: $ldd_out"
echo "PASS: verification record saved: $verify_record"
