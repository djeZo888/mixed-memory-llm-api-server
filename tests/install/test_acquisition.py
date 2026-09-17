"""Synthetic local bytes/network fixtures exercising the actual stage engine."""
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from install.acquisition import AcquisitionStage, Cancelled, CHUNK, GIB, capacity_budget, selected_manifests, validate_manifest, validate_response
from install.core import InstallError


class Response(io.BytesIO):
    def __init__(self, payload, size, offset=0, *, status=None, headers=None):
        super().__init__(payload)
        self.status = status or (206 if offset else 200)
        self.headers = {"Content-Length": str(size-offset), "ETag": '"fixture-identity"'}
        if offset:
            self.headers["Content-Range"] = f"bytes {offset}-{size-1}/{size}"
        self.headers.update(headers or {})


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".acq-test-", dir=REPO)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.uid = os.geteuid()
        self.data = self.root / "volume"
        self.data.mkdir(mode=0o700)
        self.roots = {x: str(self.data / x) for x in ("models", "build", "state", "logs", "hf_cache")}
        for p in self.roots.values():
            Path(p).mkdir(mode=0o700)
        device = self.data.stat().st_dev
        mount = {"path": str(self.data), "mount": str(self.data), "uuid": "11111111-2222-4333-8444-555555555555",
                 "fstype": "ext4", "device": f"{os.major(device)}:{os.minor(device)}"}
        self.snapshot = {"schema_version": 1, "data": mount, "models": {**mount, "path": self.roots["models"]}, "roots": self.roots}
        self.present = True
        self.payloads = {"one.bin": b"abc123" * 100, "nested/two.bin": b"z" * 1031}
        self.config = {"model_set": "qwen", "data_dir": str(self.data)}
        self.lock = {"selected_models": {}}
        self.make_manifest()
        self.requests = []
        self.overrides = {}

    def make_manifest(self, selection="qwen"):
        rows = [{"path": path, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                 "git_blob_sha1": hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()}
                for path, data in self.payloads.items()]
        self.manifest = {"schema_version": 1, "repo_id": "fixture/model", "revision": "a"*40,
                         "artifact_count": len(rows), "total_bytes": sum(len(x) for x in self.payloads.values()), "artifacts": rows}
        reports = self.root / "reports"
        reports.mkdir(exist_ok=True)
        raw = json.dumps(self.manifest).encode()
        (reports / (selection + ".json")).write_bytes(raw)
        self.lock["selected_models"][selection] = {"manifest": f"reports/{selection}.json", "sha256": hashlib.sha256(raw).hexdigest(), "directory": selection}

    def guard(self):
        if not self.present:
            raise InstallError("fixture_mount_lost")
        return self.snapshot

    def opener(self, request, timeout):
        path = request.full_url.split("/" + "a"*40 + "/", 1)[1]
        offset = int(request.get_header("Range", "bytes=0-")[6:-1])
        self.requests.append((path, offset))
        payload = self.payloads[path]
        override = self.overrides.get(path)
        if override:
            return override(payload, offset)
        return Response(payload[offset:], len(payload), offset)

    def stage(self, **kwargs):
        stage = AcquisitionStage(self.config, None, self.guard, repo=self.root, uid=self.uid, lock=self.lock,
                                 opener=self.opener, workers=1, attempts=2, retry_delay=0, **kwargs)
        stage.runtime_reserve = 0  # byte-sized synthetic fixtures, production constant unchanged
        return stage

    def dest(self, name):
        return Path(self.roots["models"]) / "qwen" / name

    def contract(self):
        return Path(self.roots["state"]) / "acquisition/qwen.complete.json"


class AcquisitionTests(Fixture):
    def test_exact_reviewed_selections_and_manifest_hashes(self):
        lock = json.loads((REPO / "scripts/install/versions.lock.json").read_text())
        selected = selected_manifests({"model_set": "glm,qwen"}, REPO, lock)
        self.assertEqual([(x["manifest"]["artifact_count"], x["manifest"]["total_bytes"]) for x in selected],
                         [(11, 467289116837), (48, 80407722953)])

    def test_complete_contract_and_noop_rehash_preserve_key_and_expected_source(self):
        key = Path(self.roots["state"]) / "sentinel-key"
        key.write_bytes(b"fixture unchanged key")
        key.chmod(0o600)
        expected = (self.root / "reports/qwen.json").read_bytes()
        stage = self.stage()
        self.assertFalse(stage.check())
        self.assertFalse(self.contract().exists())
        self.assertEqual(stage.apply()["status"], "ACQUISITION_COMPLETE")
        self.assertTrue(self.stage().check())
        self.assertEqual(self.contract().stat().st_mode & 0o777, 0o600)
        contract = json.loads(self.contract().read_text())
        self.assertEqual(contract["verified_bytes"], sum(map(len, self.payloads.values())))
        self.assertEqual(contract["inference"], "NOT_TESTED")
        self.assertEqual((self.root / "reports/qwen.json").read_bytes(), expected)
        self.assertEqual(key.read_bytes(), b"fixture unchanged key")
        for name, content in self.payloads.items():
            self.assertEqual(self.dest(name).read_bytes(), content)
        calls = len(self.requests)
        self.stage().apply()
        self.assertEqual(len(self.requests), calls)

    def test_interruption_resumes_partial_without_losing_peer(self):
        first = self.stage()
        self.overrides["nested/two.bin"] = lambda data, offset: Response(data[offset:offset+17], len(data), offset)
        with self.assertRaisesRegex(InstallError, "download_retry_limit"):
            first.apply()
        self.assertEqual(self.dest("one.bin").read_bytes(), self.payloads["one.bin"])
        partial = self.dest("nested/two.bin.partial")
        self.assertEqual(partial.stat().st_size, 34)
        mtime = self.dest("one.bin").stat().st_mtime_ns
        self.overrides.clear()
        self.requests.clear()
        self.stage().apply()
        self.assertEqual(self.requests, [("nested/two.bin", 34)])
        self.assertEqual(self.dest("one.bin").stat().st_mtime_ns, mtime)
        self.assertTrue(self.stage().check())

    def test_range_mismatch_preserves_existing_partial(self):
        self.dest("one.bin").parent.mkdir()
        partial = self.dest("one.bin.partial")
        partial.write_bytes(self.payloads["one.bin"][:20])
        partial.chmod(0o600)
        self.overrides["one.bin"] = lambda data, offset: Response(data[offset:], len(data), offset, headers={"Content-Range": "bytes 0-599/600"})
        with self.assertRaisesRegex(InstallError, "download_content_range_mismatch"):
            self.stage().apply()
        self.assertEqual(partial.read_bytes(), self.payloads["one.bin"][:20])
        self.assertFalse(self.contract().exists())

    def test_corrupt_hash_quarantines_partial_and_next_resume_retries_only_bad(self):
        self.overrides["nested/two.bin"] = lambda data, offset: Response(b"x"*len(data), len(data))
        with self.assertRaisesRegex(InstallError, "artifact_computed_hash_mismatch"):
            self.stage().apply()
        self.assertEqual(len(list(self.dest("nested").glob("two.bin.partial.rejected.*"))), 1)
        self.assertFalse(self.contract().exists())
        self.overrides.clear()
        self.requests.clear()
        self.stage().apply()
        self.assertEqual(self.requests, [("nested/two.bin", 0)])

    def test_repeated_identical_corruption_does_not_trap_resume(self):
        self.overrides["nested/two.bin"] = lambda data, offset: Response(b"x"*len(data), len(data))
        for _ in range(2):
            with self.assertRaisesRegex(InstallError, "artifact_computed_hash_mismatch"):
                self.stage().apply()
        self.assertEqual(len(list(self.dest("nested").glob("two.bin.partial.rejected.*"))), 2)
        self.assertFalse(self.dest("nested/two.bin.partial").exists())
        self.overrides.clear()
        self.requests.clear()
        self.stage().apply()
        self.assertEqual(self.requests, [("nested/two.bin", 0)])

    def test_completed_marker_cannot_override_changed_bytes_or_manifest(self):
        self.stage().apply()
        self.dest("one.bin").write_bytes(b"x"*len(self.payloads["one.bin"]))
        self.assertFalse(self.stage().check())
        with self.assertRaisesRegex(InstallError, "artifact_computed_hash_mismatch"):
            self.stage().apply()
        self.assertFalse(self.contract().exists())
        self.assertTrue(list(self.contract().parent.glob("qwen.complete.json.prior.*")))
        (self.root / "reports/qwen.json").write_text("{}")
        with self.assertRaisesRegex(InstallError, "selected_manifest_identity_changed"):
            self.stage()

    def test_completion_rechecks_earlier_file_after_last_file_hash(self):
        self.stage().apply()
        stage = self.stage()
        original = stage._hash
        def changed(path, artifact):
            result = original(path, artifact)
            if path.endswith("two.bin"):
                self.dest("one.bin").write_bytes(b"x"*len(self.payloads["one.bin"]))
            return result
        stage._hash = changed
        with self.assertRaisesRegex(InstallError, "artifact_changed_during_completion"):
            stage.apply()
        self.assertFalse(self.contract().exists())

    def test_changed_completion_contract_and_stage_identity_rejected(self):
        self.stage().apply()
        value = json.loads(self.contract().read_text())
        value["revision"] = "b"*40
        self.contract().write_text(json.dumps(value))
        self.assertFalse(self.stage().check())
        self.config["model_set"] = "glm"
        self.make_manifest("glm")
        with self.assertRaisesRegex(InstallError, "acquisition_state_identity_changed"):
            self.stage().apply()

    def test_duplicate_engine_owner_rejected(self):
        one = self.stage()
        with one._roots(), one._owner():
            with self.assertRaisesRegex(InstallError, "acquisition_owner_active"):
                self.stage().apply()
        self.stage().apply()

    def test_mount_loss_after_response_before_write_never_promotes(self):
        def detach(data, offset):
            response = Response(data[offset:], len(data), offset)
            original = response.read
            def read(size):
                result = original(size)
                self.present = False
                return result
            response.read = read
            return response
        self.overrides["one.bin"] = detach
        with self.assertRaisesRegex(InstallError, "fixture_mount_lost"):
            self.stage().apply()
        self.assertFalse(self.dest("one.bin").exists())
        self.assertFalse(self.contract().exists())
        partial = self.dest("one.bin.partial")
        self.assertTrue(partial.exists())
        self.assertEqual(partial.stat().st_size, 0)

    def test_cancellation_preserves_completed_and_partial_bytes(self):
        cancel = threading.Event()
        def stop(data, offset):
            response = Response(data[offset:], len(data), offset)
            original = response.read
            def read(size):
                chunk = original(size)
                cancel.set()
                return chunk
            response.read = read
            return response
        self.overrides["nested/two.bin"] = stop
        with self.assertRaises(Cancelled):
            self.stage(cancel=cancel).apply()
        self.assertTrue(self.dest("one.bin").exists())
        self.assertFalse(self.contract().exists())

    def test_concurrency_is_one_aggregate_pool_for_selected_models(self):
        self.make_manifest("glm")
        self.config["model_set"] = "glm,qwen"
        stage = self.stage()
        stage.workers = 2
        active, maximum = 0, 0
        mutex = threading.Lock()
        original = stage._transfer
        def counted(*args):
            nonlocal active, maximum
            with mutex:
                active += 1
                maximum = max(maximum, active)
            try:
                return original(*args)
            finally:
                with mutex:
                    active -= 1
        stage._transfer = counted
        stage.apply()
        self.assertLessEqual(maximum, 2)
        self.assertEqual(len(self.requests), 4)

    def test_capacity_shared_vs_distinct_and_no_write_when_insufficient(self):
        shared = capacity_budget(self.snapshot, 600, runtime_bytes=100, buffer_bytes=4, reserve=20)
        self.assertEqual(list(shared.values()), [724])
        self.snapshot["models"]["uuid"] = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        distinct = capacity_budget(self.snapshot, 600, runtime_bytes=100, buffer_bytes=4, reserve=20)
        self.assertEqual(sorted(distinct.values()), [120, 624])
        from types import SimpleNamespace
        with patch("install.acquisition.os.fstatvfs", return_value=SimpleNamespace(f_bavail=1, f_frsize=1)):
            with self.assertRaisesRegex(InstallError, "insufficient_aggregate_acquisition_capacity"):
                self.stage().apply()
        self.assertEqual(self.requests, [])

    def test_short_write_retry_accounts_persisted_prefix_at_capacity_boundary(self):
        from types import SimpleNamespace
        from install.acquisition import RESERVE
        stage = self.stage()
        total = sum(map(len, self.payloads.values()))
        original = os.write
        phase = 0
        def short(fd, block):
            nonlocal phase
            value = bytes(block)
            if phase == 0 and value == self.payloads["one.bin"]:
                phase = 1
                return original(fd, value[:10])
            if phase == 1 and value == self.payloads["one.bin"][10:]:
                phase = 2
                raise OSError("fixture interrupted short write")
            return original(fd, block)
        def capacity(_fd):
            used = sum(p.stat().st_size for p in Path(self.roots["models"]).rglob("*") if p.is_file())
            return SimpleNamespace(f_bavail=RESERVE + CHUNK + total - used, f_frsize=1)
        with patch("install.storage_io.os.write", side_effect=short), patch("install.acquisition.os.fstatvfs", side_effect=capacity):
            stage.apply()
        self.assertIn(("one.bin", 10), self.requests)
        self.assertTrue(self.stage().check())

    def test_ambiguous_or_oversize_existing_files_preserved(self):
        self.dest("one.bin").parent.mkdir()
        self.dest("one.bin").write_bytes(self.payloads["one.bin"])
        self.dest("one.bin.partial").write_bytes(b"x")
        with self.assertRaisesRegex(InstallError, "ambiguous_final_and_partial"):
            self.stage().apply()
        self.dest("one.bin.partial").unlink()
        self.dest("one.bin").write_bytes(b"x"*10000)
        with self.assertRaisesRegex(InstallError, "oversize_existing_artifact"):
            self.stage().apply()

    def test_actual_loopback_http_range_transfer(self):
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_GET(self):
                path = self.path[1:]
                data = fixture.payloads[path]
                offset = int(self.headers.get("Range", "bytes=0-")[6:-1])
                fixture.requests.append((path, offset))
                self.send_response(206 if offset else 200)
                self.send_header("Content-Length", str(len(data)-offset))
                if offset:
                    self.send_header("Content-Range", f"bytes {offset}-{len(data)-1}/{len(data)}")
                self.end_headers()
                self.wfile.write(data[offset:])
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.dest("one.bin").parent.mkdir()
        self.dest("one.bin.partial").write_bytes(self.payloads["one.bin"][:15])
        def local(request, timeout):
            path = request.full_url.split("/" + "a"*40 + "/", 1)[1]
            req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/{path}", headers=dict(request.header_items()))
            return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)
        stage = self.stage()
        stage.opener = local
        try:
            stage.apply()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertIn(("one.bin", 15), self.requests)
        self.assertTrue(self.stage().check())


class ProtocolTests(unittest.TestCase):
    def test_response_identity_length_and_encoding_rejections(self):
        cases = [(0, {"Content-Length": "2"}), (0, {"Content-Encoding": "gzip"}),
                 (0, {"X-Repo-Commit": "b"*40}), (4, {"Content-Range": "bytes 4-10/20"})]
        for offset, headers in cases:
            with self.subTest(headers=headers), self.assertRaises(InstallError):
                validate_response(Response(b"a", 10, offset, headers=headers), offset, 10, "a"*40)
        with self.assertRaisesRegex(InstallError, "download_etag_changed"):
            validate_response(Response(b"a", 10, 4), 4, 10, "a"*40, "b"*64)

    def test_manifest_path_and_hash_set_validation(self):
        base = {"schema_version": 1, "repo_id": "fixture/model", "revision": "a"*40, "artifact_count": 1, "total_bytes": 1}
        for path in ("../x", "/x", "one//two", "x.partial", "x/./y"):
            with self.subTest(path=path), self.assertRaises(InstallError):
                validate_manifest({**base, "artifacts": [{"path": path, "size_bytes": 1, "sha256": "a"*64}]})


if __name__ == "__main__":
    unittest.main()
