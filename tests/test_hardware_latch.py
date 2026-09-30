"""Offline hardware evidence fixtures; no NVML, live host or disk access."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from control.hardware_latch import (  # noqa: E402
    HardwareLatch, ProtectedHardwareLatch, LatchStateInvalid,
    LatchStorageUnavailable, empty_state,
)

GPU = "GPU-00000000-0000-0000-0000-000000000001"
PEER = "GPU-00000000-0000-0000-0000-000000000002"
EXTRA = "GPU-00000000-0000-0000-0000-000000000003"
BOOT = "00000000-0000-0000-0000-000000000001"
NEXT_BOOT = "00000000-0000-0000-0000-000000000002"


def inventory(second=0, *, boot=BOOT, uuids=None, **changes):
    value = {
        "state": "ok", "freshness": "fresh", "age_ms": 0,
        "complete": True, "boot_id": boot,
        "observed_at": f"2026-09-25T12:00:{second:02d}Z",
        "observation_id": f"receipt-{second}",
        "gpu_uuids": [PEER] if uuids is None else uuids,
        "hardware_faults": {},
    }
    value.update(changes)
    return value


def observe(latch, value=None, *, gpu=GPU, boot=BOOT, uptime=150):
    return latch.observe(gpu, inventory() if value is None else value,
                         current_boot_id=boot, boot_age_seconds=uptime)


def prove_missing(latch):
    assert not observe(latch, inventory(0))["hardware_latched"]
    assert observe(latch, inventory(5))["hardware_latched"]


class HardwareLatchTests(unittest.TestCase):
    def test_two_distinct_complete_receipts_after_grace_required(self):
        latch = HardwareLatch()
        self.assertEqual(observe(latch, inventory(0), uptime=119)["evidence_state"], "boot_grace")
        self.assertEqual(latch.export_state(), empty_state())
        self.assertEqual(observe(latch, inventory(1), uptime=120)["confirmation_count"], 1)
        self.assertFalse(observe(latch, inventory(1), uptime=125)["hardware_latched"])
        result = observe(latch, inventory(5), uptime=125)
        self.assertTrue(result["hardware_latched"])
        self.assertEqual(result["reason"], "hardware_missing")

    def test_pre_grace_sample_delivered_after_grace_does_not_count(self):
        latch = HardwareLatch()
        result = observe(latch, inventory(age_ms=4000), uptime=122)
        self.assertEqual(result["evidence_state"], "boot_grace")
        self.assertEqual(result["confirmation_count"], 0)

    def test_restore_pending_receipt_blocks_duplicate_count(self):
        latch = HardwareLatch()
        observe(latch)
        restarted = HardwareLatch(latch.export_state())
        self.assertEqual(observe(restarted)["confirmation_count"], 1)
        self.assertTrue(observe(restarted, inventory(5))["hardware_latched"])

    def test_restart_reset_and_late_healthy_never_clear_same_boot(self):
        latch = HardwareLatch()
        prove_missing(latch)
        for _ in range(3):
            latch = HardwareLatch(latch.export_state())  # App restart/reset loses no proof.
            result = observe(latch, inventory(10, uuids=[GPU, PEER]))
            self.assertTrue(result["hardware_latched"])
            self.assertEqual(result["latched_boot_id"], BOOT)

    def test_new_boot_unknown_and_missing_preserve_latch_until_valid_target(self):
        latch = HardwareLatch()
        prove_missing(latch)
        for value in (inventory(10, boot=NEXT_BOOT, state="timeout"),
                      inventory(10, boot=NEXT_BOOT, uuids=[]),
                      inventory(10, boot=NEXT_BOOT, uuids=[GPU], complete=False)):
            self.assertTrue(observe(latch, value, boot=NEXT_BOOT)["hardware_latched"])
        valid = inventory(11, boot=NEXT_BOOT, uuids=[GPU])
        self.assertFalse(observe(latch, valid, boot=NEXT_BOOT, uptime=10)["hardware_latched"])
        self.assertEqual(latch.export_state(), empty_state())

    def test_new_boot_requires_its_own_two_missing_confirmations(self):
        latch = HardwareLatch()
        observe(latch)
        first = observe(latch, inventory(5, boot=NEXT_BOOT), boot=NEXT_BOOT)
        self.assertEqual(first["confirmation_count"], 1)
        self.assertFalse(first["hardware_latched"])
        self.assertTrue(observe(latch, inventory(10, boot=NEXT_BOOT), boot=NEXT_BOOT)["hardware_latched"])

    def test_successful_empty_inventory_proves_absence_but_failed_init_never_does(self):
        latch = HardwareLatch()
        first = observe(latch, inventory(0, uuids=[]))
        self.assertEqual(first["evidence_state"], "missing")
        self.assertFalse(first["hardware_latched"])
        self.assertTrue(observe(latch, inventory(5, uuids=[]))["hardware_latched"])
        for state in ("error", "unknown", "timeout"):
            with self.subTest(state=state):
                failed = HardwareLatch()
                for second in (0, 5):
                    result = observe(failed, inventory(second, uuids=[], state=state,
                                     reason="nvml_init_failed"))
                    self.assertEqual(result["evidence_state"], "unknown")
                    self.assertFalse(result["hardware_latched"])
                self.assertEqual(failed.export_state(), empty_state())

    def test_unknown_stale_hung_and_ambiguous_never_prove_absence(self):
        cases = [
            {"state": "unknown"}, {"state": "timeout"}, {"state": "error"},
            {"freshness": "unknown"}, {"freshness": "stale"}, {"age_ms": 15001},
            {"age_ms": -1}, {"age_ms": None}, {"age_ms": True},
            {"age_ms": float("nan")}, {"age_ms": 10**400},
            {"boot_id": None}, {"boot_id": NEXT_BOOT}, {"complete": False},
            {"complete": 1}, {"gpu_uuids": None}, {"gpu_uuids": [PEER, PEER]},
            {"gpu_uuids": ["0"]}, {"gpu_uuids": [PEER, None]},
            {"observed_at": None}, {"observed_at": "2026-09-25T12:00:00"},
            {"hardware_faults": {GPU: "nvml_error"}},
            {"hardware_faults": {GPU: []}},
            {"hardware_faults": {GPU: "ecc_counter_nonzero"}},
        ]
        for change in cases:
            with self.subTest(change=change):
                latch = HardwareLatch()
                for second in (0, 5):
                    result = observe(latch, inventory(second, **change))
                    self.assertEqual(result["evidence_state"], "unknown")
                    self.assertFalse(result["hardware_latched"])
                self.assertEqual(latch.export_state(), empty_state())

    def test_unknown_boot_or_uptime_never_counts(self):
        for boot, uptime in ((None, 150), ("", 150), (BOOT, None),
                             (BOOT, -1), (BOOT, float("inf")), (BOOT, True)):
            with self.subTest(boot=boot, uptime=uptime):
                self.assertEqual(observe(HardwareLatch(), boot=boot, uptime=uptime)["evidence_state"], "unknown")

    def test_reordered_extra_or_missing_peer_does_not_disable_healthy_target(self):
        for uuids in ([GPU], [EXTRA, GPU], [PEER, EXTRA, GPU], [GPU, PEER, EXTRA]):
            with self.subTest(uuids=uuids):
                latch = HardwareLatch()
                for second in (0, 5):
                    self.assertEqual(observe(latch, inventory(second, uuids=uuids))["evidence_state"], "healthy")
                self.assertEqual(latch.export_state(), empty_state())

    def test_missing_target_latches_independently_of_present_peer(self):
        latch = HardwareLatch()
        for second in (0, 5):
            observe(latch, inventory(second, uuids=[EXTRA, PEER]))
            result = observe(latch, inventory(second, uuids=[PEER, EXTRA]), gpu=PEER)
            self.assertFalse(result["hardware_latched"])
            self.assertEqual(result["evidence_state"], "healthy")
        self.assertTrue(observe(latch)["hardware_latched"])

    def test_explicit_hardware_fault_can_latch_present_target(self):
        latch = HardwareLatch()
        for second in (0, 5):
            result = observe(latch, inventory(second, uuids=[GPU], hardware_faults={
                GPU: "gpu_unrecoverable_hardware_fault"}))
        self.assertTrue(result["hardware_latched"])
        self.assertEqual(result["reason"], "hardware_fault")

    def test_fault_reason_must_be_stable_across_confirmation_receipts(self):
        latch = HardwareLatch()
        observe(latch)
        result = observe(latch, inventory(5, uuids=[GPU], hardware_faults={
            GPU: "gpu_unrecoverable_hardware_fault"}))
        self.assertEqual(result["confirmation_count"], 1)
        result = observe(latch, inventory(6, uuids=[GPU], hardware_faults={
            GPU: "gpu_fallen_off_bus"}))
        self.assertEqual(result["confirmation_count"], 1)
        result = observe(latch, inventory(7, uuids=[GPU], hardware_faults={
            GPU: "gpu_fallen_off_bus"}))
        self.assertTrue(result["hardware_latched"])

    def test_replay_different_identifier_same_time_or_same_identifier_new_time(self):
        latch = HardwareLatch()
        observe(latch)
        for value in (inventory(0, observation_id="different"),
                      inventory(5, observation_id="receipt-0")):
            self.assertEqual(observe(latch, value)["confirmation_count"], 1)
        self.assertTrue(observe(latch, inventory(6))["hardware_latched"])

    def test_healthy_sample_breaks_pending_absence_confirmation(self):
        latch = HardwareLatch()
        observe(latch)
        observe(latch, inventory(5, uuids=[GPU]))
        self.assertEqual(observe(latch, inventory(10))["confirmation_count"], 1)

    def test_export_and_import_are_isolated_from_callers(self):
        latch = HardwareLatch()
        prove_missing(latch)
        saved = latch.export_state()
        restarted = HardwareLatch(saved)
        saved["targets"].clear()
        self.assertTrue(observe(latch)["hardware_latched"])
        self.assertTrue(observe(restarted)["hardware_latched"])

    def test_corrupt_persistence_never_resets_latch(self):
        latch = HardwareLatch()
        prove_missing(latch)
        for state in ({}, {"schema_version": True, "targets": {}},
                      {"schema_version": 1, "targets": {GPU: {}}}):
            with self.assertRaises(LatchStateInvalid):
                HardwareLatch(state)
        state = latch.export_state()
        state["targets"][GPU]["evidence"][1] = state["targets"][GPU]["evidence"][0]
        with self.assertRaises(LatchStateInvalid):
            HardwareLatch(state)


class MemoryProtectedStore:
    """Fixture only; production uses the existing protected-storage owner."""
    def __init__(self):
        self.state = empty_state()
        self.fail = False
        self.writes = 0

    def read(self):
        return copy.deepcopy(self.state)

    def write(self, state):
        if self.fail:
            raise OSError("private storage detail must not leak")
        self.state = copy.deepcopy(state)
        self.writes += 1


class ProtectedPersistenceTests(unittest.TestCase):
    def test_persistence_survives_reconstructed_app_and_no_write_on_status_evidence(self):
        store = MemoryProtectedStore()
        latch = ProtectedHardwareLatch(store)
        observe(latch)
        self.assertEqual(store.writes, 1)
        latch = ProtectedHardwareLatch(store)
        observe(latch)
        self.assertEqual(store.writes, 1)
        self.assertTrue(observe(latch, inventory(5))["hardware_latched"])
        self.assertTrue(observe(ProtectedHardwareLatch(store), inventory(6, uuids=[GPU]))["hardware_latched"])
        self.assertEqual(store.writes, 2)

    def test_failed_write_does_not_publish_or_lose_previous_proof(self):
        store = MemoryProtectedStore()
        latch = ProtectedHardwareLatch(store)
        observe(latch)
        store.fail = True
        with self.assertRaisesRegex(LatchStorageUnavailable, "^hardware_latch_storage_unavailable$"):
            observe(latch, inventory(5))
        self.assertEqual(latch.export_state(), store.state)
        store.fail = False
        self.assertTrue(observe(latch, inventory(5))["hardware_latched"])

    def test_failed_clear_is_not_published_and_restart_keeps_latch(self):
        store = MemoryProtectedStore()
        latch = ProtectedHardwareLatch(store)
        prove_missing(latch)
        store.fail = True
        with self.assertRaises(LatchStorageUnavailable):
            observe(latch, inventory(10, boot=NEXT_BOOT, uuids=[GPU]), boot=NEXT_BOOT)
        self.assertTrue(observe(ProtectedHardwareLatch(store))["hardware_latched"])

    def test_missing_or_corrupt_persistence_fails_closed(self):
        store = MemoryProtectedStore()
        for value in (None, {}, {"schema_version": 1, "targets": {GPU: {}}}):
            store.state = value
            with self.assertRaises(LatchStorageUnavailable):
                ProtectedHardwareLatch(store)


if __name__ == "__main__":
    unittest.main()
