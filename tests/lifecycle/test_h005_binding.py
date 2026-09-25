"""Source and explicit dependency fixtures; no image/build/live claims."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.lifecycle.test_concurrent_profiles import bound, receipt, pair
from lifecycle import qwen38 as q
from runtime import h005_runtime_binding as binding
from runtime import qwen38_oci as parent


class BindingTests(unittest.TestCase):
    def test_exact_full_binding_bytes_and_no_implicit_completed_build(self):
        value = binding.load(require_complete=False)
        self.assertEqual(value['text']['parent_config_digest'], parent.CONFIG_DIGEST)
        self.assertEqual(value['text']['parent_image_reference'], parent.IMAGE_REFERENCE)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / binding.RELATIVE
            path.parent.mkdir(parents=True)
            path.write_bytes((binding.ROOT / binding.RELATIVE).read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'h005_binding_source_mismatch'):
                binding.load(root=root)
        if value['status'] == 'BLOCKED_BY_BUILD':
            with self.assertRaisesRegex(ValueError, 'h005_runtime_blocked_by_build'):
                binding.text_oci()

    def test_closed_selector_refuses_parent_tag_wrong_overlay_and_container(self):
        value = copy.deepcopy(binding.load(require_complete=False))
        value.update(status='COMPLETE_VERIFIED_BUILD', build_receipt_sha256='8'*64)
        item = value['text']
        item.update(image_id='sha256:'+'6'*64, image_id_domain='oci_config',
                    image_config_digest='sha256:'+'6'*64, image_manifest_digest=None)
        with patch.object(binding, 'load', return_value=value):
            oci = binding.text_oci()
        image = {'Id': item['image_id'], 'Os':'linux','Architecture':'amd64','Config':{
            'Entrypoint':list(parent.IMAGE_ENTRYPOINT),'Cmd':None,'WorkingDir':parent.IMAGE_WORKDIR,
            'Labels':{'org.opencontainers.image.revision':parent.SOURCE_REVISION,
                'org.opencontainers.image.source':parent.SOURCE_REPOSITORY,
                'io.llmctl.adaptive-idle.overlay-sha256':item['overlay_sha256']}}}
        evidence = oci.verify_image(image)
        self.assertEqual(oci.IMAGE_REFERENCE, item['image_id'])
        for wrong in (parent.CONFIG_DIGEST, parent.MANIFEST_DIGEST, 'latest', 'sha256:'+'9'*64):
            with self.assertRaises(ValueError):
                oci.verify_image({**image, 'Id':wrong})
        changed = copy.deepcopy(image)
        changed['Config']['Labels']['io.llmctl.adaptive-idle.overlay-sha256']='0'*64
        with self.assertRaisesRegex(ValueError, 'h005_overlay_label_mismatch'):
            oci.verify_image(changed)
        changed = copy.deepcopy(image)
        changed['Config']['Volumes'] = {'/models': {}}
        with self.assertRaisesRegex(ValueError, 'h005_image_volumes_unreviewed'):
            oci.verify_image(changed)
        container={'Image':item['image_id'],'Config':{'Image':item['image_id']}}
        oci.validate_container_image(container,evidence)
        container['Config']['Image']='local-tag:latest'
        with self.assertRaises(ValueError):
            oci.validate_container_image(container,evidence)

    def test_pair_only_transformation_preserves_parent_and_resources(self):
        d = pair.declared_profile(pair.QWEN0_PROFILE)
        original = json.loads((binding.ROOT/'configs/runtimes/sglang-qwen38-0.5.19.json').read_text())
        self.assertEqual(d['_runtime']['parent_image_id'], original['image_id'])
        for name in ('environment','image_environment','required_cli_flags','source_commit','entrypoint'):
            self.assertEqual(d['_runtime'][name],original[name])
        self.assertEqual(q.declared_profile('qwen38-27b-256k')['_runtime'],original)
        self.assertEqual(d['launch']['context_size'],480000)
        self.assertEqual(d['concurrent_pair']['memory_bytes'],d['concurrent_pair']['memory_swap_bytes'])

    def test_protected_source_closure_contains_all_runtime_inputs(self):
        identity = pair.source_identity()
        for name in ('scripts/runtime/h005_runtime_binding.py',binding.RELATIVE,
            'scripts/runtime/verify_adaptive_idle_overlay.py','scripts/runtime/adaptive_text_drain.py',
            'scripts/runtime/adaptive_diffusion_drain.py','scripts/lifecycle/hardware_policy.py'):
            self.assertEqual(identity[name],hashlib.sha256((pair.ROOT/name).read_bytes()).hexdigest())


class TransitionTests(unittest.TestCase):
    def test_missing_transition_or_dated_receipt_drift_rejected(self):
        d=bound(pair.QWEN0_PROFILE); value,instance=receipt(d)
        pair.check_acceptance(d,instance)
        transition=value.pop('h005_transition')
        instance['concurrent_pair_acceptance']['sha256']=pair.receipt_sha256(value)
        with self.assertRaisesRegex(Exception,'h005_reviewed_transition_required'):
            pair.check_acceptance(d,instance)
        value['h005_transition']=transition
        old=d['_storage_binding'].documents[d['_storage_binding'].path('data',pair.PREDECESSOR_SUFFIX)]
        old['modes']['dual-qwen']['slots']['glm']['largest_occupied_context']-=1
        instance['concurrent_pair_acceptance']['sha256']=pair.receipt_sha256(value)
        with self.assertRaisesRegex(Exception,'h005_predecessor_receipt_mismatch'):
            pair.check_acceptance(d,instance)

    def test_cannot_relabel_measurement_as_fresh_or_change_capacity(self):
        for field in ('largest_occupied_context','host_peak_bytes','sampled_required_working_set_estimate_bytes'):
            d=bound(pair.QWEN0_PROFILE); value,instance=receipt(d)
            value['modes']['dual-qwen']['slots']['glm'][field]-=1
            instance['concurrent_pair_acceptance']['sha256']=pair.receipt_sha256(value)
            with self.assertRaisesRegex(Exception,'h005_inherited_measurement_changed'):
                pair.check_acceptance(d,instance)
        for field,value in (('host_usable_bytes',900*1024**3),('gpu_inventory',[[0,'GPU-synthetic']])):
            d=bound(pair.QWEN0_PROFILE);current,instance=receipt(d)
            current[field]=value
            instance['concurrent_pair_acceptance']['sha256']=pair.receipt_sha256(current)
            with self.assertRaisesRegex(Exception,'h005_inherited_measurement_changed'):
                pair.check_acceptance(d,instance)
        d=bound(pair.QWEN0_PROFILE);value,instance=receipt(d)
        value['h005_transition']['live_acceptance']='PASS'
        instance['concurrent_pair_acceptance']['sha256']=pair.receipt_sha256(value)
        with self.assertRaisesRegex(Exception,'h005_reviewed_transition_required'):
            pair.check_acceptance(d,instance)

    def test_no_parent_native_auth_receipt_can_admit_new_pair(self):
        d=bound(pair.QWEN0_PROFILE)
        with self.assertRaises(Exception):
            q.evidence(d,{'runtime_evidence':{q.RUNTIME:{'auth_gate_passed':True}}})
