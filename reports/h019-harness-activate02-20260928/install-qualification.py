"""Install root-reviewed nonsecret receipt once, preserving original bytes privately."""
import datetime, hashlib, json, os, pathlib, stat

os.umask(0o077)
assert os.getuid() == 0
sha = lambda b: hashlib.sha256(b).hexdigest()
source = pathlib.Path('/home/user/ai-harness-build/H019-HARNESS-PREP01-20260928/private/QUALIFICATION-950K.json')
target = pathlib.Path('/etc/sova-qualification/mimo.json')
expected = '05ad0301dc7b7d614f0400747812079a02c7f4163c506d774d8c7b944d61e83a'
for p in [target, *target.parents]:
    s = p.lstat()
    assert p.resolve() == p and s.st_uid == 0 and not s.st_mode & 0o022
    assert stat.S_ISREG(s.st_mode) and s.st_nlink == 1 if p == target else stat.S_ISDIR(s.st_mode)
assert stat.S_IMODE(target.parent.stat().st_mode) == 0o755
assert stat.S_IMODE(pathlib.Path('/etc/ai-harness').stat().st_mode) == 0o700
incoming = source.read_bytes()
assert len(incoming) <= 65536 and sha(incoming) == expected
q = json.loads(incoming)
assert all(q[k] is True for k in ['full17ToolRosterQualified', 'strictNestedSchemasQualified', 'serialCompletionQualified'])
assert q['capacity'] == dict(published=1048576, configured=950000, allocated=950000, occupiedTested=9635)
assert q['qualification']['checks']['generationCeiling']['largestCompletedOutputTokens'] == 70
old = target.read_bytes()
assert sha(old) != expected, 'already installed; inspect instead of replay'
history = target.parent/'history'
history.mkdir(mode=0o700, exist_ok=True)
hs = history.lstat()
assert history.resolve() == history and stat.S_ISDIR(hs.st_mode) and hs.st_uid == 0 and stat.S_IMODE(hs.st_mode) == 0o700
backup = history/('h019-activate02-original-' + sha(old) + '.json')
with backup.open('xb') as f:
    f.write(old); f.flush(); os.fsync(f.fileno())
temporary = target.with_name('mimo.json.h019-activate02-new')
with temporary.open('xb') as f:
    f.write(incoming); f.flush(); os.fsync(f.fileno())
os.chown(temporary, 0, 0); os.chmod(temporary, 0o644)
assert target.read_bytes() == old
os.replace(temporary, target)
fd = os.open(target.parent, os.O_DIRECTORY); os.fsync(fd); os.close(fd)
assert target.read_bytes() == incoming and backup.read_bytes() == old
print(json.dumps({'status':'INSTALLED_EXACT_ROOT_RECEIPT','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'sha256':expected, 'bytes':len(incoming), 'originalSha256':sha(old), 'privateBackup':str(backup), 'owner':'root:root','mode':'0644','parentMode':'0755','etcAiHarnessMode':'0700'}, indent=2))
