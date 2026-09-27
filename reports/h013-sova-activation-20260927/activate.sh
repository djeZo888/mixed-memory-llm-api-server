#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then echo 'Activate exact root-authorized H013 Sova release; preserves user data and credentials.'; exit 0; fi
umask 077
H013_TASK=/home/user/ai-harness-build/H013-SOVA-1M-20260927
H013_OLD=/opt/ai-harness/releases/296ae49e44eb250773223885b843994e2c5b9bcc/ai-harness
H013_RELEASE=/opt/ai-harness/releases/7143c17d73173db9364b77956679c86d7026a4ae/ai-harness
H013_UNIT=/home/user/.config/systemd/user/ai-harness.service
H013_STATUS=/etc/systemd/system/ai-harness-status.service.d/30-h008-registry.conf
H013_TAG=localhost/ai-harness-engine:0.0.2-ae65651df5f9
H013_OLD_IMAGE=c328dac0e6ede1dfb890a0657ebafd6f6fd4a1f2281f4e1c664ab95db7dcaa20
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/bin:/bin
cd "$H013_TASK"
stage=preflight
trap 'rc=$?; trap - EXIT; printf "%s %s %s\n" "$(date -u +%FT%TZ)" "$stage" "$rc" > activation.exit; exit "$rc"' EXIT
mark(){ stage="$1"; printf '%s %s\n' "$(date -u +%FT%TZ)" "$stage"; }
test "$(date -u +%s)" -lt 1790494753
python3 preservation.py pre-activation-final.json --compare before.json
H013_IMAGE=$(cat "$H013_TASK/candidate-overlay.iid")
test "$H013_IMAGE" = 'sha256:9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c'
test "$(cat source.commit)" = 7143c17d73173db9364b77956679c86d7026a4ae
printf '%s\n' '185c76b91c3bbfe68ac78f684eaebbbaf65cd5683f0253797754a66235d49eaa  H013-source.tar' '7360f1430ea0b00b1ecf1a5071ac33b5e05fb8e0b6a7500f1b2cef31d57d9378  artifacts.SHA256SUMS' '9f480de6c649c0d7ace6f233f20e7a2156d3febe07fa9f6de57c07156b4e524d  source.SHA256SUMS' '43f671c752b3376e552623b0508b1c9c25b89c941e6332161f3c25daf1c3e362  source/ai-harness/deploy/engine/configure-profile.mjs' | sha256sum -c -
sha256sum -c source.SHA256SUMS
(cd source/ai-harness; sha256sum -c ../../artifacts.SHA256SUMS) > activation-artifacts-check.log
python3 - <<'PY'
import tarfile,pathlib,hashlib
with tarfile.open('H013-source.tar') as t:
 for m in t.getmembers():
  if m.isfile():
   p=pathlib.Path('source')/m.name
   assert p.is_file() and not p.is_symlink()
   assert hashlib.sha256(p.read_bytes()).digest()==hashlib.sha256(t.extractfile(m).read()).digest(),m.name
print('PASS exact source archive content')
PY
test "$(podman image inspect localhost/ai-harness-engine:h013-7143c17-profile --format '{{.Id}}')" = "${H013_IMAGE#sha256:}"
test ! -e "$H013_RELEASE"
mark backup
mkdir -m 700 activation-backup
cp -a "$H013_UNIT" activation-backup/ai-harness.service
cp -a "$H013_STATUS" activation-backup/30-h008-registry.conf
python3 - <<'PY'
import pathlib,sqlite3
root=pathlib.Path('/home/user/.local/share/ai-harness')
for name in ('harness.sqlite','owner.sqlite'):
 with sqlite3.connect(f'file:{root/name}?mode=ro',uri=True) as src:
  with sqlite3.connect(pathlib.Path('activation-backup')/name) as dst:
   src.backup(dst); assert dst.execute('pragma integrity_check').fetchone()[0]=='ok'
print('PASS private backup evidence integrity; never restore data')
PY
mark immutable_release_install
sudo -n install -d -m 755 "$(dirname "$H013_RELEASE")"
sudo -n cp -a source/ai-harness "$H013_RELEASE"
sudo -n chown -R root:root "$H013_RELEASE"
sudo -n chmod -R a+rX "$H013_RELEASE"
(cd "$H013_RELEASE/server"; node --input-type=module -e "await import('./dist/app.js'); await import('./dist/gateway.js'); console.log('PASS ordinary user installed imports')")
mark stage_units
python3 - "$H013_UNIT" "$H013_OLD" "$H013_RELEASE" "$H013_STATUS" <<'PY'
import pathlib,sys
unit,old,new,status=sys.argv[1:]
s=pathlib.Path(unit).read_text();assert old in s
pathlib.Path('ai-harness.service').write_text(s.replace(old,new))
s=pathlib.Path(status).read_text();old_status='/opt/ai-harness/components/H008-REGISTRY-296ae49/ai-harness';assert old_status in s
pathlib.Path('30-h008-registry.conf').write_text(s.replace(old_status,new))
PY
systemd-analyze --user verify "$H013_TASK/ai-harness.service"
python3 - <<'PY'
import importlib.util,json,pathlib
s=importlib.util.spec_from_file_location('prior','/home/user/ai-harness-build/H010-WORKER2-20260927/recover-harness-02.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.require_idle(m.summary());u=m.unit('ai-harness.service',True);assert u['ActiveState']=='inactive' and u['MainPID']=='0'
b=json.loads(pathlib.Path('activation-content-before.json').read_text());assert m.unit('ai-harness-searxng.service',True)==b['units']['ai-harness-searxng.service']
assert json.loads(json.dumps(m.summary()))==b['data']
print('PASS actual app stopped/PID0, local native/user/image jobs terminal; Search unchanged')
PY
test "$(date -u +%s)" -lt 1790494753
test "$(podman image inspect "$H013_TAG" --format '{{.Id}}')" = "$H013_OLD_IMAGE"
test "$H013_IMAGE" = 'sha256:9ef88598cf54a03aa259c5aa2d2878b34b7473cfcec7c8c07cee6ba462c39f1c'
mark paired_promotion
podman tag "$H013_IMAGE" "$H013_TAG"
install -m 600 ai-harness.service "$H013_UNIT.h013-new"
mv "$H013_UNIT.h013-new" "$H013_UNIT"
sudo -n install -o root -g root -m 644 30-h008-registry.conf "$H013_STATUS.h013-new"
sudo -n mv "$H013_STATUS.h013-new" "$H013_STATUS"
systemctl --user daemon-reload
sudo -n systemctl daemon-reload
mark status_restart
sudo -n systemctl restart ai-harness-status.service
mark app_start
systemctl --user start ai-harness.service
mark app_start_returned
