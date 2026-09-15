"""Pinned runtime artifacts, without model activation or lifecycle ownership.

The dispatcher holds the existing global installer/lifecycle lease throughout.
Only the concrete Runner executes commands; injected runners are explicitly
synthetic and cannot produce a production completion contract.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import uuid

from .core import InstallError, Runner, digest, now
from .storage_io import AnchoredRoot

REPO = Path(__file__).resolve().parents[2]
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def runtime_inputs(repo=None, lock=None):
    """Read-only release integrity validation, also consumed by installer plan."""
    repo = Path(repo or REPO)
    lock = lock or json.loads((repo / "scripts/install/versions.lock.json").read_text())
    pins = lock.get("runtimes")
    if not isinstance(pins, dict) or set(pins) != {"glm", "qwen"}:
        raise InstallError("runtime_lock_missing")
    for name, pin in pins.items():
        try:
            expected_proof = "reports/d1-runtime-proof.json" if name == "glm" else "reports/f1a-sglang-proof.json"
            if pin["proof"] != expected_proof:
                raise ValueError()
            if name == "glm" and (pin["profile"] != "configs/runtimes/llama-cpp-v0.4.1-d1.json"
                    or set(pin["build_recipe_sha256"]) != {"containers/llama-cpp/Dockerfile", "containers/llama-cpp/Dockerfile.dockerignore"}):
                raise ValueError()
            proof_bytes = (repo / pin["proof"]).read_bytes()
            if sha(proof_bytes) != pin["proof_sha256"] or pin["platform"] != "linux/amd64":
                raise ValueError()
            proof = json.loads(proof_bytes)
            if name == "glm":
                if (pin["source_repository"] != "https://github.com/ggml-org/llama.cpp"
                        or not re.fullmatch(r"[0-9a-f]{40}", pin["source_revision"])
                        or proof["source_commit"] != pin["source_revision"]):
                    raise ValueError()
                for field in ("image_tag", "jinja_fix_ancestor", "source_release", "cuda_devel",
                              "cuda_runtime", "ubuntu_snapshot", "cuda_architectures", "build_jobs"):
                    if pin[field] != proof[field]:
                        raise ValueError()
                if pin["observed_reference_image_id"] != proof["image_id"]:
                    raise ValueError()
                if pin["build_recipe_sha256"] != proof["build_recipe_sha256"]:
                    raise ValueError()
                for rel, expected in pin["build_recipe_sha256"].items():
                    if sha((repo / rel).read_bytes()) != expected:
                        raise ValueError()
                profile_bytes = (repo / pin["profile"]).read_bytes()
                profile = json.loads(profile_bytes)
                if (sha(profile_bytes) != pin["profile_sha256"]
                        or profile["source_revision"] != pin["source_revision"]
                        or profile["validation"]["image_id"] != pin["observed_reference_image_id"]):
                    raise ValueError()
            elif any(pin[field] != proof[field] for field in ("image", "image_id", "repo_digest")):
                raise ValueError()
        except (KeyError, ValueError, OSError, TypeError):
            raise InstallError("runtime_release_input_drift") from None
    return pins


def runtime_plan(config, repo=None, lock=None):
    pins = runtime_inputs(repo, lock)
    rows = []
    for name in (config.get("model_set") or "").split(","):
        if not name:
            continue
        artifacts = pins[name].get("registry_artifacts", [])
        blobs = {}
        verified = bool(artifacts)
        for artifact in artifacts:
            if artifact.get("status") != "VERIFIED_PRIMARY_REGISTRY_MANIFEST":
                verified = False
                continue
            for item in artifact["layers"] + [{"digest": artifact["config_digest"], "size_bytes": artifact["config_bytes"]}]:
                if item["digest"] in blobs and blobs[item["digest"]] != item["size_bytes"]:
                    raise InstallError("runtime_registry_descriptor_size_conflict")
                blobs[item["digest"]] = item["size_bytes"]
        rows.append({"selection": name, "identity": pins[name],
                     "artifact_download_bytes": sum(blobs.values()) if verified else None,
                     "compressed_blob_descriptors": [{"digest": k, "size_bytes": v} for k, v in sorted(blobs.items())],
                     "byte_status": "exact unique compressed registry config/layers; excludes metadata, source Git and build-package traffic"
                         if verified else "registry compressed transfer sizes unavailable",
                     "effects": ["inspect/reuse verified image or acquire pinned artifact", "bounded disposable CLI/source probes",
                                 "no inference service or model activation"],
                     "acceptance": "runtime artifacts only; I1c service/auth/generation/client acceptance pending"})
    return rows


def _live_group(group):
    """Linux process group members still capable of writing (exclude zombies)."""
    members = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(") ", 1)[1].split()
            if int(fields[2]) == group and fields[0] not in {"Z", "X"}:
                members.append(int(entry.name))
        except (OSError, ValueError, IndexError):
            continue
    return members


def _stop_group(child):
    # Keep the stage's lease/descriptors until every process capable of writing
    # has exited. SIGKILL can wait on uninterruptible I/O; that is deliberately
    # safer than releasing ownership while an old writer can still mutate data.
    if not _live_group(child.pid):
        child.wait()
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 5
    while _live_group(child.pid):
        if time.monotonic() >= deadline:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(0.05)
    child.wait()


def monitored_process(argv, *, cwd, log, anchors, env, timeout=7200, poll=0.2):
    """Linux subprocess with inherited directory FDs and guarded durable output.

    All subprocess-created local paths are relative to a held directory or use
    /proc/self/fd. Cancellation terminates and waits for the process group before
    descriptor release. Docker daemon storage remains the container stage's
    independently verified responsibility.
    """
    for anchor in anchors:
        anchor.check()
    fds = tuple({a.fileno() for a in anchors} | {cwd.fileno(), log.fileno()})
    clean = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
             "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_GLOBAL": "/dev/null",
             "PYTHONDONTWRITEBYTECODE": "1", **env}
    child = None
    deadline = time.monotonic() + timeout
    try:
        child = subprocess.Popen(argv, cwd=f"/proc/self/fd/{cwd.fileno()}", env=clean,
                                 stdout=log.fileno(), stderr=subprocess.STDOUT,
                                 pass_fds=fds, start_new_session=True)
        while child.poll() is None:
            for anchor in anchors:
                anchor.check()
            if time.monotonic() >= deadline:
                raise InstallError("runtime_command_timeout")
            time.sleep(poll)
        if _live_group(child.pid):
            _stop_group(child)
            raise InstallError("runtime_command_descendants_survived")
        for anchor in anchors:
            anchor.check()
        log.fsync()
        if child.returncode:
            raise InstallError("runtime_command_failed")
    except BaseException:
        if child is not None:
            _stop_group(child)
        raise


class RuntimeStage:
    def __init__(self, config, runner, guard, *, repo=None, uid=0, lock=None):
        self.config, self.runner, self.guard, self.uid = config, runner, guard, uid
        self.repo = Path(repo or REPO)
        self.pins = runtime_inputs(self.repo, lock)
        self.selected = (config.get("model_set") or "").split(",")
        if not self.selected or any(x not in self.pins for x in self.selected):
            raise InstallError("runtime_selection_required")
        self.data = Path(config["data_dir"])
        self.evidence_class = "ACTUAL_RUNTIME_PROBES" if isinstance(runner, Runner) else "SYNTHETIC_FIXTURE"
        self._logs = {}

    def _proof(self, name):
        return json.loads((self.repo / self.pins[name]["proof"]).read_text())

    def _identity(self, name):
        return digest({"pin": self.pins[name], "probe_source_sha256": sha(Path(__file__).read_bytes())})

    def _run(self, argv, timeout=120):
        self.guard()
        result = self.runner.run(argv, timeout=timeout)
        self.guard()
        return result.strip()

    def _inspect(self, ref):
        try:
            results = json.loads(self._run(["docker", "image", "inspect", ref]))
        except InstallError as error:
            if error.code in {"command_failed", "command_unavailable_or_timeout"}:
                return None
            raise
        except (ValueError, TypeError):
            raise InstallError("runtime_image_inspection_invalid") from None
        if (not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict)
                or not IMAGE_ID.fullmatch(results[0].get("Id", ""))):
            raise InstallError("runtime_image_inspection_invalid")
        return results[0]

    def _image_valid(self, name, image):
        if not image or image.get("Os") != "linux" or image.get("Architecture") != "amd64":
            return False
        pin = self.pins[name]
        if name == "qwen":
            return image["Id"] == pin["image_id"] and pin["repo_digest"] in image.get("RepoDigests", [])
        config = image.get("Config") or {}
        labels = config.get("Labels") or {}
        return (config.get("Entrypoint") == ["/opt/llama/llama-server"]
                and labels.get("org.opencontainers.image.source") == pin["source_repository"]
                and labels.get("org.opencontainers.image.revision") == pin["source_revision"]
                and labels.get("org.opencontainers.image.version") == pin["source_release"]
                and labels.get("local.d1.cuda.architectures") == pin["cuda_architectures"]
                and (image["Id"] == pin["observed_reference_image_id"]
                     or labels.get("local.installer.runtime-input") == self._identity(name)))

    def _root_check(self):
        if self._run(["docker", "info", "--format", "{{.DockerRootDir}}"] ) != str(self.data / "docker"):
            raise InstallError("runtime_docker_storage_root_mismatch")

    def _record(self, name):
        return f"services/installer/runtime/{name}.json"

    def check(self):
        runtime_inputs(self.repo, {"runtimes": self.pins})
        self.guard()
        try:
            self._root_check()
        except InstallError as error:
            if error.code in {"command_failed", "command_unavailable_or_timeout"}:
                return False
            raise
        with AnchoredRoot(self.data, self.guard, uid=self.uid) as root:
            for name in self.selected:
                if root.stat(self._record(name), missing_ok=True) is None:
                    return False
                record = root.read_json(self._record(name))
                if (record.get("schema_version") != 1 or record.get("input_hash") != self._identity(name)
                        or record.get("evidence_class") != self.evidence_class
                        or record.get("status") != "RUNTIME_ARTIFACT_VERIFIED"
                        or not IMAGE_ID.fullmatch(record.get("image_id", ""))):
                    return False
                image = self._inspect(record["image_id"])
                if not self._image_valid(name, image) or image["Id"] != record["image_id"]:
                    return False
                logs = record.get("evidence_files", {})
                expected = {"version", "help", "devices", "source", "cmake", "packages", "compiler"} if name == "glm" else {"static"}
                if not expected <= set(logs):
                    return False
                for entry in logs.values():
                    if (not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
                            or not entry["path"].startswith("logs/installer/runtime/")
                            or not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", ""))):
                        return False
                    try:
                        with root.open(entry["path"]) as stream:
                            h = hashlib.sha256()
                            while True:
                                block = stream.read(1024 * 1024)
                                if not block:
                                    break
                                h.update(block)
                            if h.hexdigest() != entry["sha256"]:
                                return False
                    except FileNotFoundError:
                        return False
            root.check()
        return True

    def _effect(self, argv, *, root, cwd, temporary, docker_config, label, timeout=7200):
        log_rel = f"logs/installer/runtime/{label}-{uuid.uuid4().hex}.log"
        with root.open(log_rel, os.O_WRONLY | os.O_CREAT | os.O_EXCL) as log:
            env = {"TMPDIR": f"/proc/self/fd/{temporary.fileno()}",
                   "XDG_CACHE_HOME": f"/proc/self/fd/{temporary.fileno()}",
                   "DOCKER_CONFIG": f"/proc/self/fd/{docker_config.fileno()}"}
            if isinstance(self.runner, Runner):
                if not self.runner.writable:
                    raise InstallError("read_only_command_boundary")
                monitored_process(argv, cwd=cwd, log=log,
                                  anchors=[root, cwd, temporary, docker_config], env=env, timeout=timeout)
            else:
                # Explicit command fixture; never treated as actual GPU/image proof.
                output = self.runner.run(argv, timeout=timeout, env=env)
                log.write(output.encode())
                log.fsync()
        h = hashlib.sha256()
        output = bytearray()
        with root.open(log_rel) as log:
            while True:
                chunk = log.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
                if len(output) < 2 * 1024 * 1024:
                    output.extend(chunk)
        self._logs[label] = {"path": log_rel, "sha256": h.hexdigest()}
        return output.decode("utf-8", errors="replace").strip()

    @staticmethod
    def _sandbox(image, *, entrypoint=None, gpu=False):
        args = ["docker", "run", "--rm", "--network", "none", "--read-only", "--log-driver", "none",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--env", "PYTHONDONTWRITEBYTECODE=1",
                "--env", "HOME=/tmp", "--env", "XDG_CACHE_HOME=/tmp"]
        if gpu:
            args += ["--gpus", "all"]
        if entrypoint:
            args += ["--entrypoint", entrypoint]
        return args + [image]

    def _qwen_probe(self):
        proof = self._proof("qwen")
        static = proof["static"]
        options = list(proof["fixtures"]["option_contract"])
        return "\n".join([
            "import argparse, hashlib, importlib.metadata, json",
            "from pathlib import Path",
            "from sglang.srt.server_args import ServerArgs",
            f"root = Path({static['source_root']!r})",
            f"names = {list(static['source_files'])!r}",
            "files = {n: {'sha256':hashlib.sha256((root/n).read_bytes()).hexdigest(), 'bytes':(root/n).stat().st_size} for n in names}",
            f"packages = {{n:importlib.metadata.version(n) for n in {list(static['packages'])!r}}}",
            "parser = argparse.ArgumentParser(); ServerArgs.add_cli_args(parser)",
            f"actions = {{n:parser._option_string_actions.get(n) for n in {options!r}}}",
            "options = {n:None if a is None else {'dest':a.dest,'default':str(a.default),'choices':list(a.choices) if a.choices is not None else None,'help':a.help} for n,a in actions.items()}",
            "print('I1B_RUNTIME_STATIC='+json.dumps({'packages':packages,'source_files':files,'option_contract':options},sort_keys=True))",
        ])

    def _probes(self, name, image, effect):
        iid = image["Id"]
        if name == "qwen":
            output = effect(self._sandbox(iid, entrypoint="python3") + ["-B", "-c", self._qwen_probe()], label="static", timeout=300)
            try:
                lines = [line[len("I1B_RUNTIME_STATIC="):] for line in output.splitlines() if line.startswith("I1B_RUNTIME_STATIC=")]
                if len(lines) != 1:
                    raise ValueError()
                observed = json.loads(lines[0])
            except ValueError:
                raise InstallError("runtime_sglang_probe_invalid") from None
            proof = self._proof(name)
            expected = {k: proof["static"][k] for k in ("packages", "source_files")}
            expected["option_contract"] = proof["fixtures"]["option_contract"]
            if observed != expected:
                raise InstallError("runtime_sglang_source_or_capability_drift")
            return {"source_and_cli_contract": "verified", "native_sentinel_auth": "PENDING_I1C",
                    "gpu_inference": "NOT_TESTED"}
        pin = self.pins[name]
        version = effect(self._sandbox(iid) + ["--version"], label="version", timeout=120)
        help_text = effect(self._sandbox(iid) + ["--help"], label="help", timeout=120)
        devices = effect(self._sandbox(iid, gpu=True) + ["--list-devices"], label="devices", timeout=120)
        profile = json.loads((self.repo / pin["profile"]).read_text())
        if pin["source_revision"][:7] not in version:
            raise InstallError("runtime_version_drift")
        for option in profile["required_cli_flags"]:
            if not re.search(r"(?<![\w-])" + re.escape(option) + r"(?![\w-])", help_text):
                raise InstallError("runtime_cli_capability_missing")
        if len(set(re.findall(r"^\s*(CUDA\d+):", devices, re.MULTILINE))) != self.config["expected_gpu_count"]:
            raise InstallError("runtime_cuda_device_gate_failed")
        outputs = {}
        for label, filename in (("source", "source-commit.txt"), ("cmake", "CMakeCache.txt"),
                                ("packages", "build-packages.tsv"), ("compiler", "nvcc-version.txt")):
            outputs[label] = effect(self._sandbox(iid, entrypoint="/bin/cat") + ["/opt/llama/" + filename], label=label, timeout=120)
        if outputs["source"] != pin["source_revision"]:
            raise InstallError("runtime_image_source_drift")
        required_cmake = {"CMAKE_CUDA_ARCHITECTURES": pin["cuda_architectures"], "GGML_CUDA": "ON",
                          "GGML_NATIVE": "OFF", "GGML_BACKEND_DL": "ON", "GGML_CPU_ALL_VARIANTS": "ON",
                          "LLAMA_BUILD_UI": "OFF", "LLAMA_USE_PREBUILT_UI": "OFF"}
        for key, value in required_cmake.items():
            if not re.search(r"^" + key + r":[^=\n]+=" + re.escape(value) + r"$", outputs["cmake"], re.MULTILINE):
                raise InstallError("runtime_build_configuration_drift")
        if "release 13.2" not in outputs["compiler"] or not outputs["packages"]:
            raise InstallError("runtime_compiler_or_package_evidence_missing")
        return {"source_and_cli_contract": "verified", "cuda_device_enumeration": self.config["expected_gpu_count"],
                "gpu_inference": "NOT_TESTED"}

    def apply(self):
        if isinstance(self.runner, Runner) and not self.runner.writable:
            raise InstallError("read_only_command_boundary")
        self.guard()
        self._root_check()
        if self.check():
            return {"changed": False}
        with AnchoredRoot(self.data, self.guard, uid=self.uid) as root:
            for rel in ("build/installer-runtime", "logs/installer/runtime", "services/installer/runtime"):
                root.mkdir(rel)
            records = []
            for name in self.selected:
                pin = self.pins[name]
                work_rel = "build/installer-runtime/" + name + "-" + self._identity(name)[:16]
                for suffix in ("", "/source", "/tmp", "/docker-client", "/recipe"):
                    root.mkdir(work_rel + suffix)
                with contextlib.ExitStack() as stack:
                    work = stack.enter_context(root.directory(work_rel))
                    source = stack.enter_context(work.directory("source"))
                    temporary = stack.enter_context(work.directory("tmp"))
                    docker_config = stack.enter_context(work.directory("docker-client"))
                    recipe = stack.enter_context(work.directory("recipe"))
                    self._logs = {}
                    def effect(argv, *, label, timeout=7200, cwd=work):
                        return self._effect(argv, root=root, cwd=cwd, temporary=temporary,
                                            docker_config=docker_config, label=label, timeout=timeout)
                    reference = pin["repo_digest"] if name == "qwen" else pin["image_tag"]
                    image = self._inspect(reference)
                    if image is not None and not self._image_valid(name, image):
                        raise InstallError("runtime_existing_image_identity_conflict")
                    if image is None:
                        available = os.fstatvfs(root.fileno())
                        if available.f_bavail * available.f_frsize < pin["minimum_free_build_bytes"]:
                            raise InstallError("runtime_build_capacity_insufficient")
                        if name == "qwen":
                            effect(["docker", "pull", "--platform", pin["platform"], pin["repo_digest"]], label="pull")
                        else:
                            self._build_llama(pin, source, recipe, effect)
                        image = self._inspect(reference)
                    if not self._image_valid(name, image):
                        raise InstallError("runtime_result_image_identity_invalid")
                    capabilities = self._probes(name, image, effect)
                    if self._inspect(image["Id"]) != image:
                        raise InstallError("runtime_image_changed_during_verification")
                    self._root_check()
                    record = {"schema_version": 1, "selection": name, "status": "RUNTIME_ARTIFACT_VERIFIED",
                              "input_hash": self._identity(name), "image_id": image["Id"], "image_inspection": image,
                              "inputs": pin, "evidence_class": self.evidence_class, "evidence_files": self._logs,
                              "capabilities": capabilities, "finished": now(), "ready": False}
                    root.atomic_json(self._record(name), record)
                    records.append(record)
            root.check()
        self.guard()
        if not self.check():
            raise InstallError("runtime_postcondition_failed")
        return {"changed": True, "runtimes": records, "ready": False}

    def _build_llama(self, pin, source, recipe, effect):
        # Git operates entirely inside the held source FD, including partial
        # clone recovery. Existing dirty/conflicting source is preserved/refused.
        if source.stat(".git", missing_ok=True) is None:
            effect(["git", "init", "."], cwd=source, label="git-init")
        try:
            head = effect(["git", "rev-parse", "HEAD"], cwd=source, label="git-head")
        except InstallError as error:
            if error.code != "runtime_command_failed":
                raise
            head = ""
        if not head:
            effect(["git", "fetch", "--no-tags", pin["source_repository"], pin["source_revision"]], cwd=source, label="git-fetch")
            effect(["git", "checkout", "--detach", pin["source_revision"]], cwd=source, label="git-checkout")
        if effect(["git", "rev-parse", "HEAD"], cwd=source, label="git-source") != pin["source_revision"]:
            raise InstallError("runtime_source_revision_drift")
        if effect(["git", "status", "--porcelain", "--untracked-files=all"], cwd=source, label="git-clean"):
            raise InstallError("runtime_source_not_clean")
        effect(["git", "merge-base", "--is-ancestor", pin["jinja_fix_ancestor"], "HEAD"], cwd=source, label="git-ancestry")
        for rel in pin["build_recipe_sha256"]:
            content = (self.repo / rel).read_bytes()
            target = Path(rel).name
            if recipe.stat(target, missing_ok=True) is not None:
                with recipe.open(target) as existing:
                    if existing.read() != content:
                        raise InstallError("runtime_staged_recipe_drift")
            else:
                with recipe.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL) as out:
                    out.write(content)
                    out.fsync()
        # /proc/self/fd recipe is inherited by Docker through source command's
        # anchors. The Dockerfile-specific ignore file includes the clean .git.
        # Use a source-relative ../recipe path, anchored by the held source cwd.
        effect(["docker", "build", "--progress=plain", "--platform", pin["platform"],
                "--build-arg", "LLAMA_COMMIT=" + pin["source_revision"],
                "--build-arg", "CUDA_ARCHITECTURES=" + pin["cuda_architectures"],
                "--build-arg", "BUILD_JOBS=" + str(pin["build_jobs"]),
                "--build-arg", "UBUNTU_SNAPSHOT=" + pin["ubuntu_snapshot"],
                "--build-arg", "CUDA_DEVEL=" + pin["cuda_devel"],
                "--build-arg", "CUDA_RUNTIME=" + pin["cuda_runtime"],
                "--label", "local.installer.runtime-input=" + self._identity("glm"),
                "--tag", pin["image_tag"], "--file", "../recipe/Dockerfile", "."], cwd=source, label="build", timeout=14400)
