"""Use the existing installed runtime and canonical storage/lease contracts unchanged."""
import contextlib,hashlib,importlib.util,json,os,pathlib,subprocess,time
BASE=pathlib.Path('/data/services/image21-reference-20260923')
BUILD=pathlib.Path('/data/build/IMAGE21-REFERENCE-20260923')
TASK='IMAGE21-REFERENCE-20260923'
SESSION='01a0cc4b-c378-7880-b15f-0ca5886bc4a9'
p=pathlib.Path('/data/services/image21-runtime-20260923/source/service.py')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='0edadcb43ec83d369d7bdb66dddc7035962d620475314b0142cb9f047b197586'
spec=importlib.util.spec_from_file_location('installed_runtime',p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
r=m.Runtime()
assert hashlib.sha256((m.BASE/'config.json').read_bytes()).hexdigest()=='4ded6e9261b512d952c5033b0634d4eaba79fa115685635c6307defe78c11d76'
@contextlib.contextmanager
def anchor(path):
 with r.binding.mounted_guard(m.storage_io) as guard:
  with m.storage_io.AnchoredRoot(str(path),guard) as a:yield a

def qwens():
 ids=['a2afad49380a592739944f2766f5547687a5cf302badd375bda14fffdb09f75c','a71924b9e7fa4f72c6eeefc243731f59bdc0d951b817de1d32f32dbfd67f450e']
 values=json.loads(m.run(['docker','inspect',*ids]).stdout)
 assert all(x['State']['Running'] for x in values)
 return [{'id':x['Id'],'started_at':x['State']['StartedAt'],'pid':x['State']['Pid']} for x in values]
