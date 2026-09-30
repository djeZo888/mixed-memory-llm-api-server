#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'Build once from authentic protected qualification; stage immutable paired release and unit proposals. Usage: build-and-stage.sh SOURCE_COMMIT RECEIPT_SHA256. No apply/start/inference.'; exit 0; fi
umask 077
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
H016_SOURCE=${1:?source commit}; H016_SHA=${2:?receipt sha256}
[[ $H016_SOURCE =~ ^[a-f0-9]{40}$ && $H016_SHA =~ ^[a-f0-9]{64}$ ]]
H016_TASK=/home/user/ai-harness-build/H016-FINAL-BUILD-ACTIVATE-20260927
H016_GUARD=/home/user/ai-harness-build/H016-TIMEOUT-COMPILE-20260927/artifact-guard.py
H016_BASE=/opt/ai-harness/releases/df0702412b1a8f594db7d3211ca63f6aafe8a026-h016/ai-harness
H016_NEW=/opt/ai-harness/releases/${H016_SOURCE}-h016-final18/ai-harness
H016_STAGE=$H016_TASK/final-stage
cd "$H016_TASK"
printf '%s\n' "d84153e75b13c8f59a7a0c31c8a5cca2ac5cc8469ab3e1cc72ecc0f2220be496  $H016_GUARD" | sha256sum -c -
python3 "$H016_GUARD" > private/pre-build.json
sha256sum -c SOURCE.SHA256SUMS > private/source-checks.txt
test "$(cat SOURCE-COMMIT)" = "$H016_SOURCE"
test ! -e "$H016_STAGE"
test ! -e "$H016_NEW"
node stage-qualified-config.mjs "$H016_BASE" /etc/sova-qualification/mimo.json "$H016_SHA" "$H016_STAGE" "$H016_TASK/source/ai-harness/deploy/engine/configure-profile.mjs"
python3 assemble-final.py "$H016_STAGE" /home/user/ai-harness-build/H016-TIMEOUT-COMPILE-20260927/timeout14-payload.tar.gz "$H016_TASK/source" "$H016_SOURCE"
(cd "$H016_STAGE"; sha256sum -c FINAL.SHA256SUMS > ../private/final-input-checks.txt; podman build --pull=never --network none --layers --format docker --jobs=1 --file Containerfile --iidfile final-combined.iid .) > private/build.log 2>&1
python3 "$H016_GUARD" > private/post-build.json
bash verify-built.sh
sudo -n install -d -o root -g root -m 755 "$(dirname "$H016_NEW")"
sudo -n cp -a --reflink=auto "$H016_BASE" "$H016_NEW"
python3 - "$H016_STAGE/host" "$H016_NEW" <<'PY'
import pathlib,subprocess,sys
src,dst=map(pathlib.Path,sys.argv[1:])
for p in sorted(src.rglob('*')):
 if p.is_file():
  q=dst/p.relative_to(src)
  subprocess.run(['sudo','-n','install','-D','-o','root','-g','root','-m','755' if str(p.relative_to(src))=='deploy/run-engine.sh' else '644',str(p),str(q)],check=True)
PY
python3 - "$H016_SOURCE" <<'PY'
import pathlib,hashlib,json,sys,difflib
root=pathlib.Path.cwd();source=sys.argv[1];new=f'/opt/ai-harness/releases/{source}-h016-final18/ai-harness';old='/opt/ai-harness/releases/df0702412b1a8f594db7d3211ca63f6aafe8a026-h016/ai-harness'
proposed=root/'proposed';proposed.mkdir()
prior=pathlib.Path('/home/user/ai-harness-build/H016-FINAL-INTEGRATION-20260927/proposed')
expected={'ai-harness.service':'e8cdf8f8015fb25bea744fc036405b0e7ad0c8692170791f4d66995582ccccde','30-h008-registry.conf':'45fcd10bad42bb903ced6b32d8621e34377e06077b1ca3c5536056da19a4be79'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,h in expected.items():
 p=prior/name;assert sha(p)==h;body=p.read_text();assert old in body
 (proposed/name).write_text(body.replace(old,new));(proposed/name).chmod(0o600)
 installed=pathlib.Path('/home/user/.config/systemd/user/ai-harness.service' if name=='ai-harness.service' else '/etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf')
 (root/'private'/('original-'+name)).write_bytes(installed.read_bytes())
 (root/'private'/(name+'.diff')).write_text(''.join(difflib.unified_diff(installed.read_text().splitlines(True),(proposed/name).read_text().splitlines(True),fromfile=str(installed),tofile=str(proposed/name))))
(proposed/'SHA256SUMS').write_text(''.join(f'{sha(proposed/n)}  proposed/{n}\n' for n in expected))
release=pathlib.Path(new);host=root/'final-stage/host';closure={}
for p in sorted(host.rglob('*')):
 if p.is_file():
  rel=str(p.relative_to(host));assert sha(p)==sha(release/rel);closure[rel]=sha(p)
assert sha(release/'server/dist/active-frontier.js')=='3a4b7f6a2563fd1c123cc14532fdd29c1ba3613544c87f7a3056b17bfefa0c35'
closure['server/dist/active-frontier.js']=sha(release/'server/dist/active-frontier.js')
(root/'private/PAIRED-HOST-CLOSURE.json').write_text(json.dumps({'source':source,'release':new,'releaseSha256':closure,'units':{n:sha(proposed/n) for n in expected},'applied':False,'appStarted':False},indent=2)+'\n')
PY
systemd-analyze --user verify "$H016_TASK/proposed/ai-harness.service" > private/unit-verify.log 2>&1
bash activate-pair.sh "$H016_SHA" "$(cat "$H016_STAGE/final-combined.iid")" "$H016_SOURCE" --dry-run > private/pair-dry-run.log 2>&1
python3 "$H016_GUARD" > private/post-staging.json
date -u +%FT%TZ > private/build-and-stage.finished
