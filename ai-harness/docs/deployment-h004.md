# H004 deployment and rollback — later reviewed session only

These commands are a reviewable procedure, **not authority to run them in PREP**.
Root must review the exact commit in the parent `REPORT.md` and assign a fresh
Worker2 activation session. Nothing here contacts ai-vm directly or changes model
placement, nginx, keys, runtime pins or installer state. All private inventories,
backups and command output stay in the protected host task directory.

## Fixed paths and preconditions

- Host: SSH `ai-harness`, ordinary account `user`, 10.156.100.61.
- Prior release: `/home/user/.local/share/ai-harness-app/releases/9de9ecf701bedd0bcb337d9dcb49a4aca1c3fa27`.
- Persistent data: `/home/user/.local/share/ai-harness`.
- Unit: `/home/user/.config/systemd/user/ai-harness.service`.
- Node: `/home/user/.local/opt/ai-harness/node-v24.21.0/bin`.
- Expected prior engine: `11e764b2f30822ef7f65c6484c9e13892f8b18ac8b6ea4a9ae1fa2cd8473fb87`.
- Production engine alias: `localhost/ai-harness-engine:0.0.2-ae65651df5f9`.

Reverify these identities and protected ancestry in the fresh session; stop on
mismatch. Use the current harness host storage/free-space guard before/after source
staging, builds, backups and activation. The ai-vm registered-storage helpers do
not apply to this separate host, and historical H003 mutation helpers must not be
rerun. Preserve sufficient space for the complete private backup (at least the
previous 20GiB free-space gate, increased if the live data requires it).

Coordinate an exclusive quiet window. A read-only SQLite check must find no
queued/running/cancelling/unknown work, no unfinished image jobs, and idle text
lanes immediately before stop. Check native task/container settlement too. If
user work starts, stop this procedure and retain the staged candidate; do not
cancel it. These checks are not an atomic drain mechanism.

## Stage the exact candidate

On Worker2, after exact-source approval, create a source-only archive from the
reported commit (not the dirty working tree) and its checksum. Transfer only that
archive and a `REVIEWED-COMMIT` file containing the approved full40-character hash
into `/home/user/.local/share/ai-harness-deploy/H004-ACTIVATE-20260924` using the
fresh session's authorized transfer. Never transfer the parent private traces.

```bash
set -euo pipefail
# Worker2: set this to the full reviewed hash from REPORT.md, then verify it.
H004_COMMIT=$(cat ../REVIEWED-COMMIT)
test "$(git rev-parse "$H004_COMMIT^{commit}")" = "$H004_COMMIT"
git archive --format=tar --output=../H004-source.tar "$H004_COMMIT" ai-harness
shasum -a 256 ../H004-source.tar
```

On ai-harness as `user`, after the current storage/identity guard passes:

```bash
set -euo pipefail
umask 077
test "$(id -un)" = user
H004_TASK=/home/user/.local/share/ai-harness-deploy/H004-ACTIVATE-20260924
H004_COMMIT=$(cat "$H004_TASK/REVIEWED-COMMIT")
[[ "$H004_COMMIT" =~ ^[a-f0-9]{40}$ ]]
H004_RELEASE=/home/user/.local/share/ai-harness-app/releases/$H004_COMMIT
H004_OLD=/home/user/.local/share/ai-harness-app/releases/9de9ecf701bedd0bcb337d9dcb49a4aca1c3fa27
H004_ENGINE=11e764b2f30822ef7f65c6484c9e13892f8b18ac8b6ea4a9ae1fa2cd8473fb87
H004_TAG=localhost/ai-harness-engine:h004-$H004_COMMIT
export PATH=/home/user/.local/opt/ai-harness/node-v24.21.0/bin:/usr/local/bin:/usr/bin:/bin
test "$(node --version)" = v24.21.0
test "$(podman image inspect localhost/ai-harness-engine:0.0.2-ae65651df5f9 --format '{{.Id}}')" = "$H004_ENGINE"
test ! -e "$H004_RELEASE"
mkdir -m 700 "$H004_RELEASE"
# Verify the transferred tar checksum against Worker2's receipt before extraction.
# git archive has only reviewed ai-harness paths; inspect members before extraction.
tar -xf "$H004_TASK/H004-source.tar" -C "$H004_RELEASE"
(cd "$H004_RELEASE/ai-harness/server" && npm ci --no-audit --no-fund && npm run build)
(cd "$H004_RELEASE/ai-harness/web" && npm ci --no-audit --no-fund && npm run build)
```

Verify extracted source hashes against `git ls-tree`/the reviewed archive. Do not
reuse old server/web `dist`; source changed. Lockfiles are unchanged. No live
engine startup or model request is required to build these components.

The image adapter/skill lives in the engine, so an app-only release is incomplete.
Build a minimal rootless overlay on the exact retained engine, keeping its native
ACP binary/dependencies and labels. The two adapter files and image skill are the
only runtime engine changes; dependency locks and native catalog schemas are
unchanged. A complete Containerfile rebuild is not needed for this change.

```bash
cat > "$H004_TASK/Containerfile" <<'DOCKER'
FROM 11e764b2f30822ef7f65c6484c9e13892f8b18ac8b6ea4a9ae1fa2cd8473fb87
USER root
COPY tools/image/image.mjs tools/image/image-mcp.mjs /opt/ai-harness/tools/image/
COPY skills/image/SKILL.md /opt/ai-harness/skills/image/SKILL.md
USER 1000:1000
DOCKER
podman build --pull=never --network=none --format docker \
  --file "$H004_TASK/Containerfile" --tag "$H004_TAG" "$H004_RELEASE/ai-harness"
podman run --rm --network=none --entrypoint node "$H004_TAG" \
  --check /opt/ai-harness/tools/image/image.mjs
podman run --rm --network=none --entrypoint node "$H004_TAG" \
  --check /opt/ai-harness/tools/image/image-mcp.mjs
H004_CANDIDATE=$(podman image inspect "$H004_TAG" --format '{{.Id}}')
[[ "$H004_CANDIDATE" =~ ^[a-f0-9]{64}$ ]]
podman image inspect "$H004_CANDIDATE" --format '{{.Id}} {{.Digest}}' > "$H004_TASK/candidate-image.txt"
```

Record candidate ID, native/patch identities and three changed-file hashes. Compare
all unchanged `/opt/minimax` and tool dependency hashes against the prior image
using read-only image mounts/copies or network-disabled probes. These are offline
engine checks, not native agent behavior acceptance. This overlay recipe has not
been executed in PREP; stop and report build errors rather than changing pins.

## Exact profile-skill update (required)

Existing profiles validate packaged skill bytes on every engine startup. Merely
replacing the engine would reject their old image skill. Stage the following
bounded helper as `$H004_TASK/profile-image-skill.py` in the fresh deployment
session. It changes only the exact reviewed old/new image skill; all other files,
customizations and chat state are preserved. Its default/check modes do not write.

```python
import hashlib, os, pathlib, re, stat, sys, tempfile
PROFILES = pathlib.Path('/home/user/.local/share/ai-harness/profiles')
OLD = 'c8b7c8988e7bdb2aa579522dad47b3c47aaa830016b973b6a65758988ad2e57d'
NEW = '4fb64b24bcfb7e6e3428c0df02e2b485c90213306c4e671599df75a04269b974'
if sys.flags.optimize: raise RuntimeError("Optimized Python disables required checks")
mode, source = sys.argv[1:]
assert mode in ('check-upgrade', 'upgrade', 'check-rollback', 'rollback')
want = NEW if mode.endswith('upgrade') else OLD
other = OLD if want == NEW else NEW

def read(p):
    assert p.resolve() == p
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        assert stat.S_ISREG(st.st_mode) and st.st_nlink == 1
        assert st.st_uid == os.getuid() and not st.st_mode & 0o022
        assert st.st_size < 65536
        return os.read(fd, 65536)
    finally:
        os.close(fd)

def sha(data): return hashlib.sha256(data).hexdigest()
def directory(p):
    st = p.lstat()
    assert p.resolve() == p and stat.S_ISDIR(st.st_mode)
    assert st.st_uid == os.getuid() and not st.st_mode & 0o022

content = read(pathlib.Path(source))
assert sha(content) == want
pending = []
directory(PROFILES)
for profile in sorted(PROFILES.iterdir()):
    assert re.fullmatch(r'[A-Za-z0-9_-]{1,80}', profile.name)
    directory(profile)
    target = profile / 'state/skills/image/SKILL.md'
    # Never follow a symlink, including a dangling one, or a partial skill tree.
    current = profile
    missing = False
    for part in ('state', 'skills', 'image'):
        current = current / part
        if not current.exists() and not current.is_symlink():
            missing = True
            break
        directory(current)
    if missing:
        continue  # Unseeded/older roster remains governed by existing seeding.
    old = read(target)
    assert sha(old) in (other, want), 'Custom/unreviewed skill; leave unchanged'
    if sha(old) == other:
        pending.append((target, old))
# All candidates validate before any write. Service/engines must be stopped.
if not mode.startswith('check-'):
    for target, old in pending:
        assert read(target) == old
        fd, temporary = tempfile.mkstemp(prefix='.h004-image-', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
print(mode, 'exact image skills:', len(pending))
```

Before stopping, run the dry check and retain its aggregate result privately:

```bash
python3 -I "$H004_TASK/profile-image-skill.py" check-upgrade \
  "$H004_RELEASE/ai-harness/skills/image/SKILL.md"
```

After the final backup/clean stop and before switching the engine alias, run
`upgrade` with the same source path. Re-run `check-upgrade`; it must report zero
pending files. On any mismatch/partial failure, keep the service stopped and use
the exact-hash rollback mode; never overwrite a custom skill. Before rollback,
run `check-rollback` using `$H004_OLD/ai-harness/skills/image/SKILL.md`, then run
`rollback` while stopped and require zero pending in a second check. This also
covers new profiles created after activation. A profile without an image skill
is left alone and uses the existing reviewed seeding logic. This is a bounded
application guidance update, not general profile/installer migration.

## Preserve and switch once

Before stopping, stage a unit containing only the old release path replaced by the
new release path; `systemd-analyze --user verify` must pass. Copy the old unit,
protected config directory, prior image identity and SQLite backup into a new
mode0700 rollback directory under `$H004_TASK`. Never print key contents. Use
SQLite's backup API, not a live `.sqlite` file copy. Inventory original message,
run/file identities and hashes privately; keep logs out of Git.

Concrete staging commands (after the fresh identity/storage guard and quiet-window
coordination) are:

```bash
H004_UNIT=/home/user/.config/systemd/user/ai-harness.service
H004_BACKUP=$H004_TASK/rollback-final
test ! -e "$H004_BACKUP"
mkdir -m 700 "$H004_BACKUP"
cp -a "$H004_UNIT" "$H004_BACKUP/ai-harness.service"
cp -a /home/user/.config/ai-harness "$H004_BACKUP/config"
python3 -I - "$H004_UNIT" "$H004_OLD" "$H004_RELEASE" "$H004_TASK/ai-harness.service" <<'PYUNIT'
import pathlib, sys
unit, old, new, staged = sys.argv[1:]
text = pathlib.Path(unit).read_text()
assert old in text and new not in text
text = text.replace(old, new)
assert old not in text
p = pathlib.Path(staged)
with p.open('x') as f: f.write(text)
p.chmod(0o600)
PYUNIT
systemd-analyze --user verify "$H004_TASK/ai-harness.service"
```

Take the pre-stop SQLite backup with the following exact backup API command; the
same command is repeated after the clean stop to refresh this destination from the
final idle state. Do not restore this backup during ordinary code rollback.

```bash
python3 -I - "$H004_BACKUP/harness-final-idle.sqlite" <<'PYBACKUP'
import pathlib, sqlite3, sys
source = pathlib.Path('/home/user/.local/share/ai-harness/harness.sqlite')
assert source.resolve() == source
with sqlite3.connect('file:' + str(source) + '?mode=ro', uri=True) as src:
    with sqlite3.connect(sys.argv[1]) as dst:
        src.backup(dst)
        assert dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
pathlib.Path(sys.argv[1]).chmod(0o600)
PYBACKUP
```

Immediately before stop, a minimal durable work-state gate is:

```bash
python3 -I - <<'PYIDLE'
import json, sqlite3
p = '/home/user/.local/share/ai-harness/harness.sqlite'
with sqlite3.connect('file:' + p + '?mode=ro', uri=True) as db:
    db.execute('BEGIN')
    assert db.execute("SELECT COUNT(*) FROM runs WHERE status NOT IN ('completed','cancelled','failed','interrupted')").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM sessions WHERE status NOT IN ('idle','interrupted','failed') OR (deleted=0 AND delete_requested!=0)").fetchone()[0] == 0
    lanes = dict(db.execute('SELECT alias,state FROM gateway_lanes'))
    assert lanes == {'qwen3.8-27b-gpu0': 'idle', 'qwen3.8-27b': 'idle'}
    assert list(db.execute('SELECT id,state FROM h003_image_lane')) == [(1, 'idle')]
    assert all(json.loads(r[0])['job']['state'] in ('completed','failed','cancelled','interrupted') for r in db.execute('SELECT data FROM h003_image_jobs'))
print('Durable work-state gate passed; independently verify native settlement')
PYIDLE
```

This gate cannot establish native task settlement or exclude a concurrent new
submission. The fresh owner must independently verify native settlement and the
coordinated quiet window; do not stop unknown/active work.

At the final idle/settlement gate, stop the service once. Require an ordinary clean
stop. Take a final consistent SQLite backup and copy the whole persistent data
tree. Handle the top-level `harness.sqlite` with SQLite backup; exclude its
WAL/SHM and runtime `owner.sqlite*`. Native profile databases and their sidecars
are retained together only after their engines have cleanly stopped.
Retain workspaces, profiles, uploads, artifacts, image jobs and logs; validate file
hash equality. Do not run a global prune or erase the old release/image.

```bash
H004_UNIT=/home/user/.config/systemd/user/ai-harness.service
H004_BACKUP=$H004_TASK/rollback-final
# Create this directory and verified private backups before proceeding.
test -f "$H004_BACKUP/ai-harness.service"
test -f "$H004_BACKUP/harness-final-idle.sqlite"
# The fresh operator performs the documented idle gate immediately before this stop.
systemctl --user stop ai-harness.service
# Reverify clean stop and refresh the final SQLite/data backup here while stopped.
python3 -I "$H004_TASK/profile-image-skill.py" upgrade \
  "$H004_RELEASE/ai-harness/skills/image/SKILL.md"
python3 -I "$H004_TASK/profile-image-skill.py" check-upgrade \
  "$H004_RELEASE/ai-harness/skills/image/SKILL.md"
test "$(podman image inspect "$H004_TAG" --format '{{.Id}}')" = "$H004_CANDIDATE"
podman tag "$H004_CANDIDATE" localhost/ai-harness-engine:0.0.2-ae65651df5f9
test "$(podman image inspect localhost/ai-harness-engine:0.0.2-ae65651df5f9 --format '{{.Id}}')" = "$H004_CANDIDATE"
cp "$H004_TASK/ai-harness.service" "$H004_UNIT.h004-new"
chmod 600 "$H004_UNIT.h004-new"
mv "$H004_UNIT.h004-new" "$H004_UNIT"
systemctl --user daemon-reload
systemctl --user start ai-harness.service
curl --fail --silent http://10.156.100.61/api/health
```

The required stopped-state persistent-tree copy is this command, inserted at the
refresh checkpoint above after re-running the SQLite backup command. It excludes
only SQLite files handled separately and ephemeral ownership databases. It also
preserves symlinks as symlinks instead of following them outside the data tree.

```bash
python3 -I - "$H004_BACKUP/final-data" <<'PYDATA'
import hashlib, json, os, pathlib, shutil, sys
root = pathlib.Path('/home/user/.local/share/ai-harness')
assert root.resolve() == root
dest = pathlib.Path(sys.argv[1]); dest.mkdir(mode=0o700)
for p in root.iterdir():
    if p.name.startswith(('harness.sqlite', 'owner.sqlite')): continue
    out = dest / p.name
    if p.is_dir() and not p.is_symlink(): shutil.copytree(p, out, symlinks=True)
    else: shutil.copy2(p, out, follow_symlinks=False)
def manifest(base):
    result = {}
    for directory, dirs, files in os.walk(base, followlinks=False):
        for name in sorted(dirs + files):
            p = pathlib.Path(directory) / name
            st = p.lstat()
            row = {'mode': st.st_mode & 0o777}
            if p.is_symlink(): row['link'] = os.readlink(p)
            elif p.is_file():
                h = hashlib.sha256()
                with p.open('rb') as f:
                    for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
                row['sha256'] = h.hexdigest()
            elif p.is_dir(): row['directory'] = True
            else: raise RuntimeError('Unexpected special file in backup')
            result[str(p.relative_to(base))] = row
    return result
saved = manifest(dest)
original = {k: v for k, v in manifest(root).items()
            if not k.split('/')[0].startswith(('harness.sqlite', 'owner.sqlite'))}
assert original == saved
receipt = dest.parent / 'final-data-manifest.private.json'
receipt.write_text(json.dumps(saved, sort_keys=True)); receipt.chmod(0o600)
print('Private persistent-tree backup and manifest equality passed')
PYDATA
```

Do not execute this block blindly: its explicit backup/idle checkpoints are
required. A failure before the new service starts may restore the old pair; after
new traffic starts, preserve new data and coordinate rollback. Never roll back
SQLite automatically.

## Acceptance and rollback

Verify service PID/cwd/argv point to the approved release, no restart loop,
listeners remain nginx10.156.100.61:80 and loopback8080/8081, credentials/config
unchanged, history/file hashes and counts preserved. In a read-only browser open
only the authorized newest conversation: ten saved image references should render
at their authored narrative positions, separately from trays; ZIP links should be
reachable near final heading and file-list end. Download an existing reply ZIP
and compare entry names/content to its owned catalog privately. Confirm tables
at desktop and narrow widths; no UI-only image generation. Use fixture evidence
for malicious refs and upload combinations; any fresh agent acceptance needs its
own explicitly bounded root grant. The guidance-only behavior remains unproven
until that separately authorized test.

For rollback in a fresh quiet/settled window, preserve all post-activation history,
then restore only the recorded prior unit and retained engine alias:

```bash
systemctl --user stop ai-harness.service
python3 -I "$H004_TASK/profile-image-skill.py" rollback \
  "$H004_OLD/ai-harness/skills/image/SKILL.md"
python3 -I "$H004_TASK/profile-image-skill.py" check-rollback \
  "$H004_OLD/ai-harness/skills/image/SKILL.md"
cp "$H004_BACKUP/ai-harness.service" "$H004_UNIT.h004-old"
chmod 600 "$H004_UNIT.h004-old"
mv "$H004_UNIT.h004-old" "$H004_UNIT"
podman tag "$H004_ENGINE" localhost/ai-harness-engine:0.0.2-ae65651df5f9
systemctl --user daemon-reload
systemctl --user start ai-harness.service
curl --fail --silent http://10.156.100.61/api/health
```

Keep H004 additive companion metadata; old code ignores it. Do not restore
`owner.sqlite`, delete chats/files, or revert the whole data directory. A database
restore is a separate destructive recovery action requiring exact scope review.
Rollback and live acceptance are NOT_TESTED in this source session.
