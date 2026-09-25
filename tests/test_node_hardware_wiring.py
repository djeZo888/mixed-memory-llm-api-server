"""Full scheduled collector -> protected policy -> cached public latch fixtures.

Real canonical lease and production parsers/producers/projection execute here.
GPU output, Linux boot/time and persistence I/O are explicit worker seams. These
fixtures do not query or mutate a GPU, service or installed protected path.
"""
import contextlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_hardware_latch import MemoryProtectedStore, BOOT, NEXT_BOOT
from tests.test_node_projection import Cached, sample
from common.lifecycle_lease import acquire_lease, LeaseBusy
from control import node_collectors as c
from control import node_observation
from control.node import NodeStatus, NodeApplication
from lifecycle import hardware_policy as policy_module
from lifecycle.hardware_policy import GPU_UUIDS, HardwarePolicy, read_latch_status

GPU = GPU_UUIDS[0]


class HardwareProducerWiring(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.store = MemoryProtectedStore()
        self.boot_id, self.uptime = BOOT, 150
        self.epoch, self.tick = 1790347200.0, 100.0
        self.output = ''
        self.commands = []
        self.inventory = c.InventoryCollector()
        self.gpu = c.GpuCollector(GPU, run=self.command, boot=self.boot, wall=lambda: self.epoch)
        self.producer = c.HardwareEvidenceCollector(self.inventory, [self.gpu])
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        original_inventory = c.collect_inventory
        original_init = HardwarePolicy.__init__
        def init(policy, store, **kwargs):
            original_init(policy, store, **dict(kwargs, boot=lambda: {
                'boot_id': self.boot_id, 'uptime_seconds': self.uptime},
                wall=lambda: self.epoch, monotonic=lambda: self.tick,
                system_root=self.root, trusted_uid=os.geteuid()))
        stack.enter_context(patch.object(c, 'collect_inventory', side_effect=lambda seconds:
            original_inventory(seconds, run=self.command, boot=self.boot)))
        stack.enter_context(patch.object(policy_module, 'RegisteredLatchStore', side_effect=lambda *a, **kw: self.store))
        stack.enter_context(patch.object(HardwarePolicy, '__init__', init))
        stack.enter_context(patch.object(node_observation, 'production_binding', return_value=object()))
        stack.enter_context(patch('common.lifecycle_lease.acquire_lease', side_effect=lambda **kwargs:
            acquire_lease(system_root=self.root, trusted_uid=os.geteuid(), **kwargs)))
        stack.enter_context(patch.object(c.time, 'time', side_effect=lambda: self.epoch))
        stack.enter_context(patch.object(c.time, 'monotonic', side_effect=lambda: self.tick))

    def boot(self):
        return {'boot_id': self.boot_id, 'boot_age_seconds': self.uptime}

    def advance(self, seconds):
        self.epoch += seconds
        self.tick += seconds
        self.uptime += seconds

    def command(self, argv, seconds):
        self.commands.append(argv)
        if argv[1] == '--id=' + GPU:
            return '<nvidia_smi_log><gpu><uuid>' + GPU + '</uuid><temperature><gpu_temp>40</gpu_temp></temperature></gpu></nvidia_smi_log>'
        self.assertEqual(argv, ['/usr/bin/nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader,nounits'])
        if isinstance(self.output, Exception):
            raise self.output
        return self.output

    def latch(self):
        return read_latch_status(object(), [GPU], current_boot_id=self.boot_id, wall=lambda: self.epoch)

    def public(self, **sample_options):
        raw = dict(self.latch(), boot_id=self.boot_id, ready=True, admitting=None)
        snapshot = NodeStatus(Cached({'boot': sample({'boot_id': self.boot_id}),
                                     'qwen-gpu0': sample(raw, **sample_options)})).snapshot()
        return next(item for item in snapshot['services'] if item['service_id'] == 'qwen-gpu0')

    def prove_missing(self):
        self.inventory(2)
        self.producer(2)
        self.advance(5)
        self.inventory(2)
        self.producer(2)
        self.assertTrue(self.public()['hardware_latched'])

    def test_empty_or_inventory_presence_has_no_negative_proof_until_exact_gpu_probe(self):
        self.assertIsNone(self.public()['hardware_latched'])
        self.output = GPU
        self.inventory(2)
        self.producer(2)
        self.assertIsNone(self.public()['hardware_latched'])
        self.gpu(2)
        self.producer(2)
        self.assertFalse(self.public()['hardware_latched'])
        self.advance(14)
        # Child proof age plus cached service age must both count.
        self.assertIsNone(self.public(age_ms=2000)['hardware_latched'])

    def test_global_inventory_failure_with_exact_uuid_clears_inherited_only_on_new_boot(self):
        self.prove_missing()
        self.gpu(2)
        self.producer(2)
        self.assertTrue(self.public()['hardware_latched'])
        self.boot_id, self.uptime = NEXT_BOOT, 10
        self.advance(1)
        self.output = RuntimeError('NVML initialization failed')
        with self.assertRaises(RuntimeError):
            self.inventory(2)
        self.gpu(2)  # Actual production XML exact-UUID parser, not a fabricated proof.
        self.producer(2)
        public = self.public()
        self.assertFalse(public['hardware_latched'])
        self.assertIsNone(public['hardware_latched_boot_id'])
        self.assertEqual(self.latch()['hardware_validated_boot_id'], NEXT_BOOT)
        self.assertEqual(self.latch()['hardware_validated_gpu_uuids'], [GPU])
        self.assertEqual([x for x in self.commands if x[1].startswith('--id=')][-1],
                         ['/usr/bin/nvidia-smi', '--id=' + GPU, '-q', '-x'])

    def test_stale_exact_proof_cannot_clear_inherited_new_boot_latch(self):
        self.prove_missing()
        self.boot_id, self.uptime = NEXT_BOOT, 20
        self.gpu(2)
        self.advance(16)
        self.producer(2)
        self.assertTrue(self.public()['hardware_latched'])
        self.assertEqual(self.public()['hardware_latched_boot_id'], BOOT)

    def test_cached_exact_proof_cannot_erase_newer_absence_receipts(self):
        self.gpu(2)
        self.producer(2)
        self.assertFalse(self.public()['hardware_latched'])
        self.advance(5)
        self.inventory(2)  # successful empty, newer than cached exact UUID proof
        self.producer(2)
        self.assertEqual(len(self.store.state['targets'][GPU]['evidence']), 1)
        self.assertIsNone(self.public()['hardware_latched'])
        self.advance(5)
        self.inventory(2)
        self.producer(2)
        self.assertTrue(self.public()['hardware_latched'])

    def test_same_inventory_receipt_never_double_counts_and_boot_grace_counts_capture(self):
        self.uptime = 119
        self.inventory(2)
        self.advance(3)
        self.producer(2)
        self.assertNotIn(GPU, self.store.state['targets'])
        self.inventory(2)
        self.producer(2)
        self.advance(2)
        self.producer(2)  # same receipt read twice
        self.assertFalse(self.store.state['targets'][GPU]['hardware_latched'])
        self.assertEqual(len(self.store.state['targets'][GPU]['evidence']), 1)
        self.advance(1)
        self.inventory(2)
        self.producer(2)
        self.assertTrue(self.public()['hardware_latched'])

    def test_lease_contention_blocks_producer_and_cached_get_has_no_writes(self):
        self.gpu(2)
        with acquire_lease(system_root=self.root, trusted_uid=os.geteuid()):
            with self.assertRaises(LeaseBusy):
                self.producer(2)
        self.assertEqual(self.store.writes, 0)
        raw = dict(self.latch(), boot_id=self.boot_id, ready=None, admitting=None)
        app = NodeApplication(NodeStatus(Cached({'boot': sample({'boot_id': self.boot_id}),
                                               'qwen-gpu0': sample(raw)})))
        calls = list(self.commands)
        for _ in range(3):
            status, body = app.handle('GET', '/control/v1/node/status', {}, b'')
            self.assertEqual(status, 200)
            self.assertIsNone(body['services'][0]['hardware_latched'])
        self.assertEqual(self.store.writes, 0)
        self.assertEqual(self.commands, calls)
