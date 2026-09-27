#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'Stage only the checked H016 host artifacts and proposed units; no activation or build.'; exit 0; fi
umask 077
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
H016_BUILD=/home/user/ai-harness-build/H016-MIMO-BUILD-20260927
H016_PREP=/home/user/ai-harness-build/H016-ACTIVATION-PREP-20260927
H016_NEW=/opt/ai-harness/releases/928b3b470058241f089a839367d4b30d5887a6e3-h016/ai-harness
cd "$H016_PREP"
python3 "$H016_BUILD/guard.py" > private/before.json
python3 verify-stage.py inputs > artifact-checks.json
test ! -e "$H016_NEW"
sudo -n install -d -m 755 "$(dirname "$H016_NEW")"
sudo -n cp -a "$H016_BUILD/source/ai-harness" "$H016_NEW"
sudo -n chown -R root:root "$H016_NEW"
sudo -n chmod -R u=rwX,go=rX "$H016_NEW"
python3 verify-stage.py staged > staged-checks.json
(cd "$H016_NEW/server"; node --input-type=module -e "await import('./dist/app.js'); await import('./dist/gateway.js'); await import('./dist/mimo-frontier.js'); console.log('PASS staged imports; no entrypoint started')") > imports.log 2>&1
systemd-analyze --user verify "$H016_PREP/proposed/ai-harness.service" > unit-verify.log 2>&1
python3 "$H016_BUILD/guard.py" > private/after.json
python3 verify-stage.py preservation > preservation.json
