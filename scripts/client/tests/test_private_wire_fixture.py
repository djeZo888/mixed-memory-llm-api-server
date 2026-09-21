"""Offline guards for the opt-in own-worker private HTTP wire proof."""

from email.message import Message
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from test_bootstrap import snapshot

SPEC = importlib.util.spec_from_file_location("n1c_private_wire", Path(__file__).with_name("private_wire_fixture.py"))
wire = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wire)


class PrivateWireGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="n1c-wire-guard-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_invalid_bind_addresses_fail_before_address_probe(self):
        for value in ("0.0.0.0", "127.0.0.1", "8.8.8.8", "169.254.1.1", "224.0.0.1",
                      "localhost", "::1", "10.01.2.3", "167772161", "0x0a000001", None, 1):
            with self.subTest(address=value), mock.patch.object(wire.subprocess, "run") as probe:
                with self.assertRaisesRegex(wire.FixtureError, "canonical_private_ipv4_required"):
                    wire.confirm_own_private_ipv4(value)
                probe.assert_not_called()

    def test_read_only_interface_confirmation_requires_exact_own_address(self):
        result = SimpleNamespace(stdout="en0: flags=active\n\tinet 10.156.100.182 netmask 0xffffff00\n")
        with mock.patch.object(wire.sys, "platform", "darwin"), \
                mock.patch.object(wire.subprocess, "run", return_value=result) as probe:
            self.assertEqual(wire.confirm_own_private_ipv4("10.156.100.182"), "10.156.100.182")
            probe.assert_called_once_with(["/sbin/ifconfig"], capture_output=True, text=True,
                                          timeout=10, check=True)
            with self.assertRaisesRegex(wire.FixtureError, "private_address_not_assigned_to_this_worker"):
                wire.confirm_own_private_ipv4("10.156.100.60")

    def test_foreign_address_is_refused_before_any_output_or_listener(self):
        before = snapshot(self.root)
        with mock.patch.object(wire, "confirm_own_private_ipv4", side_effect=wire.FixtureError("unassigned")), \
                mock.patch.object(wire, "OwnAddressServer") as server:
            with self.assertRaisesRegex(wire.FixtureError, "unassigned"):
                wire.run_fixture(self.root / "new", self.root / "source", "10.0.0.4")
            server.assert_not_called()
        self.assertEqual(snapshot(self.root), before)

    def test_existing_work_root_is_refused_without_listener(self):
        before = snapshot(self.root)
        with mock.patch.object(wire, "confirm_own_private_ipv4", return_value="10.0.0.4"), \
                mock.patch.object(wire, "OwnAddressServer") as server:
            with self.assertRaisesRegex(wire.FixtureError, "work_root_must_be_new"):
                wire.run_fixture(self.root, self.root / "source", "10.0.0.4")
            server.assert_not_called()
        self.assertEqual(snapshot(self.root), before)

    def test_server_refuses_other_lan_peers(self):
        server = object.__new__(wire.OwnAddressServer)
        server.server_address = ("10.156.100.182", 12345)
        self.assertTrue(server.verify_request(None, ("10.156.100.182", 55555)))
        for peer in ("10.156.100.60", "127.0.0.1", "10.156.100.181"):
            self.assertFalse(server.verify_request(None, (peer, 55555)))

    def test_exact_host_required_before_existing_path_and_key_validation(self):
        handler = object.__new__(wire.ExactHandler)
        handler.server = SimpleNamespace(expected_host="10.156.100.182:12345", failure=None)
        handler.send_error = mock.Mock()
        for hosts in ([], ["10.156.100.182:1234"], ["localhost:12345"],
                      ["10.156.100.182:12345", "10.156.100.182:12345"]):
            handler.headers = Message()
            for host in hosts:
                handler.headers.add_header("Host", host)
            with mock.patch.object(wire.Handler, "do_POST") as parent:
                handler.do_POST()
                parent.assert_not_called()
            self.assertEqual(handler.server.failure, "unexpected_host")
        handler.headers = Message()
        handler.headers.add_header("Host", "10.156.100.182:12345")
        with mock.patch.object(wire.Handler, "do_POST") as parent:
            handler.do_POST()
            parent.assert_called_once_with()

    def test_mismatched_dependency_lock_refuses_bootstrap(self):
        source = self.root / "source"
        runtime = wire.runtime_dir(source)
        runtime.mkdir(parents=True)
        (runtime / "package.json").write_text("{}")
        before = snapshot(self.root)
        with mock.patch.object(wire.bootstrap, "bootstrap") as bootstrap:
            with self.assertRaisesRegex(wire.FixtureError, "source_dependency_lock_mismatch"):
                wire.offline_bootstrap(self.root / "prefix", "http://10.0.0.1:1/v1",
                                       self.root / "key", source)
            bootstrap.assert_not_called()
        self.assertEqual(snapshot(self.root), before)

    def test_only_zero_request_native_timeout_is_unavailable(self):
        for failure, received, unavailable in (("child_timeout", 0, True),
                                                ("child_timeout", 1, False),
                                                ("unexpected_path", 1, False),
                                                ("synthetic_auth_failed", 1, False),
                                                ("child_failed_output_withheld", 0, False),
                                                ("opencode_error_event", 0, False)):
            with self.subTest(failure=failure, received=received), tempfile.TemporaryDirectory(
                    dir=self.root, prefix="case-") as folder:
                work_root = Path(folder)
                server = mock.Mock(server_port=12345)
                thread = mock.Mock()
                thread.is_alive.return_value = False

                def child(argv, *args):
                    if argv[-1] == "run":
                        server.received = received
                        raise wire.FixtureError(failure)
                    return b""

                with mock.patch.object(wire, "OwnAddressServer", return_value=server), \
                        mock.patch.object(wire.threading, "Thread", return_value=thread), \
                        mock.patch.object(wire, "offline_bootstrap"), \
                        mock.patch.object(wire, "child", side_effect=child):
                    with self.assertRaises(wire.FixtureError) as caught:
                        wire.run_case(work_root, work_root / "source", "10.0.0.4", "private",
                                      b"synthetic", work_root / "key")
                self.assertEqual(isinstance(caught.exception, wire.PrivateUnavailable), unavailable)
                server.shutdown.assert_called_once_with()
                server.server_close.assert_called_once_with()
                thread.join.assert_called_once_with(timeout=5)


if __name__ == "__main__":
    unittest.main()
