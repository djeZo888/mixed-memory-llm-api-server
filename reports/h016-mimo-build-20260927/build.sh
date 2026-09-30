#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'H016 bounded offline isolated compile and server/web build. No activation.'; exit 0; fi
umask 077
H016_TASK=/home/user/ai-harness-build/H016-MIMO-BUILD-20260927
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
cd "$H016_TASK"
trap 'rc=$?; trap - EXIT; printf "%s\n" "$rc" > build.exit; date -u +%FT%TZ > build.finished; exit "$rc"' EXIT
python3 guard.py > pre-build.json
date -u +%FT%TZ > build.started
printf '%s\n' 'd2e160be6081dd69b48da661bc6f9a6e049d258cbd0b3121ef1185d7ece52662  artifact-cache/code-0.3.11.tgz' | sha256sum -c -
timeout --signal=TERM --kill-after=20s 900s podman build --layers --format docker --pull=never --network none --volume "$H016_TASK/artifact-cache:/build/minimax/.cache/artifacts:rw,rprivate" --file "$H016_TASK/Containerfile.compile" --jobs=1 --tag localhost/ai-harness-h016-compiled:928b3b4 --iidfile "$H016_TASK/compiled.iid" source/ai-harness > compile.log 2>&1
for part in server web; do
 donor=/home/user/ai-harness-build/H013-SOVA-1M-20260927/source/ai-harness/$part
 cmp source/ai-harness/$part/package.json "$donor/package.json"
 cmp source/ai-harness/$part/package-lock.json "$donor/package-lock.json"
 cp -a "$donor/node_modules" source/ai-harness/$part/node_modules
 (cd source/ai-harness/$part; npm ls --all --offline; npm run build) > "$part-build.log" 2>&1
 done
(cd source/ai-harness; find server/dist web/dist -type f -print0 | sort -z | xargs -0 sha256sum) > artifacts.SHA256SUMS
python3 guard.py > post-build.json
