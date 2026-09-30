#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'Stage checked H016 receipt-path server only; create empty nonsecret receipt directory; no activation.'; exit 0; fi
umask 077
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
H016_TASK=/home/user/ai-harness-build/H016-FINAL-INTEGRATION-20260927
H016_BASE=/opt/ai-harness/releases/928b3b470058241f089a839367d4b30d5887a6e3-h016/ai-harness
H016_NEW=/opt/ai-harness/releases/df0702412b1a8f594db7d3211ca63f6aafe8a026-h016/ai-harness
cd "$H016_TASK"
python3 /home/user/ai-harness-build/H016-MIMO-BUILD-20260927/guard.py > private/pre-stage.json
python3 -c 'import json; assert json.load(open("BUILD-CHECKS.json"))["result"] == "PASS"'
sudo -n python3 etc-metadata.py > private/etc-before.json
test ! -e "$H016_NEW"
sudo -n install -d -o root -g root -m 755 "$(dirname "$H016_NEW")"
sudo -n cp -a --reflink=auto "$H016_BASE" "$H016_NEW"
for H016_FILE in server/src/active-frontier.ts server/dist/active-frontier.js server/test/mimo-receipt.test.ts; do
 sudo -n install -o root -g root -m 644 "ai-harness/$H016_FILE" "$H016_NEW/$H016_FILE"
done
sudo -n python3 - <<'PY'
import os,pathlib,stat
p=pathlib.Path('/etc/sova-qualification')
for q in p.parents:
 s=q.lstat(); assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022 and q.resolve()==q
if not p.exists(): p.mkdir(mode=0o755)
s=p.lstat(); assert stat.S_ISDIR(s.st_mode) and s.st_uid==s.st_gid==0 and stat.S_IMODE(s.st_mode)==0o755 and p.resolve()==p
assert not (p/'mimo.json').exists(), 'unexpected existing receipt: preserve and review'
PY
sudo -n python3 etc-metadata.py > private/etc-after.json
cmp private/etc-before.json private/etc-after.json
(cd "$H016_NEW/server"; node --input-type=module -e "await import('./dist/active-frontier.js'); await import('./dist/app.js'); console.log('PASS compiled imports; no main or inference')") > imports.txt
python3 /home/user/ai-harness-build/H016-MIMO-BUILD-20260927/guard.py > private/after.json
python3 verify-final.py > STAGING-CHECKS.json
