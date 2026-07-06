#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/bench/run-m9c-benchmarks.sh [--help] [--dry-run]

Run the M9C local benchmark suite against the active localhost-only SGLang
first real model. Raw JSONL and command observations are written under
/data/logs/benchmarks/m9c. The summarized report is written to
reports/m9c-real-model-benchmark-review.md.
USAGE
}

dry_run=0
for arg in "$@"; do
  case "$arg" in
    --help|-h)
      usage
      exit 0
      ;;
    --dry-run)
      dry_run=1
      ;;
    *)
      usage >&2
      echo "STOP: unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

cd "$(repo_root)"

log_root="/data/logs/benchmarks/m9c"
run_id="${M9C_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
run_dir="$log_root/run-$run_id"
results_jsonl="$log_root/m9c-results.jsonl"
container="sglang-qwen3-30b-a3b-instruct-2507"
cuda_image="nvidia/cuda:13.2.1-base-ubuntu24.04"
export M9C_RUN_ID="$run_id"

if [[ "$dry_run" == 1 ]]; then
  cat <<EOF
M9C benchmark dry-run
repo: $(pwd)
run_id: $run_id
raw_jsonl: $results_jsonl
run_dir: $run_dir
endpoint: http://127.0.0.1:30001/v1/chat/completions
model: qwen3-30b-a3b-instruct-2507
cases: tiny_health technical_short coding_short streaming_short context_4k context_8k context_16k_if_prior_pass
no_restart: true
no_launch_arg_change: true
no_public_exposure: true
EOF
  exit 0
fi

mkdir -p "$run_dir"

timestamp_utc() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

append_json() {
  python3 - "$results_jsonl" <<'PY'
import json, os, sys
path = sys.argv[1]
entry = json.loads(os.environ['M9C_JSON_ENTRY'])
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'a', encoding='utf-8') as fh:
    fh.write(json.dumps(entry, sort_keys=True, separators=(',', ':')) + '\n')
PY
}

record_simple_event() {
  local event_type="$1"
  local status="$2"
  local name="$3"
  local details="$4"
  M9C_JSON_ENTRY="$(python3 - "$event_type" "$status" "$name" "$details" <<'PY'
import json, os, sys
from datetime import datetime, timezone
print(json.dumps({
  'type': sys.argv[1],
  'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
  'run_id': os.environ.get('M9C_RUN_ID', 'manual'),
  'status': sys.argv[2],
  'name': sys.argv[3],
  'details': sys.argv[4],
}))
PY
)" append_json
}

run_and_record_guard() {
  local name="$1"
  shift
  local outfile="$run_dir/guard-$name.txt"
  set +e
  "$@" >"$outfile" 2>&1
  local rc=$?
  set -e
  if [[ "$rc" == 0 ]]; then
    echo "PASS: guard $name"
    record_simple_event guard PASS "$name" "$outfile"
  else
    echo "STOP: guard $name failed; see $outfile" >&2
    record_simple_event guard STOP "$name" "$outfile"
    sed -n '1,160p' "$outfile" >&2 || true
    exit "$rc"
  fi
}

record_resource_snapshot() {
  local label="$1"
  local stage="$2"
  python3 - "$results_jsonl" "$run_dir" "$label" "$stage" <<'PY'
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

results = Path(sys.argv[1])
run_dir = Path(sys.argv[2])
label = sys.argv[3]
stage = sys.argv[4]
run_id = os.environ.get('M9C_RUN_ID', 'manual')
container = 'sglang-qwen3-30b-a3b-instruct-2507'

def run(cmd):
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {'cmd': cmd, 'returncode': proc.returncode, 'stdout': proc.stdout}

nvidia = run([
    'nvidia-smi',
    '--query-gpu=index,name,memory.used,memory.total,utilization.gpu,utilization.memory,power.draw,temperature.gpu',
    '--format=csv,noheader,nounits',
])
docker_stats = run(['sudo', '-n', 'docker', 'stats', '--no-stream', container])
df = run(['df', '-hT', '/', '/data'])
docker_df = run(['sudo', '-n', 'docker', 'system', 'df'])

prefix = f"{label}-{stage}".replace('/', '_')
for suffix, payload in [('nvidia.csv', nvidia), ('docker-stats.txt', docker_stats), ('df.txt', df), ('docker-system-df.txt', docker_df)]:
    (run_dir / f"{prefix}-{suffix}").write_text(payload['stdout'], encoding='utf-8')

gpus = []
if nvidia['returncode'] == 0:
    reader = csv.reader(nvidia['stdout'].splitlines())
    for row in reader:
        if len(row) < 8:
            continue
        def num(value):
            value = value.strip()
            try:
                return float(value)
            except ValueError:
                return None
        gpus.append({
            'index': row[0].strip(),
            'name': row[1].strip(),
            'memory_used_mib': num(row[2]),
            'memory_total_mib': num(row[3]),
            'utilization_gpu_pct': num(row[4]),
            'utilization_memory_pct': num(row[5]),
            'power_draw_w': num(row[6]),
            'temperature_c': num(row[7]),
        })
entry = {
    'type': 'resource_snapshot',
    'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'run_id': run_id,
    'label': label,
    'stage': stage,
    'gpus': gpus,
    'docker_stats_status': docker_stats['returncode'],
    'docker_stats_excerpt': ' '.join(docker_stats['stdout'].split())[:600],
    'df_excerpt': ' | '.join(line.strip() for line in df['stdout'].splitlines())[:600],
    'docker_system_df_excerpt': ' | '.join(line.strip() for line in docker_df['stdout'].splitlines())[:600],
}
results.parent.mkdir(parents=True, exist_ok=True)
with results.open('a', encoding='utf-8') as fh:
    fh.write(json.dumps(entry, sort_keys=True, separators=(',', ':')) + '\n')
print(f"resource {label}/{stage}: gpu_rows={len(gpus)}")
PY
}

record_log_summary() {
  local logfile="$run_dir/sglang-log-tail-300.txt"
  sudo -n docker logs --tail 300 "$container" >"$logfile" 2>&1 || true
  python3 - "$results_jsonl" "$logfile" <<'PY'
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

results = Path(sys.argv[1])
logfile = Path(sys.argv[2])
text = logfile.read_text(encoding='utf-8', errors='replace') if logfile.exists() else ''
patterns = re.compile(r'(warning|warn|error|exception|traceback|oom|out of memory|moe kernel|numa)', re.I)
lines = []
for line in text.splitlines():
    if patterns.search(line):
        compact = ' '.join(line.split())
        if compact not in lines:
            lines.append(compact[:500])
entry = {
    'type': 'log_summary',
    'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'run_id': os.environ.get('M9C_RUN_ID', 'manual'),
    'logfile': str(logfile),
    'matched_warning_error_lines': lines[:30],
    'matched_count': len(lines),
}
results.parent.mkdir(parents=True, exist_ok=True)
with results.open('a', encoding='utf-8') as fh:
    fh.write(json.dumps(entry, sort_keys=True, separators=(',', ':')) + '\n')
print(f"log summary: matched_warning_error_lines={len(lines)} logfile={logfile}")
PY
}

run_lifecycle_dry_run() {
  local name="$1"
  shift
  local outfile="$run_dir/lifecycle-$name.txt"
  set +e
  "$@" >"$outfile" 2>&1
  local rc=$?
  set -e
  if [[ "$rc" == 0 ]]; then
    echo "PASS: lifecycle dry-run $name"
    record_simple_event lifecycle PASS "$name" "$outfile"
  else
    echo "STOP: lifecycle dry-run $name failed; see $outfile" >&2
    record_simple_event lifecycle STOP "$name" "$outfile"
    sed -n '1,160p' "$outfile" >&2 || true
    return "$rc"
  fi
}

run_case() {
  local case_name="$1"
  local max_tokens="$2"
  local temperature="$3"
  local stream_flag="$4"
  local timeout_seconds="$5"
  record_resource_snapshot "$case_name" before
  set +e
  if [[ "$stream_flag" == stream ]]; then
    scripts/bench/bench-openai-chat.py --case "$case_name" --max-tokens "$max_tokens" --temperature "$temperature" --timeout "$timeout_seconds" --stream --output-jsonl "$results_jsonl"
  else
    scripts/bench/bench-openai-chat.py --case "$case_name" --max-tokens "$max_tokens" --temperature "$temperature" --timeout "$timeout_seconds" --output-jsonl "$results_jsonl"
  fi
  local rc=$?
  set -e
  record_resource_snapshot "$case_name" after
  if [[ "$rc" == 0 ]]; then
    echo "PASS: benchmark $case_name"
    return 0
  fi
  echo "FAIL: benchmark $case_name" >&2
  return "$rc"
}

echo "M9C benchmark run_id=$run_id"
record_simple_event run_start PASS m9c "run_dir=$run_dir raw_jsonl=$results_jsonl branch=$(git branch --show-current) commit=$(git rev-parse HEAD)"

run_and_record_guard require_data scripts/common/require-data-mounted.sh
run_and_record_guard root_disk scripts/common/root-disk-guard.sh --report "$run_dir/root-disk-guard-before.md"
run_and_record_guard docker_storage scripts/docker/verify-docker-storage.sh --report "$run_dir/docker-storage-before.md"
sudo -n docker image inspect "$cuda_image" >/dev/null || { echo "STOP: required local CUDA verifier image missing: $cuda_image" >&2; exit 1; }

gpu_verify_root="$run_dir/gpu-verify"
mkdir -p "$gpu_verify_root/scripts" "$gpu_verify_root/reports"
cp -R scripts/common scripts/docker scripts/nvidia "$gpu_verify_root/scripts/"
run_and_record_guard gpu_container bash -c "cd '$gpu_verify_root' && M4_REPORT_PATH='$gpu_verify_root/reports/docker-storage.md' scripts/nvidia/verify-gpu-containers.sh"
run_and_record_guard real_fast_live scripts/sglang/verify-sglang-real-fast-live.sh

record_resource_snapshot suite pre

suite_failed=0
context_4k_pass=0
context_8k_pass=0
run_case tiny_health 64 0 nostream 600 || suite_failed=1
run_case technical_short 200 0.1 nostream 900 || suite_failed=1
run_case coding_short 400 0.1 nostream 900 || suite_failed=1
run_case streaming_short 300 0.1 stream 900 || suite_failed=1
if run_case context_4k 500 0.1 nostream 1200; then
  context_4k_pass=1
else
  suite_failed=1
fi
if [[ "$context_4k_pass" == 1 ]]; then
  if run_case context_8k 700 0.1 nostream 1500; then
    context_8k_pass=1
  else
    suite_failed=1
  fi
else
  record_simple_event bench_skipped SKIP context_8k "context_4k did not pass"
  suite_failed=1
fi
if [[ "$context_4k_pass" == 1 && "$context_8k_pass" == 1 ]]; then
  run_case context_16k 900 0.1 nostream 1800 || suite_failed=1
else
  record_simple_event bench_skipped SKIP context_16k "context_4k/context_8k prerequisite did not pass"
fi

record_resource_snapshot suite post
record_log_summary

run_lifecycle_dry_run status scripts/llmctl status || suite_failed=1
run_lifecycle_dry_run logs_dry_run scripts/llmctl logs --dry-run || suite_failed=1
run_lifecycle_dry_run stop_dry_run scripts/llmctl stop --dry-run || suite_failed=1
run_lifecycle_dry_run restart_dry_run scripts/llmctl restart --dry-run || suite_failed=1

if [[ "$suite_failed" == 0 ]]; then
  record_simple_event run_end PASS m9c "benchmark suite passed"
else
  record_simple_event run_end STOP m9c "one or more benchmark or lifecycle checks failed"
fi

scripts/bench/summarize-m9c-results.py --input-jsonl "$results_jsonl" --run-id "$run_id" --output reports/m9c-real-model-benchmark-review.md

if [[ "$suite_failed" != 0 ]]; then
  exit 1
fi
