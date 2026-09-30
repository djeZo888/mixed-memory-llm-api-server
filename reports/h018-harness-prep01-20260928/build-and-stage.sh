#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'Build once from authentic protected qualification; stage immutable paired release and unit proposals. Usage: build-and-stage.sh SOURCE_COMMIT RECEIPT_SHA256. No apply/start/inference.'; exit 0; fi
umask 077
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
H018_SOURCE=${1:?source commit}; H018_SHA=${2:?receipt sha256}
[[ $H018_SOURCE =~ ^[a-f0-9]{40}$ && $H018_SHA =~ ^[a-f0-9]{64}$ ]]
H018_TASK=/home/user/ai-harness-build/H018-HARNESS-PREP01-20260928
H018_GUARD=/home/user/ai-harness-build/H016-TIMEOUT-COMPILE-20260927/artifact-guard.py
H018_BASE=/opt/ai-harness/releases/6c4b5869d9bc7658fcaf565b642bd951ad0f5752-h016-final18/ai-harness
H018_NEW=/opt/ai-harness/releases/${H018_SOURCE}-h018-prep01/ai-harness
H018_STAGE=$H018_TASK/final-stage
cd "$H018_TASK"
printf '%s\n' "d84153e75b13c8f59a7a0c31c8a5cca2ac5cc8469ab3e1cc72ecc0f2220be496  $H018_GUARD" | sha256sum -c -
python3 "$H018_GUARD" > private/pre-build.json
sha256sum -c SOURCE.SHA256SUMS > private/source-checks.txt
test "$(cat SOURCE-COMMIT)" = "$H018_SOURCE"
test ! -e "$H018_STAGE"
test ! -e "$H018_NEW"
node stage-qualified-config.mjs "$H018_BASE" /etc/sova-qualification/mimo.json "$H018_SHA" "$H018_STAGE" "$H018_TASK/source/ai-harness/deploy/engine/configure-profile.mjs"
python3 assemble-final.py "$H018_STAGE" /home/user/ai-harness-build/H016-TIMEOUT-COMPILE-20260927/timeout14-payload.tar.gz "$H018_TASK/source" "$H018_SOURCE"
(cd "$H018_STAGE"; sha256sum -c FINAL.SHA256SUMS > ../private/final-input-checks.txt; podman build --pull=never --network none --layers --format docker --jobs=1 --file Containerfile --iidfile final-combined.iid .) > private/build.log 2>&1
python3 "$H018_GUARD" > private/post-build.json
bash verify-built.sh
sudo -n install -d -o root -g root -m 755 "$(dirname "$H018_NEW")"
sudo -n cp -a --reflink=auto "$H018_BASE" "$H018_NEW"
python3 - "$H018_STAGE/host" "$H018_NEW" <<'PY'
import pathlib,subprocess,sys
src,dst=map(pathlib.Path,sys.argv[1:])
for p in sorted(src.rglob('*')):
 if p.is_file():
  q=dst/p.relative_to(src)
  subprocess.run(['sudo','-n','install','-D','-o','root','-g','root','-m','755' if str(p.relative_to(src))=='deploy/run-engine.sh' else '644',str(p),str(q)],check=True)
PY
python3 - "$H018_SOURCE" <<'PY'
import pathlib,hashlib,json,sys,difflib
root=pathlib.Path.cwd();source=sys.argv[1];new=f'/opt/ai-harness/releases/{source}-h018-prep01/ai-harness';old='/opt/ai-harness/releases/6c4b5869d9bc7658fcaf565b642bd951ad0f5752-h016-final18/ai-harness'
proposed=root/'proposed';proposed.mkdir()
prior=pathlib.Path('/home/user/ai-harness-build/H016-FINAL-BUILD-ACTIVATE-20260927/proposed')
expected={'ai-harness.service': 'd51eb566d66deaa62750eb45a49ccdd715198da690c46b3406d5a748a9cd8a1e', '30-h008-registry.conf': 'e2f59b2ed574e7b2434d54668db5ec45a7d551ffe01ae9bc8cc2702d215fc4a9'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,h in expected.items():
 p=prior/name;assert sha(p)==h;body=p.read_text();assert old in body
 (proposed/name).write_text(body.replace(old,new));(proposed/name).chmod(0o600)
 installed=pathlib.Path('/home/user/.config/systemd/user/ai-harness.service' if name=='ai-harness.service' else '/etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf')
 (root/'private'/('original-'+name)).write_bytes(installed.read_bytes())
 (root/'private'/(name+'.diff')).write_text(''.join(difflib.unified_diff(installed.read_text().splitlines(True),(proposed/name).read_text().splitlines(True),fromfile=str(installed),tofile=str(proposed/name))))
(proposed/'SHA256SUMS').write_text(''.join(f'{sha(proposed/n)}  proposed/{n}\n' for n in expected))
release=pathlib.Path(new);host=root/'final-stage/host'
retained=json.loads((root/'source/reports/h016-final-build-activate-20260927/PAIRED-HOST-CLOSURE.json').read_text())
closure=dict(retained['releaseSha256'])
for rel,h in closure.items():assert sha(pathlib.Path(old)/rel)==h
for rel,h in closure.items():
 if not (host/rel).exists():assert sha(release/rel)==h
for p in sorted(host.rglob('*')):
 if p.is_file():
  rel=str(p.relative_to(host));assert sha(p)==sha(release/rel);closure[rel]=sha(p)
assert sha(release/'server/dist/active-frontier.js')=='3a4b7f6a2563fd1c123cc14532fdd29c1ba3613544c87f7a3056b17bfefa0c35'
closure['server/dist/active-frontier.js']=sha(release/'server/dist/active-frontier.js')
(root/'private/PAIRED-HOST-CLOSURE.json').write_text(json.dumps({'source':source,'release':new,'releaseSha256':closure,'units':{n:sha(proposed/n) for n in expected},'applied':False,'appStarted':False},indent=2)+'\n')
PY
systemd-analyze --user verify "$H018_TASK/proposed/ai-harness.service" > private/unit-verify.log 2>&1
bash activate-pair.sh "$H018_SHA" "$(cat "$H018_STAGE/final-combined.iid")" "$H018_SOURCE" --dry-run > private/pair-dry-run.log 2>&1
python3 "$H018_GUARD" > private/post-staging.json
date -u +%FT%TZ > private/build-and-stage.finished
