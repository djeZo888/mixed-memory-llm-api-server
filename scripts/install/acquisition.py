"""Immutable selected-model acquisition on registered storage.

Generalizes D1b/F1A's bounded workers, exact Range, computed SHA, fsync and
atomic promotion protocol. No historical host paths, mutable manifest writes,
HF cache duplicate, lifecycle action or inference claim. The dispatcher holds
the global lifecycle lease; a local FD lock also excludes duplicate engines.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager, ExitStack
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import threading
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import quote, urlsplit

from .core import InstallError, digest, now
from .storage_io import AnchoredRoot

CHUNK = 1024 ** 2
GIB = 1024 ** 3
RESERVE = 20 * GIB


class Cancelled(InstallError):
    def __init__(self):
        super().__init__("acquisition_cancelled")


def validate_manifest(manifest):
    """Generic schema; the lock digest fixes the exact selected file set."""
    if (manifest.get("schema_version") != 1 or
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", manifest.get("repo_id", "")) or
            not re.fullmatch(r"[0-9a-f]{40}", manifest.get("revision", ""))):
        raise InstallError("manifest_identity_invalid")
    rows = manifest.get("artifacts")
    if not isinstance(rows, list) or not rows or len(rows) > 256 or len(rows) != manifest.get("artifact_count"):
        raise InstallError("manifest_artifact_set_invalid")
    paths = []
    for row in rows:
        path = row.get("path", "")
        if (not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_./-]{0,240}", path) or
                any(x in {"", ".", ".."} for x in path.split("/")) or
                any(x.endswith(".partial") or ".rejected." in x for x in path.split("/")) or
                type(row.get("size_bytes")) is not int or row["size_bytes"] <= 0 or
                not re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", ""))):
            raise InstallError("manifest_artifact_invalid")
        if row.get("lfs_sha256") not in (None, row["sha256"]):
            raise InstallError("manifest_lfs_identity_invalid")
        if "git_blob_sha1" in row and not re.fullmatch(r"[0-9a-f]{40}", row["git_blob_sha1"]):
            raise InstallError("manifest_git_identity_invalid")
        paths.append(path)
    if len(set(paths)) != len(paths) or any(str(p) in paths for path in paths for p in PurePosixPath(path).parents if str(p) != "."):
        raise InstallError("manifest_path_collision")
    if sum(row["size_bytes"] for row in rows) != manifest.get("total_bytes"):
        raise InstallError("manifest_size_mismatch")
    return rows


def selected_manifests(config, repo, lock):
    result = []
    for selection in config["model_set"].split(","):
        pin = lock.get("selected_models", {}).get(selection)
        if not pin or selection not in {"glm", "qwen"}:
            raise InstallError("selected_manifest_lock_missing")
        relative = pin["manifest"]
        if not re.fullmatch(r"reports/[A-Za-z0-9_.-]+\.json", relative):
            raise InstallError("manifest_source_path_invalid")
        raw = (Path(repo) / relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != pin["sha256"]:
            raise InstallError("selected_manifest_identity_changed")
        manifest = json.loads(raw)
        validate_manifest(manifest)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", pin["directory"]):
            raise InstallError("manifest_destination_invalid")
        result.append({"selection": selection, "sha256": pin["sha256"],
                       "directory": pin["directory"], "manifest": manifest})
    if len({x["directory"] for x in result}) != len(result):
        raise InstallError("manifest_destination_collision")
    return result


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise InstallError("unsafe_download_redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_download(request, timeout=90):
    # No ambient token, netrc or proxy credentials are read by the engine.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), HTTPSRedirect()).open(request, timeout=timeout)


def validate_response(response, offset, size, revision, previous_etag=None):
    if response.headers.get("Content-Encoding", "identity") != "identity":
        raise InstallError("download_content_encoding_changed")
    if offset:
        if response.status != 206 or response.headers.get("Content-Range") != f"bytes {offset}-{size-1}/{size}":
            raise InstallError("download_content_range_mismatch")
    elif response.status != 200 or response.headers.get("Content-Range"):
        raise InstallError("download_initial_response_invalid")
    if response.headers.get("Content-Length") != str(size - offset):
        raise InstallError("download_content_length_mismatch")
    if response.headers.get("X-Repo-Commit", revision) != revision:
        raise InstallError("download_revision_changed")
    etag = response.headers.get("ETag")
    etag_hash = hashlib.sha256(etag.encode()).hexdigest() if etag else None
    if previous_etag and etag_hash != previous_etag:
        raise InstallError("download_etag_changed")
    return etag_hash


def capacity_budget(snapshot, remaining, *, runtime_bytes, buffer_bytes, reserve=RESERVE):
    """One reserve per UUID; data build/cache and all models are aggregated."""
    data, models = snapshot["data"]["uuid"], snapshot["models"]["uuid"]
    required = {data: runtime_bytes + reserve}
    if models != data:
        required[models] = reserve
    required[models] += remaining + buffer_bytes
    return required


class AcquisitionStage:
    def __init__(self, config, runner, guard, *, repo=None, uid=0, lock=None,
                 opener=None, workers=4, attempts=6, cancel=None, retry_delay=1):
        self.config, self.runner, self.guard, self.uid = config, runner, guard, uid
        self.repo = Path(repo or Path(__file__).resolve().parents[2])
        self.lock = lock or json.loads((self.repo / "scripts/install/versions.lock.json").read_text())
        self.selections = selected_manifests(config, self.repo, self.lock)
        if type(workers) is not int or not 1 <= workers <= 4 or type(attempts) is not int or not 1 <= attempts <= 6:
            raise InstallError("acquisition_worker_or_retry_bound")
        self.workers, self.attempts = workers, attempts
        self.opener = opener or open_download
        self.cancel = cancel or threading.Event()
        self.retry_delay = retry_delay
        self.mutex = threading.RLock()
        self.runtime_reserve = sum(100 if x["selection"] == "glm" else 40 for x in self.selections) * GIB
        self.records = {}
        self.last_save = 0

    def _cancelled(self):
        if self.cancel.is_set():
            raise Cancelled()

    @contextmanager
    def _roots(self):
        snapshot = self.guard()
        with ExitStack() as stack:
            self.data = stack.enter_context(AnchoredRoot(snapshot["roots"]["build"], self.guard, uid=self.uid))
            self.models = stack.enter_context(AnchoredRoot(snapshot["roots"]["models"], self.guard, uid=self.uid))
            self.state = stack.enter_context(AnchoredRoot(snapshot["roots"]["state"], self.guard, uid=self.uid))
            self.identity = {"schema_version": 1, "selections": [{k: s[k] for k in ("selection", "sha256", "directory")} for s in self.selections],
                             "storage": {key: {f: snapshot[key][f] for f in ("path", "mount", "uuid", "fstype")} for key in ("data", "models")}}
            yield

    @contextmanager
    def _owner(self):
        with self.state.open("acquisition.owner", os.O_CREAT | os.O_RDWR) as owner:
            try:
                fcntl.flock(owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise InstallError("acquisition_owner_active") from None
            # Close-only release, consistent with the canonical lease handoff.
            # No descriptor is exported or inherited by a subprocess here.
            yield

    def _rows(self):
        for selected in self.selections:
            for artifact in selected["manifest"]["artifacts"]:
                yield selected, artifact, selected["directory"] + "/" + artifact["path"]

    def _present(self, path, size):
        final = self.models.stat(path, missing_ok=True)
        partial = self.models.stat(path + ".partial", missing_ok=True)
        if final and partial:
            raise InstallError("ambiguous_final_and_partial")
        st = final or partial
        if st and st.st_size > size:
            raise InstallError("oversize_existing_artifact")
        return final, partial, st.st_size if st else 0

    def _capacity(self, *, scan=False, enforce=True):
        # Called under the mutex before each write, preventing workers from
        # independently reserving the same free capacity.
        snapshot = self.guard()
        remaining = sum(a["size_bytes"] - (self._present(p, a["size_bytes"])[2] if scan else self.records[p]["bytes_present"])
                        for _, a, p in self._rows())
        required = capacity_budget(snapshot, remaining, runtime_bytes=self.runtime_reserve,
                                   buffer_bytes=self.workers * CHUNK)
        available = {}
        for root, key in ((self.data, "data"), (self.models, "models")):
            root.check()
            vfs = os.fstatvfs(root.fileno())
            free = vfs.f_bavail * vfs.f_frsize
            fs = snapshot[key]["uuid"]
            available[fs] = min(available.get(fs, free), free)
        sufficient = all(available[key] >= value for key, value in required.items())
        if enforce and not sufficient:
            raise InstallError("insufficient_aggregate_acquisition_capacity")
        return {"remaining_bytes": remaining, "required_by_uuid": required, "available_by_uuid": available,
                "space_status": "sufficient_for_remaining_reservation" if sufficient else "insufficient",
                "hash_status": "not_checked_by_capacity_scan"}

    def plan_remaining(self):
        """Read-only on already registered roots; actual sizes, no hash claim."""
        with self._roots():
            return self._capacity(scan=True, enforce=False)

    def _save(self, status="running", force=False):
        with self.mutex:
            if not force and time.monotonic() - self.last_save < 15:
                return
            self.state.atomic_json("acquisition/status.json", {**self.identity, "status": status,
                "updated": now(), "workers": self.workers, "files": self.records})
            self.last_save = time.monotonic()

    def _hash(self, path, artifact):
        sha = hashlib.sha256()
        git = hashlib.sha1(f'blob {artifact["size_bytes"]}\0'.encode()) if artifact.get("git_blob_sha1") else None
        count = 0
        with self.models.open(path) as stream:
            before = stream.stat()
            while True:
                self._cancelled()
                block = stream.read(CHUNK)
                if not block:
                    break
                sha.update(block)
                if git is not None:
                    git.update(block)
                count += len(block)
            after = stream.stat()
        fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if fingerprint(before) != fingerprint(after):
            raise InstallError("artifact_changed_during_hash")
        valid = count == artifact["size_bytes"] and sha.hexdigest() == artifact["sha256"]
        if artifact.get("git_blob_sha1"):
            valid = valid and git.hexdigest() == artifact["git_blob_sha1"]
        return valid, sha.hexdigest(), fingerprint(after)

    def _contract(self, selected, verified):
        manifest = selected["manifest"]
        return {"schema_version": 1, "status": "COMPLETE_COMPUTED_SHA256", "selection": selected["selection"],
                "manifest_sha256": selected["sha256"], "repo_id": manifest["repo_id"], "revision": manifest["revision"],
                "destination": str(Path(self.models.path) / selected["directory"]), "storage": self.identity["storage"],
                "artifact_count": manifest["artifact_count"], "verified_bytes": manifest["total_bytes"], "artifacts": verified,
                "inference": "NOT_TESTED", "authentication": "NOT_TESTED", "tool_calls": "NOT_TESTED"}

    @staticmethod
    def _fingerprint(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    def _unchanged(self, fingerprints):
        for path, expected in fingerprints:
            if self._fingerprint(self.models.stat(path)) != expected:
                raise InstallError("artifact_changed_during_completion")

    def _invalidate_contracts(self):
        # Keep old proof as audit history, outside the lifecycle-consumed name.
        for selected in self.selections:
            name = "acquisition/" + selected["selection"] + ".complete.json"
            if self.state.stat(name, missing_ok=True) is not None:
                self.state.replace(name, name + ".prior." + uuid.uuid4().hex)

    def _verify(self, *, publish=False):
        contracts, fingerprints = [], []
        for selected in self.selections:
            verified = []
            for artifact in selected["manifest"]["artifacts"]:
                path = selected["directory"] + "/" + artifact["path"]
                final, partial, _ = self._present(path, artifact["size_bytes"])
                if not final or partial:
                    return False
                valid, computed, fingerprint = self._hash(path, artifact)
                if not valid:
                    return False
                fingerprints.append((path, fingerprint))
                verified.append({"path": artifact["path"], "size_bytes": artifact["size_bytes"], "computed_sha256": computed})
            expected = self._contract(selected, verified)
            name = "acquisition/" + selected["selection"] + ".complete.json"
            contracts.append((name, expected))
        self._unchanged(fingerprints)
        for name, expected in contracts:
            if publish:
                self._cancelled()
                self._unchanged(fingerprints)
                self.state.atomic_json(name, {**expected, "completed": now()})
            else:
                if self.state.stat(name, missing_ok=True) is None:
                    return False
                actual = self.state.read_json(name)
                if {k: v for k, v in actual.items() if k != "completed"} != expected:
                    return False
        self._unchanged(fingerprints)
        return True

    def check(self):
        with self._roots():
            return self._verify()

    def _transfer(self, selected, artifact, path):
        self._cancelled()
        with self.mutex:
            final, partial, offset = self._present(path, artifact["size_bytes"])
        row = self.records[path]
        if not final:
            for attempt in range(self.attempts):
                self._cancelled()
                with self.mutex:
                    _, _, offset = self._present(path, artifact["size_bytes"])
                    row["bytes_present"] = offset
                    self._capacity()
                    previous_etag = row.get("etag_sha256") if offset else None
                if offset == artifact["size_bytes"]:
                    break
                m = selected["manifest"]
                url = "https://huggingface.co/" + m["repo_id"] + "/resolve/" + m["revision"] + "/" + quote(artifact["path"], safe="/")
                headers = {"Accept-Encoding": "identity"}
                if offset:
                    headers["Range"] = f"bytes={offset}-"
                try:
                    with self.opener(urllib.request.Request(url, headers=headers), timeout=90) as response:
                        etag = validate_response(response, offset, artifact["size_bytes"], m["revision"], previous_etag)
                        with self.mutex:
                            row.update(status="downloading", attempt=row.get("attempt", 0) + 1, etag_sha256=etag)
                            self._save(force=True)
                        with self.models.open(path + ".partial", os.O_CREAT | os.O_WRONLY | os.O_APPEND) as stream:
                            if stream.stat().st_size != offset:
                                raise InstallError("partial_offset_changed")
                            try:
                                while True:
                                    self._cancelled()
                                    block = response.read(min(CHUNK, artifact["size_bytes"] - offset + 1))
                                    if not block:
                                        break
                                    if offset + len(block) > artifact["size_bytes"]:
                                        raise InstallError("download_body_exceeds_expected_size")
                                    with self.mutex:
                                        self._cancelled()
                                        self._capacity()
                                        try:
                                            stream.write(block)
                                        finally:
                                            # A short write followed by EIO may have
                                            # persisted a prefix. Account for it before
                                            # another worker reserves or retries.
                                            row["bytes_present"] = stream.stat().st_size
                                        offset += len(block)
                                        if row["bytes_present"] != offset:
                                            raise InstallError("partial_offset_changed")
                                        self._save()
                            finally:
                                stream.fsync()
                    if offset != artifact["size_bytes"]:
                        raise OSError("truncated transfer")
                    break
                except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException):
                    self._cancelled()
                    if attempt == self.attempts - 1:
                        raise InstallError("download_retry_limit") from None
                    if self.cancel.wait(min(self.retry_delay * 2 ** attempt, 30)):
                        raise Cancelled()
        target = path if final else path + ".partial"
        valid, computed, fingerprint = self._hash(target, artifact)
        if not valid:
            # Preserve bad bytes without trapping the next resume on the same
            # bad full partial. Other completed shards remain untouched.
            if not final:
                with self.mutex:
                    rejected = target + ".rejected." + computed + "." + uuid.uuid4().hex
                    if self.models.stat(rejected, missing_ok=True) is not None:
                        raise InstallError("acquisition_quarantine_collision")
                    self.models.replace(target, rejected)
            raise InstallError("artifact_computed_hash_mismatch")
        with self.mutex:
            self._cancelled()
            if not final:
                if self.models.stat(path, missing_ok=True) is not None:
                    raise InstallError("final_appeared_during_transfer")
                with self.models.open(target) as stream:
                    st = stream.stat()
                    if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns) != fingerprint:
                        raise InstallError("artifact_changed_before_promotion")
                    stream.fsync()
                self.models.replace(target, path)
            row.update(status="verified", bytes_present=artifact["size_bytes"], computed_sha256=computed)
            self._save(force=True)

    def apply(self):
        with self._roots(), self._owner():
            self.state.mkdir("acquisition")
            saved = self.state.stat("acquisition/status.json", missing_ok=True)
            if saved:
                previous = self.state.read_json("acquisition/status.json")
                if any(previous.get(k) != v for k, v in self.identity.items()):
                    raise InstallError("acquisition_state_identity_changed")
                self.records = previous.get("files", {})
                if not isinstance(self.records, dict):
                    raise InstallError("acquisition_state_invalid")
            try:
                if self._verify():
                    return {"status": "ACQUISITION_COMPLETE", "changed": False, "ready": False}
            except BaseException:
                try:
                    self._invalidate_contracts()
                except Exception:
                    pass  # observed mount loss must not redirect audit writes
                raise
            self._invalidate_contracts()
            for _, artifact, path in self._rows():
                self.models.mkdir(str(PurePosixPath(path).parent))
                _, _, present = self._present(path, artifact["size_bytes"])
                row = self.records.setdefault(path, {})
                row.update(bytes_present=present, status="pending")
            self._capacity()
            self._save(force=True)
            old_handlers = {}
            if threading.current_thread() is threading.main_thread():
                for sig in (signal.SIGINT, signal.SIGTERM):
                    old_handlers[sig] = signal.signal(sig, lambda *_: self.cancel.set())
            try:
                errors = []
                def worker(selected, artifact, path):
                    try:
                        self._transfer(selected, artifact, path)
                    except BaseException as exc:
                        self.cancel.set()
                        with self.mutex:
                            self.records[path]["status"] = "cancelled" if isinstance(exc, Cancelled) else "failed"
                        raise
                with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="installer-acquire") as pool:
                    futures = [pool.submit(worker, s, a, p) for s, a, p in self._rows()]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except BaseException as exc:
                            self.cancel.set()
                            errors.append(exc)
                if errors:
                    raise next((e for e in errors if not isinstance(e, Cancelled)), errors[0])
                if not self._verify(publish=True):
                    raise InstallError("acquisition_completion_rejected")
                self._save(status="complete", force=True)
                return {"status": "ACQUISITION_COMPLETE", "ready": False,
                        "contracts": ["acquisition/" + s["selection"] + ".complete.json" for s in self.selections]}
            except BaseException:
                self.cancel.set()
                try:
                    self._invalidate_contracts()
                    self._save(status="interrupted_or_failed", force=True)
                except Exception:
                    pass  # detached storage: leave previous protected state intact
                raise
            finally:
                for sig, handler in old_handlers.items():
                    signal.signal(sig, handler)
