#!/usr/bin/env python3
"""One-time reviewed H028 CAS: extend the existing protected owner to Ada30014.

Run only from protected staged delivery. Old receipt/filter/source are archived
before mutation; existing twelve unit bytes and chain rules remain unchanged.
"""
import hashlib, importlib.util, json, os, pathlib, subprocess, time
P=pathlib.Path
STAGE=P('/etc/llm-server/h028-finalize-stage')
BACKUP=P('/etc/llm-server/h028-network-predecessor-20260929')
HELPER=P('/usr/local/lib/llm-server/private-network/private_network.py')
OLD='bb5d6731e0c1374d67e8773cc29d42e6ada064db8224c5593d62d207b574da7e'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def atomic(path,raw,mode):
    tmp=path.with_name(path.name+'.h028-new')
    fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
def command(*args):subprocess.run(args,check=True,timeout=60)
def main():
    assert os.geteuid()==0 and sha(HELPER.read_bytes())==OLD
    old=load('h028_old_network',HELPER)
    pins=json.loads(old._protected(STAGE/'pins.json',0o600))
    files={name:old._protected(STAGE/name,0o644) for name in pins}
    assert all(sha(files[n])==h for n,h in pins.items())
    old.operate('check')
    command('systemctl','stop','llm-private-network-rearm.timer')
    # Do not kill an owner midway through an ingress transaction.
    assert subprocess.check_output(['systemctl','show','llm-private-network-rearm.service','-p','ActiveState','--value'],text=True).strip() in ('inactive','failed')
    with old._lock():
        signature=old._installation();receipt=old._state(signature)
        original_filter=old._snapshot();assert old._inspect(original_filter)[0]=='complete'
        old._interface()
        assert receipt is not None
        for suffix in ('socket','service'):
            assert not os.path.lexists('/etc/systemd/system/llm-private-ada200k.'+suffix)
        old_unit_hashes={n:sha((old.UNIT_DIR/n).read_bytes()) for n in old.expected_units()}
        original={str(HELPER):old._protected(HELPER,0o644),str(old.POLICY):old._protected(old.POLICY,0o600),str(old.STATE):old._protected(old.STATE,0o600)}
        # Exact archive is create-only and retains predecessor ownership evidence.
        BACKUP.mkdir(mode=0o700)
        for path,raw in original.items():(BACKUP/P(path).name).write_bytes(raw);os.chmod(BACKUP/P(path).name,0o600)
        (BACKUP/'filter.txt').write_text(original_filter);os.chmod(BACKUP/'filter.txt',0o600)
        for n in old.expected_units():(BACKUP/n).write_bytes((old.UNIT_DIR/n).read_bytes())
        (BACKUP/'manifest.json').write_text(json.dumps({'files':{p:sha(v) for p,v in original.items()},'units':old_unit_hashes,'filter':sha(original_filter.encode()),'successor':pins},indent=2)+'\n')
        for path,raw in original.items():assert P(path).read_bytes()==raw
        assert old._snapshot()==original_filter
        for n in ('llm-private-ada200k.socket','llm-private-ada200k.service'):
            atomic(old.UNIT_DIR/n,files[n],0o644)
        atomic(HELPER,files['private_network.py'],0o644)
        atomic(old.POLICY,files['ai-vm-private-api.json'],0o600)
        for n in ('private_network_rearm.py',):atomic(HELPER.parent/n,files[n],0o644)
        for n in ('llm-private-network-rearm.service','llm-private-network-rearm.timer'):atomic(old.UNIT_DIR/n,files[n],0o644)
        command('systemctl','daemon-reload')
        new=load('h028_new_network',HELPER)
        successor_signature=new._installation()
        # One atomic rule replacement extends only the dport match. No flush or
        # unprotected gap; same exact loopback/LAN/interface/terminal DROP chain.
        assert old._snapshot()==original_filter
        new._ipt('-R','INPUT','1',*new._rules()[0])
        assert new._inspect(new._snapshot())[0]=='complete'
        assert old.STATE.read_bytes()==original[str(old.STATE)]
        successor={**receipt,'signature':successor_signature}
        atomic(old.STATE,(json.dumps(successor,sort_keys=True,indent=2)+'\n').encode(),0o600)
        assert all(sha((old.UNIT_DIR/n).read_bytes())==h for n,h in old_unit_hashes.items())
    print(new.operate('check'),flush=True)
    command('systemd-analyze','verify','--man=no','/etc/systemd/system/llm-private-ada200k.socket','/etc/systemd/system/llm-private-ada200k.service','/etc/systemd/system/llm-private-network-rearm.service','/etc/systemd/system/llm-private-network-rearm.timer')
    command('systemctl','enable','--now','llm-private-ada200k.socket')
    command('systemctl','start','llm-private-network-rearm.timer')
    print(json.dumps({'old_helper':OLD,'successor':pins,'old_12_units_unchanged':True,'original_receipt_sha256':sha(original[str(old.STATE)]),'successor_receipt_sha256':sha(old.STATE.read_bytes()),'backup':str(BACKUP)}),flush=True)
if __name__=='__main__':main()
