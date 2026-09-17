"""Injected frozen I1b interface tests; these are NOT integrated writer tests."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from storage_fixtures import RegisteredFixture
from lifecycle.storage_binding import BindingError


class MountedGuardInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = RegisteredFixture()
        self.addCleanup(self.fixture.close)
        self.binding = self.fixture.binding()
        self.events = []
        self.instances = []
        events, instances = self.events, self.instances

        class InjectedMountedStorageGuard:
            """Frozen protocol only; does not implement descriptors or a writer."""
            def __init__(self, storage):
                self.snapshot = storage.verify()
                self.active = False
                self.full_result = None
                self.fail_full = False
                self.path_result = None
                self.fail_path = False
                events.append("constructed")
                instances.append(self)

            def __enter__(self):
                self.active = True
                events.append("entered")
                return self

            def __exit__(self, kind, error, traceback):
                self.active = False
                events.append(("closed", kind))

            def __call__(self):
                if not self.active:
                    raise RuntimeError("fixture-closed")
                events.append("snapshot")
                return self.snapshot

            def verify_full(self):
                events.append("full")
                if self.fail_full:
                    raise RuntimeError("SENSITIVE-SHARED-ERROR")
                return self.full_result

            def check_path(self, path):
                if not self.active:
                    raise RuntimeError("fixture-closed")
                events.append(("check_path", path))
                if self.fail_path:
                    raise RuntimeError("SENSITIVE-PATH-ERROR")
                return self.snapshot if self.path_result is None else self.path_result

        self.guard_class = InjectedMountedStorageGuard
        self.io = SimpleNamespace(MountedStorageGuard=InjectedMountedStorageGuard)

    def test_before_after_full_guards_and_single_context_close(self):
        with self.binding.mounted_guard(self.io, roles=("data",)) as guard:
            self.assertEqual(self.events[:4], ["constructed", "entered", "full", "snapshot"])
            result = guard()
            self.assertEqual(result["data"]["uuid"], "data-uuid")
            result["data"]["uuid"] = "caller-mutation"
            self.assertEqual(guard()["data"]["uuid"], "data-uuid")
        self.assertEqual(self.events.count("full"), 2)
        self.assertEqual([item for item in self.events if isinstance(item, tuple)], [("closed", None)])
        with self.assertRaisesRegex(BindingError, "mounted_storage_guard_failed"):
            guard()

    def test_every_fast_snapshot_is_bound_to_original_stable_identity(self):
        for field in ("uuid", "mount", "path", "fstype"):
            with self.subTest(field=field), self.assertRaisesRegex(BindingError, "mounted_storage_identity_changed"):
                with self.binding.mounted_guard(self.io) as guard:
                    self.instances[-1].snapshot["models"][field] = "changed"
                    guard()
            self.assertFalse(self.instances[-1].active)

    def test_full_guard_return_is_checked_even_when_fast_snapshot_is_original(self):
        with self.assertRaisesRegex(BindingError, "mounted_storage_identity_changed"):
            with self.binding.mounted_guard(self.io) as guard:
                changed = copy.deepcopy(self.instances[-1].snapshot)
                changed["roots"]["docker"] = "/unregistered"
                self.instances[-1].full_result = changed
        self.assertFalse(self.instances[-1].active)

    def test_actual_absolute_operation_path_forwarded_without_projection(self):
        with self.binding.mounted_guard(self.io) as guard:
            for path in ("/srv/ai/services/backend/new/state.json",
                         Path("/srv/ai/services/backend/new/state.json")):
                with self.subTest(path=path):
                    before = self.events.count("snapshot")
                    result = guard.check_path(path)
                    self.assertEqual(self.events[-1], ("check_path", path))
                    self.assertIs(self.events[-1][1], path)
                    self.assertEqual(self.events.count("snapshot"), before)
                    result["data"]["uuid"] = "caller-mutation"
                    self.assertEqual(guard.check_path(path)["data"]["uuid"], "data-uuid")

    def test_path_snapshot_identity_is_checked_even_when_fast_snapshot_is_original(self):
        with self.binding.mounted_guard(self.io) as guard:
            changed = copy.deepcopy(self.instances[-1].snapshot)
            changed["roots"]["services"] = "/unregistered"
            self.instances[-1].path_result = changed
            with self.assertRaisesRegex(BindingError, "^mounted_storage_identity_changed$"):
                guard.check_path("/srv/ai/services/state.json")
            self.assertEqual(guard()["roots"]["services"], "/srv/ai/services")

    def test_path_failure_is_sanitized_and_closed_guard_remains_unusable(self):
        with self.binding.mounted_guard(self.io) as guard:
            self.instances[-1].fail_path = True
            with self.assertRaisesRegex(BindingError, "^mounted_storage_guard_failed$"):
                guard.check_path("/srv/ai/services/state.json")
        with self.assertRaisesRegex(BindingError, "^mounted_storage_guard_failed$"):
            guard.check_path("/srv/ai/services/state.json")
        self.assertFalse(self.instances[-1].active)

    def test_missing_path_capability_fails_without_snapshot_fallback(self):
        with self.binding.mounted_guard(self.io) as guard:
            self.instances[-1].check_path = None
            before = list(self.events)
            with self.assertRaisesRegex(BindingError, "^mounted_storage_path_guard_required$"):
                guard.check_path("/srv/ai/services/state.json")
            self.assertEqual(self.events, before)

    def test_observed_device_renumbering_does_not_change_stable_identity(self):
        with self.binding.mounted_guard(self.io) as guard:
            self.instances[-1].snapshot["data"].update(source="/dev/renumbered", device="259:44", parents=["/dev/parent"])
            self.assertEqual(guard()["data"]["device"], "259:44")

    def test_body_exception_preserved_and_context_closed(self):
        expected = ValueError("caller failure")
        with self.assertRaises(ValueError) as caught:
            with self.binding.mounted_guard(self.io):
                raise expected
        self.assertIs(caught.exception, expected)
        self.assertEqual(self.events.count("full"), 2)
        self.assertEqual(self.events[-1], ("closed", ValueError))

    def test_shared_failure_is_sanitized_and_context_closed(self):
        with self.assertRaisesRegex(BindingError, "^mounted_storage_guard_failed$"):
            with self.binding.mounted_guard(self.io):
                self.instances[-1].fail_full = True
        self.assertFalse(self.instances[-1].active)

    def test_roles_forwarded_only_to_explicitly_supported_constructor(self):
        received = []
        base = self.guard_class

        class RoleAwareGuard(base):
            def __init__(self, storage, *, roles):
                received.append(roles)
                super().__init__(storage)

        with self.binding.mounted_guard(SimpleNamespace(MountedStorageGuard=RoleAwareGuard), roles=("data",)):
            pass
        self.assertEqual(received, [("data",)])
        # The original frozen constructor accepts no roles; this must remain
        # usable but does not prove data-only acceptance on missing model mounts.
        with self.binding.mounted_guard(self.io, roles=("data",)):
            pass

    def test_missing_guard_or_invalid_roles_refused_without_fallback(self):
        with self.assertRaisesRegex(BindingError, "i1b_mounted_storage_guard_required"):
            with self.binding.mounted_guard(SimpleNamespace()):
                self.fail("must not enter")
        for roles in ((), ("unknown",), "data"):
            with self.subTest(roles=roles), self.assertRaisesRegex(BindingError, "invalid_storage_roles"):
                with self.binding.mounted_guard(self.io, roles=roles):
                    self.fail("must not enter")


if __name__ == "__main__":
    unittest.main()
