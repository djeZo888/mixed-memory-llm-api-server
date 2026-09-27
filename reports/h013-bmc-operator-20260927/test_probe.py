#!/usr/bin/env python3
"""Offline safety regression tests; never connect to any endpoint."""
import hashlib
import gzip
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location('h013_readonly_probe', Path(__file__).with_name('probe.py'))
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
TEST_DER = b'offline-test-certificate-not-a-real-credential'
TEST_PIN = hashlib.sha256(TEST_DER).hexdigest()


class FakeSocket:
    def __init__(self, der=TEST_DER):
        self.der = der
        self.sent = []
        self.closed = False

    def getpeercert(self, binary_form=False):
        assert binary_form is True
        return self.der

    def sendall(self, value):
        self.sent.append(value)

    def close(self):
        self.closed = True


class SafetyTests(unittest.TestCase):
    def setUp(self):
        probe.PIN_CHECKS = 0
        probe.REQUESTS = 0
        self.time_patch = patch.object(probe.time, 'time', return_value=probe.DEADLINE - 60)
        self.time_patch.start()
        self.addCleanup(self.time_patch.stop)
        # A regression that accidentally reaches a real socket fails before I/O.
        self.network_patch = patch.object(probe.socket, 'create_connection', side_effect=AssertionError('offline test forbids network'))
        self.network_patch.start()
        self.addCleanup(self.network_patch.stop)

    def test_actual_socket_pin_before_credential_and_http_send(self):
        events = []
        sock = FakeSocket()
        def connect(conn):
            events.append('tls')
            conn.sock = sock
        def credentials():
            events.append('credential')
            self.assertEqual(probe.PIN_CHECKS, 1)
            return {'username': 'sova', 'password': 'offline-test-only'}
        def send(conn, method, path, **kwargs):
            events.append('http')
            self.assertIs(conn.sock, sock)
            self.assertIn('Authorization', kwargs['headers'])
        response = Mock(status=200)
        response.read.return_value = b'{"Name":"CHA_FAN3"}'
        response.getheader.return_value = None
        with patch.object(probe, 'PIN', TEST_PIN), patch.object(probe.http.client.HTTPSConnection, 'connect', connect), patch.object(probe, 'credential', credentials), patch.object(probe.http.client.HTTPSConnection, 'request', send), patch.object(probe.http.client.HTTPSConnection, 'getresponse', return_value=response):
            result = probe.request('/redfish/v1')
        self.assertEqual(events, ['tls', 'credential', 'http'])
        self.assertTrue(result['pin_verified'])
        self.assertTrue(sock.closed)

    def test_changed_pin_stops_before_credential_or_request(self):
        sock = FakeSocket(b'changed-test-certificate')
        def connect(conn):
            conn.sock = sock
        with patch.object(probe, 'PIN', TEST_PIN), patch.object(probe.http.client.HTTPSConnection, 'connect', connect), patch.object(probe, 'credential') as cred, patch.object(probe.http.client.HTTPSConnection, 'request') as send:
            with self.assertRaises(probe.PinError):
                probe.request('/redfish/v1')
        cred.assert_not_called()
        send.assert_not_called()
        self.assertEqual(probe.REQUESTS, 0)
        self.assertTrue(sock.closed)

    def test_http_reconnect_rechecks_peer_before_send(self):
        sockets = [FakeSocket(), FakeSocket(b'changed-on-reconnect')]
        def connect(conn):
            conn.sock = sockets[probe.PIN_CHECKS]
        with patch.object(probe, 'PIN', TEST_PIN), patch.object(probe.http.client.HTTPSConnection, 'connect', connect):
            conn = probe.PinnedConnection()
            self.assertEqual((conn.host, conn.port), (probe.HOST, 443))
            conn.send(b'offline-first-message')
            conn.close()
            with self.assertRaises(probe.PinError):
                conn.send(b'offline-must-not-send')
        self.assertEqual(probe.PIN_CHECKS, 2)
        self.assertEqual(len(sockets[0].sent), 1)
        self.assertEqual(sockets[1].sent, [])
        self.assertTrue(sockets[1].closed)

    def test_only_read_methods_and_local_paths(self):
        with patch.object(probe, 'PinnedConnection') as connect:
            for method in ('POST', 'PATCH', 'PUT', 'DELETE', 'CONNECT', 'TRACE'):
                with self.subTest(method=method), self.assertRaises(ValueError):
                    probe.request('/redfish/v1', method)
            for path in ('https://elsewhere.invalid/', '//elsewhere.invalid/', '/a\r\nb', '/a?x=1', '/a#fragment'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    probe.request(path)
            connect.assert_not_called()

    def test_redirect_is_not_followed_and_location_not_retained(self):
        conn = Mock()
        response = Mock(status=302)
        response.read.return_value = b'private response body'
        response.getheader.return_value = None
        conn.getresponse.return_value = response
        with patch.object(probe, 'PinnedConnection', return_value=conn), patch.object(probe, 'credential') as cred:
            result = probe.request('/redfish/v1', auth=False)
        cred.assert_not_called()
        self.assertEqual(conn.request.call_count, 1)
        self.assertTrue(result['redirect_refused'])
        self.assertNotIn('data', result)
        self.assertNotIn('Location', result)

    def test_gzip_is_bounded_after_decompression(self):
        conn = Mock()
        response = Mock(status=200)
        response.getheader.side_effect = lambda name: 'gzip' if name == 'Content-Encoding' else None
        conn.getresponse.return_value = response
        response.read.return_value = gzip.compress(b'{"Name":"CHA_FAN3"}')
        with patch.object(probe, 'PinnedConnection', return_value=conn):
            result = probe.request('/redfish/v1', auth=False)
            self.assertEqual(result['data'], {'Name': 'CHA_FAN3'})
            response.read.return_value = gzip.compress(b'A' * (16777216 + 1))
            with self.assertRaises(ValueError):
                probe.request('/redfish/v1', auth=False)
        self.assertEqual(conn.request.call_count, 2)

    def test_request_and_time_bounds_precede_connect(self):
        with patch.object(probe, 'PinnedConnection') as conn:
            probe.REQUESTS = 30
            with self.assertRaises(ValueError):
                probe.request('/redfish/v1')
            probe.REQUESTS = 0
            with patch.object(probe.time, 'time', return_value=probe.DEADLINE), self.assertRaises(ValueError):
                probe.request('/redfish/v1')
            conn.assert_not_called()

    def test_filtered_response_drops_secret_fields(self):
        result = probe.filtered({'Name': 'CHA_FAN3', 'Password': 'offline-test-only', 'Token': 'offline-test-only', 'Oem': {'Ami': {'OwnerLUN': 0, 'Password': 'offline-test-only'}}})
        self.assertEqual(result, {'Name': 'CHA_FAN3', 'Oem': {'Ami': {'OwnerLUN': 0}}})

    def parent_stat(self, path):
        return types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=os.getuid())

    def test_credential_restrictive_mode_and_target(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'test-credential.json'
            path.write_text(json.dumps({'host': probe.HOST, 'username': 'sova', 'password': 'offline-test-only'}))
            path.chmod(0o600)
            with patch.object(probe, 'CREDENTIAL', str(path)), patch.object(probe.os, 'lstat', self.parent_stat):
                self.assertEqual(probe.credential()['username'], 'sova')
                path.chmod(0o644)
                with self.assertRaises(ValueError):
                    probe.credential()
                path.chmod(0o600)
                path.write_text(json.dumps({'host': 'elsewhere.invalid', 'username': 'sova', 'password': 'offline-test-only'}))
                with self.assertRaises(ValueError):
                    probe.credential()

    def test_unsafe_parent_rejected_before_file_open(self):
        for mode, uid in ((stat.S_IFDIR | 0o777, os.getuid()), (stat.S_IFLNK | 0o700, os.getuid()), (stat.S_IFDIR | 0o700, os.getuid() + 10000)):
            bad = types.SimpleNamespace(st_mode=mode, st_uid=uid)
            with self.subTest(mode=mode, uid=uid), patch.object(probe.os, 'lstat', return_value=bad), patch.object(probe.os, 'open') as opened:
                with self.assertRaises(ValueError):
                    probe.credential()
                opened.assert_not_called()

    def test_symlink_credential_is_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'target.json'
            path.write_text('{}')
            path.chmod(0o600)
            link = Path(temp) / 'symlink.json'
            link.symlink_to(path)
            with patch.object(probe, 'CREDENTIAL', str(link)), patch.object(probe.os, 'lstat', self.parent_stat), self.assertRaises(OSError):
                probe.credential()


if __name__ == '__main__':
    unittest.main()
