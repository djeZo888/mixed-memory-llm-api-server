#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then
  echo 'Usage: launch-acquisition.sh RUN_DIR MANIFEST_SHA256 GLM_MANIFEST_SHA256 [UNIT_NAME] [WORKERS: 1-4]'
  echo 'Launches only pinned Qwen acquisition; default two streams. Never changes GLM or inference.'
  echo 'Exact run: /data/build/f1a-qwen-20260915; immutable manifests in RUN_DIR/repo/reports/.'
  exit 0
fi
[[ $# -ge 3 && $# -le 5 ]] || { echo 'Use --help' >&2; exit 2; }
RUN=$1
MANIFEST_SHA=$2
GLM_MANIFEST_SHA=$3
UNIT=${4:-f1a-qwen-fast-acquire-20260915}
WORKERS=${5:-2}
[[ $RUN == /data/build/f1a-qwen-20260915 && $WORKERS =~ ^[1-4]$ &&
   $UNIT =~ ^f1a-qwen-fast-acquire-[a-zA-Z0-9-]+$ &&
   $MANIFEST_SHA =~ ^[0-9a-f]{64}$ && $GLM_MANIFEST_SHA =~ ^[0-9a-f]{64}$ ]] || exit 2
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export TMPDIR="$RUN/tmp" PYTHONDONTWRITEBYTECODE=1
MODEL_UUID=a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a
# Strict mount checks precede data output. Never canonicalize a symlink into acceptance.
python3 "$SCRIPT_DIR/../d1/storage_guard.py" --model-uuid "$MODEL_UUID"
python3 - "$RUN" "$SCRIPT_DIR" <<'PY'
import os
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[2])
from acquire import no_symlinks
run = Path(sys.argv[1])
for path in (run, run / 'tmp', run / 'evidence', run / 'acquisition.log'):
    no_symlinks(path)
    if path.exists() and path.stat().st_dev != os.stat('/data').st_dev:
        raise SystemExit('STOP: task path redirects to another filesystem')
if not (run / 'tmp').is_dir() or not (run / 'evidence').is_dir():
    raise SystemExit('STOP: guarded staging directories must already exist')
PY
python3 "$SCRIPT_DIR/../d1/storage_guard.py" --model-uuid "$MODEL_UUID" \
  --report "$RUN/evidence/root-launch-before.md"
[[ $(sha256sum "$RUN/repo/reports/f1a-qwen-manifest.json" | cut -d' ' -f1) == "$MANIFEST_SHA" ]]
[[ $(sha256sum "$RUN/repo/reports/r2-flagship-artifact.json" | cut -d' ' -f1) == "$GLM_MANIFEST_SHA" ]]
if systemctl list-units --type=service --state=active,activating,deactivating --no-legend 'f1a-qwen-fast-acquire-*' | grep -q f1a-qwen-fast-acquire-; then
  echo 'STOP: Qwen acquisition unit already active' >&2; exit 1
fi
sudo -n systemd-run --unit="$UNIT" --uid=user --gid=ai \
  --property="WorkingDirectory=$RUN" \
  --property="StandardOutput=append:$RUN/acquisition.log" \
  --property="StandardError=append:$RUN/acquisition.log" \
  --property=MemoryMax=2G --property=TasksMax=128 --property=Nice=10 \
  --property=TimeoutStopSec=120 --property=RuntimeMaxSec=36h \
  --setenv="TMPDIR=$RUN/tmp" --setenv=PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/python3 "$SCRIPT_DIR/acquire.py" \
  --manifest "$RUN/repo/reports/f1a-qwen-manifest.json" --manifest-sha256 "$MANIFEST_SHA" \
  --glm-manifest "$RUN/repo/reports/r2-flagship-artifact.json" --glm-manifest-sha256 "$GLM_MANIFEST_SHA" \
  --run-dir "$RUN" --workers "$WORKERS"
python3 "$SCRIPT_DIR/../d1/storage_guard.py" --model-uuid "$MODEL_UUID" \
  --report "$RUN/evidence/root-launch-after.md"
