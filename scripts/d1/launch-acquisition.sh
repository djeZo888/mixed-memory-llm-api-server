#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then
  echo 'Usage: launch-acquisition.sh RUN_DIR MODEL_UUID REVIEWED_READY_SHA256 [UNIT_NAME]'
  echo 'Requires RUN_DIR/evidence/d0b-storage-ready.md copied from reviewed D0B PASS handoff.'
  echo 'Starts a bounded durable acquisition job. Same command resumes partials in place.'
  exit 0
fi
[[ $# -ge 3 && $# -le 4 ]] || { echo 'Use --help' >&2; exit 2; }
RUN=$(realpath -e "$1")
MODEL_UUID=$2
READY_SHA=$3
UNIT=${4:-d1-glm53-acquire-20260915}
[[ $RUN == /data/build/d1-* && $UNIT =~ ^d1-glm53-acquire-[a-zA-Z0-9-]+$ && $READY_SHA =~ ^[0-9a-f]{64}$ ]] || exit 2
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$SCRIPT_DIR/storage_guard.py" --model-uuid "$MODEL_UUID"
[[ $(sha256sum "$RUN/evidence/d0b-storage-ready.md" | cut -d' ' -f1) == "$READY_SHA" ]]
# Refuse competing acquisition jobs, including differently named resumes.
if systemctl list-units --type=service --state=active --no-legend 'd1-glm53-acquire-*' | grep -q d1-glm53-acquire-; then
  echo 'STOP: acquisition unit is already active' >&2; exit 1
fi
sudo -n systemd-run --unit="$UNIT" --uid=user --gid=ai \
  --property="WorkingDirectory=$RUN" \
  --property="StandardOutput=append:$RUN/acquisition.log" \
  --property="StandardError=append:$RUN/acquisition.log" \
  --property=MemoryMax=2G --property=TasksMax=128 --property=Nice=10 \
  --property=RuntimeMaxSec=36h --setenv="TMPDIR=$RUN/tmp" \
  --setenv=PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/python3 "$SCRIPT_DIR/acquire.py" \
  --manifest "$RUN/repo/reports/r2-flagship-artifact.json" --run-dir "$RUN" \
  --model-uuid "$MODEL_UUID" --storage-ready "$RUN/evidence/d0b-storage-ready.md" \
  --ready-sha256 "$READY_SHA"
