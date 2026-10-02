"""Focused source-only checks against actual installed public descriptor values."""
import copy
import datetime
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_image_owner_successor as prior
m, core = prior.m, prior.core
FIXTURE = Path(__file__).resolve().parents[2]/'output/mutable-discovery06.json'


def actual_values():
    packet = json.loads(FIXTURE.read_text())
    values = {p:copy.deepcopy(v['value']) for p,v in packet['descriptors'].items()}
    guard = values[m.GUARD_PATH]
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    guard['observed_at'] = stamp
    guard['sample']['hardware_validation']['observed_at'] = stamp
    guard['hardware_proof']['hardware_validation_age_ms'] = 0
    return values


class MutableChecks(unittest.TestCase):
    setUp = prior.ArchiveTests.setUp

    def descriptor(self, public_path, value):
        path = self.fixture.path/('latch.json' if public_path == m.LATCH_PATH else 'guard.json')
        path.write_bytes(core.encode(value)); path.chmod(0o600)
        s = path.stat(); parent = path.parent.stat()
        binding = {'path':public_path,'protectedMetadata':list(core.signature(s))[2:6],
            'parentIdentity':[parent.st_dev,parent.st_ino,parent.st_mode,parent.st_uid,parent.st_gid],
            'temperatureLimitC':85 if public_path == m.GUARD_PATH else None,
            'semantic':m.mutable_semantic(public_path,path.read_bytes())}
        audit = []
        return path,m.MutableDescriptor(str(path),binding,audit=audit.append,
            trusted_uid=os.getuid(),fixture_root=self.fixture.path),audit

    def test_actual_background_updates_and_atomic_replacements_between_reads(self):
        for public_path,value in actual_values().items():
            with self.subTest(path=public_path):
                path,descriptor,audit = self.descriptor(public_path,value)
                descriptor.read(); first_inode = path.stat().st_ino
                for i in range(8):
                    changed = copy.deepcopy(value)
                    if public_path == m.LATCH_PATH:
                        proof = changed['validated'][core.READING_GPU]
                        proof['observed_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        proof['observation_id'] = ('a' if i%2 else 'b')*32
                    else:
                        changed['observed_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        changed['observed_monotonic_s'] += i
                        changed['sample']['gpus'][0]['free_mib'] -= i
                        changed['sample']['gpus'][0]['temp_c'] += i
                        changed['sample']['host']['MemAvailable'] -= i
                        changed['sample']['cgroup']['memory.current'] = str(int(changed['sample']['cgroup']['memory.current'])-i)
                        changed['proxy_disposition']['active_requests'] = i%2
                        changed['hardware_proof']['hardware_validation_age_ms'] = i
                    replacement = path.with_suffix('.next'); replacement.write_bytes(core.encode(changed)); replacement.chmod(0o600)
                    os.replace(replacement,path)
                    raw = path.read_bytes(); self.assertEqual(descriptor.read(),raw); self.assertEqual(path.read_bytes(),raw)
                self.assertEqual(len(audit),9)
                self.assertNotEqual(audit[1]['identity'][1],first_inode)
                self.assertTrue(all(v['classification'].endswith('NOT_HARDWARE_PROOF') for v in audit))

    def test_latch_selected_target_pending_fault_history_boot_and_gpu_refused(self):
        value = actual_values()[m.LATCH_PATH]; baseline = m.mutable_semantic(m.LATCH_PATH,core.encode(value))
        from control.hardware_latch import HardwareLatch
        receipt = {'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'observation_id':'c'*32}
        record = {'boot_id':core.OLD_BOOT,'hardware_latched':True,'reason':'hardware_fault',
            'hardware_fault_code':'gpu_fallen_off_bus','evidence':[receipt]}
        cases=[]
        for gpu in (core.EXTERNAL_GPU,core.READING_GPU):
            changed=copy.deepcopy(value);changed['targets'][gpu]=record;cases.append(changed)
        changed=copy.deepcopy(value);changed['validated'][core.READING_GPU]['boot_id']=core.OLD_BOOT;cases.append(changed)
        changed=copy.deepcopy(value);changed['validated'].pop(core.READING_GPU);cases.append(changed)
        changed=copy.deepcopy(value);changed['validated'][core.EXTERNAL_GPU]['observation_id']='d'*32;cases.append(changed)
        for changed in cases:
            try: result=m.mutable_semantic(m.LATCH_PATH,core.encode(changed))
            except core.Refused:continue
            self.assertNotEqual(result,baseline)
        # Existing unrelated history remains frozen through a healthy annotation update.
        with_history=copy.deepcopy(value);with_history['targets'][core.READING_GPU]=copy.deepcopy(record)
        with_history['targets'][core.READING_GPU]['pending']={'boot_id':core.BOOT,'hardware_latched':False,
            'reason':'hardware_missing','hardware_fault_code':None,'evidence':[receipt]}
        baseline=m.mutable_semantic(m.LATCH_PATH,core.encode(with_history))
        changed=copy.deepcopy(with_history);changed['targets'][core.READING_GPU]['pending']['evidence'][0]['observation_id']='e'*32
        self.assertNotEqual(m.mutable_semantic(m.LATCH_PATH,core.encode(changed)),baseline)
        for target in (record,with_history['targets'][core.READING_GPU],with_history['targets'][core.READING_GPU]['pending']):
            changed=copy.deepcopy(value);changed['targets'][core.EXTERNAL_GPU]=target
            with self.assertRaisesRegex(core.Refused,'must_not_clear'):m.mutable_semantic(m.LATCH_PATH,core.encode(changed))

    def test_guard_owner_boot_source_device_fault_capacity_schema_and_stale_refused(self):
        value=actual_values()[m.GUARD_PATH];path,descriptor,audit=self.descriptor(m.GUARD_PATH,value)
        changes=[('status','failed'),('boot_id',core.OLD_BOOT),('manifest_sha256','0'*64),('hardware_latched',True)]
        for key,new in changes:
            changed=copy.deepcopy(value);changed[key]=new;path.write_bytes(core.encode(changed))
            with self.assertRaises(core.Refused):descriptor.read()
        for branch,key,new in [('native','pid',429393),('supervisor','pid',1),('selection','generation',14),
            ('proxy','pid',2),('hardware_proof','reason','hardware_fault')]:
            changed=copy.deepcopy(value);changed[branch][key]=new;path.write_bytes(core.encode(changed))
            with self.assertRaises(core.Refused):descriptor.read()
        cases=[]
        for branch,key,new in [('gpus','free_mib',0),('gpus','temp_c',150),('host','MemAvailable',0),('cgroup','memory.current',str(2**50))]:
            changed=copy.deepcopy(value)
            item=changed['sample'][branch][0] if branch == 'gpus' else changed['sample'][branch]
            item[key]=new;cases.append(changed)
        for invalid in (2,0.5):
            changed=copy.deepcopy(value);changed['proxy_disposition']['active_requests']=invalid;cases.append(changed)
        changed=copy.deepcopy(value);changed['sample']['gpus'][0]['uuid']=core.EXTERNAL_GPU;cases.append(changed)
        changed=copy.deepcopy(value);changed['sample']['gpus'][0]['total_mib']+=1;cases.append(changed)
        changed=copy.deepcopy(value);changed['sample']['cgroup']['memory.events']['oom']='1';cases.append(changed)
        changed=copy.deepcopy(value);changed['proxy_disposition']['quarantined']=True;cases.append(changed)
        changed=copy.deepcopy(value);changed['observed_at']='2020-01-01T00:00:00+00:00';cases.append(changed)
        changed=copy.deepcopy(value);changed['new_history']={'keep':True};cases.append(changed)
        for changed in cases:
            path.write_bytes(core.encode(changed))
            with self.assertRaises(core.Refused):descriptor.read()
        self.assertEqual(len(audit),len(changes)+5+len(cases))
        self.assertTrue(all(v['semanticAcceptance'] == 'NOT_EVALUATED' for v in audit))

    def test_protected_parent_mode_link_and_during_read_race_refused(self):
        value=actual_values()[m.LATCH_PATH];path,descriptor,audit=self.descriptor(m.LATCH_PATH,value)
        path.chmod(0o640)
        with self.assertRaises(core.Refused):descriptor.read()
        path.chmod(0o600);os.link(path,path.with_suffix('.link'))
        with self.assertRaises(core.Refused):descriptor.read()
        path.with_suffix('.link').unlink()
        with patch.object(m.os,'pread',return_value=b'{}'):
            with self.assertRaisesRegex(core.Refused,'read_race'):descriptor.read()
        old=descriptor.binding['parentIdentity'][1];descriptor.binding['parentIdentity'][1]=old+1
        with self.assertRaisesRegex(core.Refused,'parent'):descriptor.read()
        self.assertEqual(audit,[])

    def test_static_source_config_and_archive_closures_remain_exact(self):
        import image_executor as executor
        packet=json.loads((Path(__file__).resolve().parents[2]/'output/canonical-current.json').read_text())
        binding=executor.canonical_storage_binding(packet)
        raws={p:v['text'].encode() for p,v in packet['sources'].items()}
        executor.validate_storage_binding(binding,raws)
        for path in raws:
            changed=dict(raws);changed[path]+=b'\n# changed source\n'
            with self.subTest(source=path),self.assertRaises(ValueError):executor.validate_storage_binding(binding,changed)
        changed=copy.deepcopy(binding);changed['registration']['roots']['logs']='/data/other'
        with self.assertRaises(ValueError):executor.validate_storage_binding(changed,raws)

    def test_during_read_write_restore_is_not_a_stable_snapshot(self):
        value=actual_values()[m.LATCH_PATH];path,descriptor,audit=self.descriptor(m.LATCH_PATH,value)
        original=path.read_bytes();pread=os.pread
        def race(fd,size,offset):
            raw=pread(fd,size,offset)
            path.write_bytes(b'{}');path.write_bytes(original)
            return raw
        with patch.object(m.os,'pread',side_effect=race):
            with self.assertRaises(core.Refused):descriptor.read()
        self.assertEqual(path.read_bytes(),original);self.assertEqual(audit,[])

    def test_exact_mutable_writer_source_metadata_and_descriptor_sets_required(self):
        go,now=prior.ControlTests().go()
        m.validate_go(go,'a'*64,now)
        mutations=[lambda v:v['mutableSourceSha256'].update({next(iter(m.MUTABLE_SOURCE_SHA)):'0'*64}),
            lambda v:v['peerFileSha256'].update({m.GUARD_PATH:'0'*64}),
            lambda v:v['mutableDescriptorBinding'].pop(m.LATCH_PATH),
            lambda v:v['mutableDescriptorBinding'][m.GUARD_PATH]['protectedMetadata'].__setitem__(0,0o100644)]
        for mutate in mutations:
            changed=copy.deepcopy(go);mutate(changed)
            with self.assertRaises(core.Refused):m.validate_go(changed,'a'*64,now)



if __name__ == '__main__':unittest.main()
