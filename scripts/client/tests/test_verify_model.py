"""Local HTTP model identity checks; no VM or generation requests."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify


class ModelHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.paths.append(self.path)
        self.server.auth.append(self.headers.get("Authorization"))
        self.send_response(self.server.code)
        if self.server.code == 302:
            self.send_header("Location", "/unexpected-redirect")
        self.send_header("Content-Length", str(len(self.server.body)))
        self.end_headers()
        self.wfile.write(self.server.body)


class ModelIdentityTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
        self.server.paths, self.server.auth = [], []
        self.server.code = 200
        self.server.body = json.dumps({"data": [{"id": "synthetic"}]}).encode()
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.settings = {"base_url": "http://127.0.0.1:" + str(self.server.server_port) + "/v1", "model": "synthetic"}

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_exact_authenticated_model_discovery_without_generation(self):
        self.assertEqual(verify.observe_model(self.settings, "synthetic-private-key", 2), "synthetic")
        self.assertEqual(self.server.paths, ["/v1/models"])
        self.assertEqual(self.server.auth, ["Bearer synthetic-private-key"])

    def test_wrong_ambiguous_and_malformed_model_list_fail(self):
        for value in ({"data": [{"id": "other"}]}, {"data": []},
                      {"data": [{"id": "synthetic"}, {"id": "other"}]},
                      {"data": [{"id": "synthetic"}, {"id": "synthetic"}]},
                      {"data": "synthetic"}, []):
            self.server.body = json.dumps(value).encode()
            with self.subTest(value=value), self.assertRaises(verify.VerifyError):
                verify.observe_model(self.settings, "synthetic-private-key", 2)

    def test_redirect_never_forwards_credential(self):
        self.server.code = 302
        with self.assertRaisesRegex(verify.VerifyError, "redirect_denied"):
            verify.observe_model(self.settings, "synthetic-private-key", 2)
        self.assertEqual(self.server.paths, ["/v1/models"])

    def test_http_auth_error_retains_only_status_for_caller(self):
        self.server.code = 401
        with self.assertRaises(urllib.error.HTTPError) as caught:
            verify.observe_model(self.settings, "synthetic-private-key", 2)
        self.assertEqual(caught.exception.code, 401)
        caught.exception.close()
        self.assertEqual(self.server.paths, ["/v1/models"])


if __name__ == "__main__":
    unittest.main()
