# Worker-only copied-stat reproduction

Executed results are in the adjacent two metadata JSON files. The original commands
ran inline; no production script changed. The following equivalent replay uses a
new directory and includes the helper Git options consistently. Original initial
Git init/add/commit/diff/restore/refresh used ordinary Git; the recorded confirmation
checks used the exact helper options/environment below. Replay block is documented,
not claimed additionally executed. Apple Git 2.54.0; no Linux/Docker qualification.

```sh
python3 - <<'PYTHON'
from pathlib import Path
import os, shutil, subprocess
r = Path('../d3b-git-stat-repro-replay').resolve()
r.mkdir()  # Refuse reuse; preserve prior evidence.
base = r / 'original'
base.mkdir()
env = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
env.update(GIT_AUTHOR_NAME='CodexAIagent',
           GIT_AUTHOR_EMAIL='133749519+djeZo888@users.noreply.github.com',
           GIT_COMMITTER_NAME='CodexAIagent',
           GIT_COMMITTER_EMAIL='133749519+djeZo888@users.noreply.github.com')
def g(where, *args):
    return subprocess.run(['git', '-c', 'core.fsmonitor=false',
        '-c', 'core.untrackedCache=false', '-C', str(where), *args],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
def ok(where, *args):
    p = g(where, *args)
    assert p.returncode == 0, (args, p.returncode)
    return p.stdout
ok(base, 'init', '-q')
(base/'tiny.txt').write_text('alpha\nbeta\ngamma\n')
ok(base, 'add', 'tiny.txt')
ok(base, 'commit', '-qm', 'Stat cache fixture')
(base/'tiny.txt').write_text('alpha\nbeta revised\ngamma\n')
patch = r/'tiny.patch'
patch.write_bytes(ok(base, 'diff', '--binary', '--', 'tiny.txt'))
ok(base, 'restore', 'tiny.txt')
ok(base, 'update-index', '--refresh')
copied = r/'exact-helper-git-env'
shutil.copytree(base, copied, copy_function=shutil.copyfile)
env.update(GIT_OPTIONAL_LOCKS='0', GIT_NO_REPLACE_OBJECTS='1')
assert ok(copied, 'status', '--porcelain=v1', '--untracked-files=all',
          '--ignored=matching') == b''
ok(copied, 'diff-index', '--cached', '--quiet', 'HEAD', '--')
assert (copied/'tiny.txt').read_bytes() == (base/'tiny.txt').read_bytes()
tree_before = ok(copied, 'write-tree')
index_before = (copied/'.git/index').read_bytes()
apply_args = ('apply', '--check', '--index', '--whitespace=error-all', str(patch))
assert g(copied, *apply_args).returncode == 1
ok(copied, 'update-index', '--refresh')
assert (copied/'.git/index').read_bytes() != index_before
assert ok(copied, 'write-tree') == tree_before
ok(copied, *apply_args)
assert (copied/'tiny.txt').read_bytes() == (base/'tiny.txt').read_bytes()
negative = r/'dirty-control'
shutil.copytree(base, negative, copy_function=shutil.copyfile)
(negative/'tiny.txt').write_text('CHANGED\n')
assert g(negative, 'update-index', '--refresh').returncode == 1
assert g(negative, *apply_args).returncode == 1
print('PASS_STAT_REPRO_AND_CHANGED_BYTE_REFUSAL')
PYTHON
```
