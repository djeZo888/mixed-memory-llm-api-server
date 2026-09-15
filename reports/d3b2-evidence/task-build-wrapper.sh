#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then
  printf 'Usage: task-build-wrapper.sh\nOne D3B2 reviewed build; run only via its authorized transient unit.\n'
  exit 0
fi
[[ $# == 0 ]]
RUN=/data/build/d3p-d3b2-20260915
[[ $PWD == "$RUN" && $HOME == /home/user ]]
[[ ! -e "$RUN/job.started" && ! -e "$RUN/job.exit" ]]
umask 007
sudo -n /usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py --root-guard --json >/dev/null
printf '%s\n' "$$" > "$RUN/job.pid"
date -u +%FT%TZ > "$RUN/job.started"
set +e
"$RUN/repo/containers/llama-cpp/build-d3p-runtime.sh" "$RUN"
result=$?
set -e
# Refuse completion-file writes if the registered data guard now fails.
sudo -n /usr/bin/python3 -I -B /usr/local/lib/llm-server/control-api/scripts/common/registered-storage.py --root-guard --json >/dev/null
printf '%s\n' "$result" > "$RUN/job.exit"
date -u +%FT%TZ > "$RUN/job.finished"
exit "$result"
