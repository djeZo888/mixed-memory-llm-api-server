"""H016 passive owner/guard/native fixtures. No AI-server or inference access."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from control import node_observation as n
from control.node import NodeStatus, SERVICES
from tests.test_node_projection import Cached, sample

BOOT = '37e425eb-3d3e-4070-80a0-5ecfb39604f1'
NATIVE = dict(container_id='a'*64, name='llm-frontier-mimo-production', image_id=n.MIMO_IMAGE, pid=1234,
              pid_start_ticks='5678', started_at='2026-09-27T11:00:00Z')
SUPERVISOR = dict(unit=n.UNITS['mimo'], pid=4321, invocation_id='b'*32)
PROXY = dict(pid=4322, pid_start_ticks='8765', parent_pid=4321)
TEMPLATE = (Path(__file__).resolve().parents[1] / 'reports/h014-mimo-selection-20260927/sources/pro-chat_template.jinja').read_text()[:-1]
MANIFEST = dict(schema_version=2, owner=n.MIMO_OWNER, service_id=n.MIMO, qualified=True,
    container_name=NATIVE['name'], image_id=n.MIMO_IMAGE, required_gpu_uuids=list(SERVICES[n.MIMO]),
    model_revision=n.MIMO_REVISION,
    context=131072, parallel=1, slot_id=0, build_info=n.MIMO_BUILD,
    model_path=n.MIMO_MODEL_PATH, template_sha256=hashlib.sha256(TEMPLATE.encode()).hexdigest())
PROPS = dict(model_alias=n.MIMO, is_sleeping=False, build_info=MANIFEST['build_info'],
    model_path=MANIFEST['model_path'], chat_template=TEMPLATE, total_slots=1,
    default_generation_settings=dict(n_ctx=131072), modalities=dict(vision=False,video=False,audio=False))
SLOTS = [dict(id=0, n_ctx=131072, is_processing=False, speculative=False)]


class MimoObservationTests(unittest.TestCase):
    def setUp(self):
        self.clock = 100.
        self.calls = []
        self.manifest = copy.deepcopy(MANIFEST)
        digest = n.canonical_sha256(self.manifest)
        selected = dict(schema_version=1, selected_frontier=n.MIMO, generation=1, manifest_sha256=digest)
        disposition = dict(schema_version=2, boot_id=BOOT, native=NATIVE, launch_id='d'*32,
                           **PROXY, active_requests=0, quarantined=False)
        self.docs = {
            'selection.json': selected,
            'manifest.json': self.manifest,
            'state.json': dict(schema_version=2, status='RUNNING', manifest_sha256=digest,
                boot_id=BOOT, supervisor=SUPERVISOR, native=NATIVE, proxy=PROXY,
                launch_id='d'*32, selection=copy.deepcopy(selected)),
            'guard.json': dict(schema_version=2, status='ok', boot_id=BOOT,
                manifest_sha256=digest, supervisor=SUPERVISOR, proxy=PROXY, native=NATIVE,
                selection=copy.deepcopy(selected), proxy_disposition=disposition,
                observed_monotonic_s=99., hardware_latched=False),
        }
        binding = SimpleNamespace(path=lambda *args: '/data/services/secrets/llm-api-key',
            validate_path=lambda *args: None,
            read_json=lambda role, path: copy.deepcopy(self.docs[Path(path).name]))
        self.latch = dict(hardware_latched=False, hardware_validation_age_ms=0,
            hardware_validated_boot_id=BOOT, hardware_validated_gpu_uuids=list(SERVICES[n.MIMO]),
            identity=[[SERVICES[n.MIMO][0], BOOT, 'validated']])
        self.reader = n.CanonicalIdentityReader(run=self.run_command, boot=lambda:dict(boot_id=BOOT),
            binding=lambda _:binding, latch=lambda *_:dict(self.latch),
            read=lambda *args, **kwargs:b'fixture-protected-key-123456789012345', clock=lambda:self.clock)

    def run_command(self, args, seconds):
        self.calls.append(args)
        if args[0] == '/usr/bin/cat':
            if '/4322/' in args[1]:
                return '4322 (proxy) ' + ' '.join(['S','4321'] + ['0']*17 + ['8765'])
            return '1234 (native process) ' + ' '.join(['S'] + ['0']*18 + ['5678'])
        if args[0] == '/usr/bin/systemctl':
            identity = SUPERVISOR
            return '\n'.join([f"Id={identity['unit']}", 'ActiveState=active', 'SubState=running',
                f"MainPID={identity['pid']}", f"InvocationID={identity['invocation_id']}"])
        return json.dumps([NATIVE['container_id'], '/' + NATIVE['name'], n.MIMO_IMAGE,
            True, NATIVE['started_at'], NATIVE['pid'], n.MIMO_OWNER, n.canonical_sha256(self.manifest), 'd'*32])

    def collect(self, *, props=None, slots=None):
        def get(port, path, key, seconds):
            self.assertEqual(port,30012)
            self.assertIn(path, ('/props','/slots'))
            return 200, copy.deepcopy((PROPS if props is None else props) if path == '/props'
                                     else (SLOTS if slots is None else slots))
        return n.PassiveServiceCollector(n.MIMO,self.reader,get=get,clock=lambda:self.clock)(2)

    def test_qualified_guarded_same_native_has_actual_capacity_not_idle_claim(self):
        row=self.collect()
        self.assertTrue(row['ownership_valid']); self.assertTrue(row['ready'])
        self.assertIsNone(row['admitting']); self.assertEqual(row['activity'],'unknown')
        self.assertEqual(row['configured_context_tokens'],131072)
        self.assertNotIn('.Config.Env',str(self.calls))
        snapshot=NodeStatus(Cached({'boot':sample(dict(boot_id=BOOT)), n.MIMO:sample(row)})).snapshot()
        public=next(x for x in snapshot['services'] if x['service_id']==n.MIMO)
        self.assertEqual(public['availability'],'available')
        self.assertEqual(public['state'],'ok'); self.assertEqual(public['freshness'],'fresh')
        self.assertEqual(public['required_gpu_uuids'], list(SERVICES[n.MIMO]))
        self.assertNotIn('fixture-protected-key',json.dumps(snapshot))

    def test_slot_busy_does_not_make_model_unready_or_claim_gpu_activity(self):
        row=self.collect(slots=[{**SLOTS[0], 'is_processing':True}])
        self.assertTrue(row['ready']); self.assertEqual(row['activity'],'unknown')
        self.assertIsNone(row['admitting'])

    def test_native_context_slot_template_or_alias_mismatch_holds_frontier(self):
        for props,slots in [({**PROPS,'model_alias':'glm-5.3-flash'},SLOTS),
            ({**PROPS,'chat_template':TEMPLATE+'\n'},SLOTS),
            ({**PROPS,'total_slots':True},SLOTS),
            (PROPS,[{**SLOTS[0],'n_ctx':65536}]),(PROPS,[]),
            (PROPS,[{**SLOTS[0],'id':1}])]:
            row=self.collect(props=props,slots=slots)
            self.assertIsNone(row['ready']); self.assertIsNone(row['configured_context_tokens'])

    def test_missing_unqualified_wrong_boot_stale_or_unowned_never_ready(self):
        for doc,field,bad in [('manifest.json','qualified',False),
            ('state.json','status','LOADING'),('guard.json','observed_monotonic_s',84.9),
            ('guard.json','observed_monotonic_s',101.),('guard.json','hardware_latched',None),
            ('state.json','boot_id','00000000-0000-0000-0000-000000000001')]:
            original=self.docs[doc][field];self.docs[doc][field]=bad
            self.assertIsNot(self.collect()['ready'],True,(doc,field))
            self.docs[doc][field]=original
        del self.docs['manifest.json']
        self.assertIsNot(self.collect()['ready'],True)

    def test_quarantine_survives_idle_slots_without_native_probe(self):
        self.docs['guard.json']['proxy_disposition'].update(quarantined=True)
        collector=n.PassiveServiceCollector(n.MIMO,self.reader,
            get=lambda *_:self.fail('quarantine must not query readiness'),clock=lambda:self.clock)
        row=collector(2)
        self.assertFalse(row['ready']); self.assertEqual(row['reason'],'software_quarantine')

    def test_selected_rollback_does_not_claim_mimo_readiness_or_absence(self):
        self.docs['selection.json']['selected_frontier']='glm-5.3-flash'
        row=self.collect()
        self.assertFalse(row['ready']);self.assertIsNone(row['running'])
        self.assertIsNone(row.get('configured_context_tokens'))

    def test_cached_guard_cannot_outlive_15_second_freshness_budget(self):
        row=self.collect();row['guard_age_ms']=14000
        snap=NodeStatus(Cached({'boot':sample(dict(boot_id=BOOT)),
            n.MIMO:sample(row,age_ms=2000)})).snapshot()
        row=next(x for x in snap['services'] if x['service_id']==n.MIMO)
        self.assertIsNone(row['ready']);self.assertEqual(row['availability'],'unknown')

    def test_unchanged_generation_excludes_guard_heartbeat(self):
        first=self.reader.service(n.MIMO)['generation']
        self.docs['guard.json']['observed_monotonic_s']=100.
        self.assertEqual(self.reader.service(n.MIMO)['generation'],first)

    def test_identity_selection_or_quarantine_change_during_native_readback_is_held(self):
        for change in ('selection', 'quarantine', 'identity'):
            with self.subTest(change=change):
                self.setUp()
                def get(port,path,key,seconds):
                    if path == '/slots':
                        if change == 'selection':
                            self.docs['selection.json']['selected_frontier']='glm-5.3-flash'
                        elif change == 'quarantine':
                            self.docs['guard.json']['proxy_disposition'].update(quarantined=True)
                        else:
                            self.docs['state.json']['native'] = {**NATIVE, 'pid':1235}
                    return 200, copy.deepcopy(PROPS if path == '/props' else SLOTS)
                row=n.PassiveServiceCollector(n.MIMO,self.reader,get=get,clock=lambda:self.clock)(2)
                self.assertIsNot(row['ready'],True)
                self.assertIsNone(row['configured_context_tokens'])

    def test_dormant_glm_does_not_probe_readiness_or_advertise_ready(self):
        row=dict(boot_id=BOOT, running=True, frontier_selected=False,
                 ready=False,admitting=False,reason='unqualified')
        reader=SimpleNamespace(service=lambda *_:dict(row))
        value=n.PassiveServiceCollector('glm-5.3-flash',reader,
            get=lambda *_:self.fail('dormant rollback must not probe native readiness'))(2)
        self.assertFalse(value['ready'])

    def test_hardware_failure_affects_shared_frontier_only(self):
        snapshot=NodeStatus(Cached({'boot':sample(dict(boot_id=BOOT)), n.MIMO:sample(self.collect()),
            'qwen-gpu0':sample(dict(boot_id=BOOT,ready=True,hardware_latched=False,
                hardware_validation_age_ms=0, hardware_validated_boot_id=BOOT,
                hardware_validated_gpu_uuids=list(SERVICES['qwen-gpu0'])))})).snapshot()
        self.assertEqual(next(x for x in snapshot['services'] if x['service_id']=='qwen-gpu0')['availability'],'available')
        self.assertEqual(SERVICES[n.MIMO],SERVICES['glm-5.3-flash'])

    def test_container_name_must_agree_with_exact_manifest(self):
        self.manifest['container_name'] = 'llm-frontier-mimo-other'
        self.assertIsNot(self.collect()['ready'], True)

    def test_reviewed_actual_capacity_not_published_capacity(self):
        self.manifest['context'] = 262144
        digest = n.canonical_sha256(self.manifest)
        self.docs['selection.json']['manifest_sha256'] = digest
        for name in ('state.json','guard.json'):
            self.docs[name]['manifest_sha256'] = digest
            self.docs[name]['selection']['manifest_sha256'] = digest
        row = self.collect(props={**PROPS, 'default_generation_settings': {'n_ctx':262144}},
                           slots=[{**SLOTS[0], 'n_ctx':262144}])
        self.assertTrue(row['ready'])
        self.assertEqual(row['configured_context_tokens'],262144)

    def test_glm_native_bracket_rejects_deselection_even_same_generation(self):
        for changed in ({'frontier_selected':False},
                        {'frontier_selection':{'selected_frontier':'glm-5.3-flash','generation':2}},
                        {'generation':8}):
            row = dict(boot_id=BOOT,running=True,ownership_valid=True,frontier_selected=True,
                       frontier_selection={'selected_frontier':'glm-5.3-flash','generation':1},
                       generation=7,source_context_tokens=1048576,hardware_latched=None)
            responses = iter([row,{**row,**changed}])
            binding=SimpleNamespace(path=lambda *_:'/fixture',validate_path=lambda *_:None)
            reader=SimpleNamespace(service=lambda *_:next(responses),binding=lambda *_:binding,
                read=lambda *a,**k:b'fixture-key-123456789012345678901234',boot=lambda:dict(boot_id=BOOT))
            def get(port,path,key,seconds):
                if path == '/v1/readiness':
                    return 200, {'ready':True,'admitting':True,'model':'glm-5.3-flash'}
                return 200,dict(context_length=1048576,max_total_tokens=1048576,
                    max_total_num_tokens=1048576,max_req_input_len=1048570)
            # Pin readiness parser to a successful native result; exercise actual
            # capacity+second-identity bracket independently of response spelling.
            from unittest.mock import patch
            with patch.object(n,'text_readiness',return_value={'ready':True,'admitting':True}):
                value=n.PassiveServiceCollector('glm-5.3-flash',reader,get=get)(2)
            self.assertIsNot(value['ready'],True,changed)

if __name__=='__main__': unittest.main()
