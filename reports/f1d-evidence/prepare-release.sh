#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == --help ]]; then
  printf '%s\n' 'Prepare exact reviewed F1D release and narrowly retire obsolete boot writer; --dry-run is required first.'
  exit 0
fi
MODE=${1:-}
[[ $# == 1 && ( $MODE == --dry-run || $MODE == --apply ) ]] || exit 2
[[ $EUID == 0 ]] || exit 2
RUN=/data/build/f1d-qwen-20260915
RELEASE=/data/services/releases/e46c788534d5b71e988c2cdf188f37f6214f7514-f1d-20260915
export TMPDIR=$RUN/tmp
export PYTHONDONTWRITEBYTECODE=1
umask 077
test "$(findmnt -rn -M /data -o UUID)" = 8daf56f1-5649-4163-9d87-919c2d271875
test "$(findmnt -rn -M /data/models-large -o UUID)" = a6d4ab58-84e1-4e48-9a67-13ad1c6f6e0a
bash "$RUN/reviewed-source/scripts/common/require-data-mounted.sh"
bash "$RUN/reviewed-source/scripts/common/root-disk-guard.sh" --report "$RUN/evidence/release-pre-root-guard.md"
test "$(sha256sum "$RUN/integration.bundle" | cut -d ' ' -f1)" = 65b13bd77af17fb5a64d867c9a8def54d3b6673ef75bfce79c1b44f74c9d0d21
test ! -e "$RELEASE"
test ! -e "$RUN/backups/release-pre.tar"
test "$(systemctl show m6b-post-reboot-verify.service -p ActiveState --value)" = active
test "$(systemctl show m6b-post-reboot-verify.service -p SubState --value)" = exited
test "$(sha256sum /etc/systemd/system/m6b-post-reboot-verify.service | cut -d ' ' -f1)" = eb89d7312a0b870163e79e44b9c7f552aeb0b631f9d07fba943c393eddc07ede
test "$(sha256sum /data/services/m6b-post-reboot/m6b-post-reboot-verify.sh | cut -d ' ' -f1)" = 35515bdc2158be054fc3474fc4efa6ca9badeeb3d5ef72c56f1c69664187be76
python3 - <<'PY'
from pathlib import Path
import os,stat
paths=['/data','/data/services','/data/services/llm-manager','/data/services/llm-manager/active','/data/services/secrets']
for name in paths:
 p=Path(name);s=p.lstat()
 assert p.resolve()==p and stat.S_ISDIR(s.st_mode)
for name in ['/data/services/releases','/data/services/llm-manager/acquisition','/data/services/llm-manager/adapters']:
 p=Path(name)
 if p.exists():
  s=p.lstat();assert p.resolve()==p and stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode & 0o022
print('PASS: exact preparation targets validated')
PY
if [[ $MODE == --dry-run ]]; then
  printf '%s\n' 'PLAN: backup manager/unit/script/enablement and metadata; protect services+manager inodes only; clone exact new root-owned release; copy exact adapter; create protected acquisition directory; disable only obsolete m6b unit; daemon-reload. No key/state/model change.' > "$RUN/evidence/release-dry-run.txt"
  cat "$RUN/evidence/release-dry-run.txt"
  exit 0
fi
test -s "$RUN/evidence/release-dry-run.txt"
mkdir -p -m 700 "$RUN/backups"
python3 - <<'PY'
from pathlib import Path
import json,os,stat
paths=['/data','/data/services','/data/services/llm-manager','/data/services/llm-manager/active','/data/services/secrets','/data/models-large','/data/models-large/glm-5.3-ud-q4-k-xl','/data/services/mixed-memory-llm-api-server']
out={}
for name in paths:
 s=Path(name).lstat();out[name]={'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode),'device':s.st_dev,'inode':s.st_ino,'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}
p=Path('/data/build/f1d-qwen-20260915/backups/release-metadata-pre.json')
with p.open('x') as f:json.dump(out,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
PY
systemctl show m6b-post-reboot-verify.service --property=Id,LoadState,ActiveState,SubState,UnitFileState,FragmentPath > "$RUN/backups/m6b-unit-before.txt"
tar --acls --xattrs --numeric-owner -cpf "$RUN/backups/release-pre.tar" -C / data/services/llm-manager etc/systemd/system/m6b-post-reboot-verify.service data/services/m6b-post-reboot/m6b-post-reboot-verify.sh etc/systemd/system/multi-user.target.wants/m6b-post-reboot-verify.service
sha256sum "$RUN/backups/release-pre.tar" > "$RUN/backups/release-pre.tar.sha256"
sha256sum /data/services/mixed-memory-llm-api-server/reports/m3-root-disk-guard.md /data/services/mixed-memory-llm-api-server/reports/m4b-docker-containerd-install.md /data/services/mixed-memory-llm-api-server/reports/m6b-nvidia-container-toolkit-install.md > "$RUN/backups/old-dirty-reports.sha256"
chown 0 /data/services /data/services/llm-manager
chmod g-w,o-w /data/services /data/services/llm-manager
install -d -o root -g root -m 755 /data/services/releases
git clone --quiet --branch milestone/server-completion-20260915 "$RUN/integration.bundle" "$RELEASE"
test "$(git -C "$RELEASE" rev-parse HEAD)" = e46c788534d5b71e988c2cdf188f37f6214f7514
git -C "$RELEASE" checkout --quiet --detach e46c788534d5b71e988c2cdf188f37f6214f7514
test -z "$(git -C "$RELEASE" status --porcelain)"
git -C "$RELEASE" config user.name CodexAIagent
git -C "$RELEASE" config user.email 133749519+djeZo888@users.noreply.github.com
install -d -o root -g root -m 700 /data/services/llm-manager/acquisition
install -d -o root -g root -m 755 /data/services/llm-manager/adapters
test ! -e /data/services/llm-manager/adapters/sglang_file_auth.py
install -o root -g root -m 644 "$RELEASE/scripts/lifecycle/sglang_file_auth.py" /data/services/llm-manager/adapters/sglang_file_auth.py
test "$(sha256sum /data/services/llm-manager/adapters/sglang_file_auth.py | cut -d ' ' -f1)" = 1bf781b83d1a6bf25b63b948550cf2926e16247f48d6f977188954e9a10d212a
systemctl disable m6b-post-reboot-verify.service > "$RUN/evidence/m6b-disable.stdout" 2> "$RUN/evidence/m6b-disable.stderr"
systemctl daemon-reload
test "$(systemctl show m6b-post-reboot-verify.service -p UnitFileState --value)" = disabled
systemctl show m6b-post-reboot-verify.service --property=Id,LoadState,ActiveState,SubState,UnitFileState,FragmentPath > "$RUN/evidence/m6b-unit-after.txt"
sha256sum -c "$RUN/backups/old-dirty-reports.sha256"
PYTHONPATH="$RELEASE/scripts" python3 - <<'PY'
from lifecycle.qwen_next import protected_bytes
import hashlib
assert hashlib.sha256(protected_bytes('/data/services/llm-manager/adapters/sglang_file_auth.py')).hexdigest()=='1bf781b83d1a6bf25b63b948550cf2926e16247f48d6f977188954e9a10d212a'
print('PASS: reviewed protected adapter validator')
PY
bash "$RELEASE/scripts/common/require-data-mounted.sh"
bash "$RELEASE/scripts/common/root-disk-guard.sh" --report "$RUN/evidence/release-post-root-guard.md"
printf '%s\n' 'PASS_PREPARED_AUTH_BLOCKED' > "$RUN/evidence/release-result.txt"
cat "$RUN/evidence/release-result.txt"
