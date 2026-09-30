"""Narrow offline checks: no credentials, network, image generation or full decode."""

import base64
import importlib.util
import io
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest import mock
from urllib.error import HTTPError


SPEC = importlib.util.spec_from_file_location(
    "image_example", Path(__file__).with_name("generate.py"))
example = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(example)
CALLER = SimpleNamespace(pw_name="example-user", pw_uid=1001, pw_gid=1002)


def png_header(width=1920, height=1080):
    # Deliberately a header fixture, not evidence of a decoded or generated image.
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
            + struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
            + b"\0\0\0\0")


def response(png):
    return json.dumps({"data": [{"b64_json": base64.b64encode(png).decode("ascii")}]}
                      ).encode("utf-8")


class OfflineTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket", "socket.create_connection"):
            patcher = mock.patch(target, side_effect=AssertionError("network forbidden"))
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_fullhd_header_passes_without_claiming_full_decode(self):
        header = png_header()
        self.assertEqual(example.decode_response(response(header)), header)

    def test_rejects_schema_and_base64_failures(self):
        values = [None, [], {}, {"data": []}, {"data": [{}, {}]},
                  {"data": [{}]}, {"data": [{"b64_json": 1}]},
                  {"data": [{"b64_json": "not base64!"}]}]
        for value in values:
            with self.subTest(value=value), self.assertRaises(example.ExampleError):
                example.decode_response(json.dumps(value).encode("utf-8"))
        for raw in (b"{", b"\xff"):
            with self.subTest(raw=raw), self.assertRaises(example.ExampleError):
                example.decode_response(raw)

    def test_rejects_png_header_and_dimension_failures(self):
        header = png_header()
        bad_headers = [b"", header[:24], b"bad-sign" + header[8:],
                       header[:8] + struct.pack(">I", 12) + header[12:],
                       header[:12] + b"IDAT" + header[16:],
                       png_header(1920, 1088), png_header(1080, 1920)]
        for bad in bad_headers:
            with self.subTest(header=bad), self.assertRaises(example.ExampleError):
                example.decode_response(response(bad))

    def test_http_error_uses_status_only_and_never_reads_body(self):
        body = mock.Mock()
        body.read.side_effect = AssertionError("error body must not be read")
        opener = mock.Mock()
        opener.open.side_effect = HTTPError(
            "http://127.0.0.1:30006/v1/images/generations", 429,
            "untrusted backend text", {"X-Untrusted": "untrusted header"}, body)
        with mock.patch.object(example.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(example.ExampleError) as caught:
                example.request_png("complete local prompt", None, "fixture-only-key")
        message = str(caught.exception)
        self.assertIn("429", message)
        self.assertIn("busy", message.lower())
        self.assertNotIn("untrusted", message)
        body.read.assert_not_called()
        opener.open.assert_called_once()

    def test_fixed_http_messages(self):
        self.assertIn("busy", example.http_error_message(429).lower())
        self.assertIn("request", example.http_error_message(400).lower())
        self.assertLess(len(example.http_error_message(599)), 160)

    def test_root_requires_valid_sudo_identity(self):
        invalid = [{}, {"SUDO_UID": "0", "SUDO_GID": "1002"},
                   {"SUDO_UID": "01001", "SUDO_GID": "1002"},
                   {"SUDO_UID": "1001", "SUDO_GID": "0"},
                   {"SUDO_UID": "1001", "SUDO_GID": "9999"}]
        with mock.patch.object(example.os, "getuid", return_value=0), \
                mock.patch.object(example.os, "geteuid", return_value=0), \
                mock.patch.object(example.pwd, "getpwuid", return_value=CALLER):
            for environ in invalid:
                with self.subTest(environ=environ), \
                        mock.patch.dict(example.os.environ, environ, clear=True), \
                        self.assertRaises(example.ExampleError):
                    example.sudo_caller()
            with mock.patch.dict(example.os.environ,
                                 {"SUDO_UID": "1001", "SUDO_GID": "1002"}, clear=True):
                self.assertEqual(example.sudo_caller(), CALLER)

    def privilege_mocks(self, groups):
        calls = mock.Mock()
        for name in ("initgroups", "setgid", "setuid"):
            patcher = mock.patch.object(example.os, name)
            calls.attach_mock(patcher.start(), name)
            self.addCleanup(patcher.stop)
        returns = {"getuid": 1001, "geteuid": 1001, "getgid": 1002, "getegid": 1002,
                   "getgroups": groups}
        if hasattr(example.os, "getresuid"):
            returns["getresuid"] = (1001, 1001, 1001)
        if hasattr(example.os, "getresgid"):
            returns["getresgid"] = (1002, 1002, 1002)
        for name, value in returns.items():
            patcher = mock.patch.object(example.os, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        return calls

    def test_drop_replaces_groups_before_gid_and_uid(self):
        calls = self.privilege_mocks([1002, 1003])
        example.drop_privileges(CALLER)
        self.assertEqual(calls.mock_calls, [mock.call.initgroups("example-user", 1002),
                                          mock.call.setgid(1002), mock.call.setuid(1001)])

    def test_drop_rejects_remaining_root_group_or_uid(self):
        self.privilege_mocks([0, 1002])
        with self.assertRaises(example.ExampleError):
            example.drop_privileges(CALLER)
        with mock.patch.object(example.os, "getgroups", return_value=[1002]), \
                mock.patch.object(example.os, "geteuid", return_value=0):
            with self.assertRaises(example.ExampleError):
                example.drop_privileges(CALLER)

    def test_main_reads_key_then_drops_before_request_or_save(self):
        header = png_header()
        functions = {"sudo_caller": CALLER, "read_key": "fixture-only-key",
                     "drop_privileges": None, "open_output_directory": 123,
                     "request_png": header, "save_png": None}
        calls = mock.Mock()
        with mock.patch.multiple(example, **{name: mock.DEFAULT for name in functions}) as mocks, \
                mock.patch.object(example.os, "close") as close, \
                mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            for name, value in functions.items():
                mocks[name].return_value = value
                calls.attach_mock(mocks[name], name)
            result = example.main(["--prompt", "complete prompt", "--output",
                                   str(example.OUTPUT_DIR / "fixture.png")])
        self.assertEqual(result, 0)
        self.assertEqual([call[0] for call in calls.mock_calls], list(functions))
        mocks["drop_privileges"].assert_called_once_with(CALLER)
        close.assert_called_once_with(123)
        self.assertIn("1920x1080", output.getvalue())
        self.assertNotIn("fixture-only-key", output.getvalue())


if __name__ == "__main__":
    unittest.main()
