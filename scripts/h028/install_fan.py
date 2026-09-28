"""H028 reviewed exact UUID extension; run once as root after source review."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,importlib.util
NEW='GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf'
OLD='47adea43b4c404ab325b2470ca0a701ab825dfd079f2c6e6f6edf258f8c6bfb3'
STAGE=Path('/data/services/h028-fan-20260929')
SOURCE=Path('/usr/local/lib/local-ai-fan-boost/fan_boost.py')
CONFIG=Path('/etc/local-ai-server/fan-boost.json')
STATE=Path('/var/lib/local-ai-fan-boost/ownership.json')
def run():
    assert os.geteuid()==0
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==OLD
    incoming=(STAGE/'fan_boost.py').read_bytes()
    assert incoming==SOURCE.read_bytes().replace(b'KNOWN = {\n',b'KNOWN = {\n    "GPU-14c23cbc-12f0-9c61-0fda-7aaf80fbd1bf": "Ada-Qwen200K",\n')
    conf=json.loads(CONFIG.read_text()); assert NEW not in conf['devices']
    assert set(conf['devices'])=={'GPU-88058d9d-08e5-cb1e-a77a-04cbc1488237','GPU-69acfa26-8b60-61b5-702d-aee252c163cc','GPU-5d895991-b794-2b4c-b9c4-5f1b668afd23','GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528'}
    backup=STAGE/'before';backup.mkdir(mode=0o700)
    for p in [SOURCE,CONFIG,STATE]:shutil.copy2(p,backup/p.name)
    subprocess.run(['systemctl','stop','local-ai-fan-boost.service'],check=True,timeout=20)
    state=json.loads(STATE.read_text());assert state['owner']=='h013-nvml-fan-boost-v1' and state['version']==1
    assert set(state['owned'])==set(conf['devices'])-{'GPU-93dbfca8-ef3a-9628-a798-6a4afd0af528'}
    assert all(type(v) is bool for v in state['owned'].values())
    shutil.copy2(STATE,backup/'ownership-after-stop.json')
    state['owned'][NEW]=False;conf['devices'].insert(0,NEW)
    for p,data,mode in [(SOURCE,incoming,0o644),(CONFIG,(json.dumps(conf,indent=2)+'\n').encode(),0o644),(STATE,(json.dumps(state,sort_keys=True)+'\n').encode(),0o600)]:
        tmp=p.with_name(p.name+'.h028-new');fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,mode)
        with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,p)
    subprocess.run(['systemctl','start','local-ai-fan-boost.service'],check=True,timeout=20)
    print(json.dumps({'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'config':conf,'ownership':state,'backup':str(backup)}))
    subprocess.run(['python3',str(SOURCE),'capabilities'],check=True,timeout=15)
if __name__=='__main__':run()
