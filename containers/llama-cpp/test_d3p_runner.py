#!/usr/bin/env python3
"""Focused source runner contracts; no Docker, VM, root writes or installation.

Run: PYTHONDONTWRITEBYTECODE=1 python3 containers/llama-cpp/test_d3p_runner.py

The shell runs from a temporary copy with only fixed host paths/interpreter
translated. Fake commands provide Linux metadata and registered guard results.
The real shell closure hash/mode/link checks, branch selection, exact build argv,
report paths and exit behavior run unchanged. UID 0 is simulated, never acquired.
These tests do not establish installed Linux guard or runtime build acceptance.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


RECIPE = Path(__file__).resolve().parent
REPO = RECIPE.parents[1]
PATCH = "43e4aeb5b63dbb82d7457526000391ba52d49a408040ec736fb302092e734f3b"
TREE = "0075e6f2ca5b8a3f13c0725e35f60a0ceb2b2b5e"
CLOSURE = ("scripts/common/registered-storage.py", "scripts/install/storage.py")

# Only this fake dispatcher reads the test environment. No production CLI,
# environment override, host path or privilege policy is added by the harness.
FAKE_COMMAND = r'''
import hashlib, json, os, pathlib, stat, sys
p = pathlib.Path
root = p(os.environ["D3BR_FIXTURE"])
name, args = p(sys.argv[0]).name, sys.argv[1:]
def event(kind, argv):
    with (root / "events.jsonl").open("a") as stream:
        stream.write(json.dumps({"kind": kind, "args": argv,
                                 "home": os.environ.get("HOME")}) + "\n")
def stop():
    print("STOP: fake guard rejected fixture", file=sys.stderr)
    raise SystemExit(1)
if name == "realpath":
    print(p(args[-1]).resolve(strict=True))
elif name == "stat":
    field, path = args[1], p(args[2])
    info = path.lstat()
    if field == "%d": print(info.st_dev)
    elif field == "%h": print(info.st_nlink)
    elif field == "%u": print(501 if str(path) == os.environ.get("D3BR_UNOWNED") else 0)
    elif field == "%a":
        # The real host's /tmp ancestors are outside the simulated root.
        mode = stat.S_IMODE(info.st_mode) if path == root or root in path.parents else 0o755
        print(format(mode, "o"))
    else: raise AssertionError(args)
elif name == "sha256sum":
    for path in args:
        print(hashlib.sha256(p(path).read_bytes()).hexdigest() + "  " + path)
elif name == "git":
    event("git", args)
    if "status" in args: print(os.environ.get("D3BR_DIRTY", ""), end="")
    elif args[-2:] == ["rev-parse", "HEAD"]: print("e" * 40)
    else: raise AssertionError(args)
elif name == "flock":
    event("flock", args)
elif name == "df":
    print("Avail\n214748364800")
elif name == "sudo":
    event("sudo", args)
    assert args[0] == "-n", args
    args = args[1:]
    if "registered-storage.py" in " ".join(args):
        assert args[:3] == [sys.executable, "-I", "-B"], args
        event("registered", args[4:])
        parent = root / "etc/local-ai-server"
        registry = parent / "storage.json"
        if not registry.is_file() or parent.is_symlink() or registry.is_symlink(): stop()
        if parent.stat().st_mode & 0o022 or registry.stat().st_mode & 0o022: stop()
        try: value = json.loads(registry.read_text())
        except ValueError: stop()
        if value.get("reject"): stop()
        if "--json" in args: print(json.dumps(value))
        elif "--root-guard" in args and "--report" in args:
            report = p(args[args.index("--report") + 1])
            logs = root / "data/logs"
            if logs not in report.parents or not report.parent.is_dir(): stop()
            for ancestor in (report, *report.parents):
                if ancestor == root: break
                if ancestor.is_symlink(): stop()
                if ancestor.exists() and ancestor.stat().st_mode & 0o022: stop()
            report.write_text(json.dumps(value))
            report.chmod(0o600)
            event("report", [str(report)])
        else: raise AssertionError(args)
    elif args[0] == "env":
        args = args[1:]
        while args and "=" in args[0]: args = args[1:]
        assert args[0] == "docker", args
        args = args[1:]
        event("docker", args)
        if args[:1] == ["info"]: print(root / "data/docker")
        elif args[:1] == ["build"]:
            if os.environ.get("D3BR_TRANSITION") == "disappear":
                (root / "etc/local-ai-server/storage.json").unlink()
                (root / "etc/local-ai-server").rmdir()
            elif os.environ.get("D3BR_TRANSITION") == "appear":
                parent = root / "etc/local-ai-server"
                parent.mkdir(mode=0o700, parents=True)
                (parent / "storage.json").write_text((root / "registration-template.json").read_text())
                (parent / "storage.json").chmod(0o600)
            p(args[args.index("--iidfile") + 1]).write_text("sha256:" + "a" * 64 + "\n")
        elif args[:2] == ["image", "inspect"]: print("sha256:" + "a" * 64 + " amd64 linux {}")
        else: raise AssertionError(args)
    elif args[0] == "awk": print(root / "data/containerd/root")
    else: raise AssertionError(args)
elif name in ("storage_guard.py", "require-data-mounted.sh", "root-disk-guard.sh", "prepare-d3p-source.py"):
    event(name, args)
    if os.environ.get("D3BR_FAIL") == name: stop()
    if name == "root-disk-guard.sh":
        assert args[0] == "--report"
        p(args[1]).write_text("fake legacy report\n")
        event("report", [args[1]])
    elif name == "prepare-d3p-source.py":
        assert args[-1] == "--check-only", args
        print('{"source_state":"verified-upstream"}')
else: raise AssertionError((name, args))
'''


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="d3br-runner-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.run = self.root / "data/build/d3p-fixture"
        self.repo = self.run / "repo"
        self.recipe = self.repo / "containers/llama-cpp"
        self.logs = self.root / "data/logs/d3p-fixture"
        self.registry_parent = self.root / "etc/local-ai-server"
        self.registry = self.registry_parent / "storage.json"
        self.control = self.root / "control-api"
        self.bin = self.root / "bin"
        for path in (self.recipe, self.run / "source", self.run / "tmp",
                     self.run / "evidence", self.logs, self.bin):
            path.mkdir(parents=True, mode=0o700)
        self.env = dict(os.environ, D3BR_FIXTURE=str(self.root),
                        PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
                        PYTHONDONTWRITEBYTECODE="1")
        self.original_home = os.environ.get("HOME")
        script = "#!" + sys.executable + "\n" + FAKE_COMMAND
        for name in ("realpath", "stat", "sha256sum", "git", "flock", "df", "sudo"):
            self.write_executable(self.bin / name, script)
        for relative in ("scripts/d1/storage_guard.py", "scripts/common/require-data-mounted.sh",
                         "scripts/common/root-disk-guard.sh", "containers/llama-cpp/prepare-d3p-source.py"):
            self.write_executable(self.repo / relative, script)
        for relative in CLOSURE:
            destination = self.control / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, destination)
            destination.chmod(0o644)
        for name in ("Dockerfile.d3p", "Dockerfile.d3p.dockerignore", "d3p-source.json", "strict-model-chat.patch"):
            shutil.copyfile(RECIPE / name, self.recipe / name)
        source = (RECIPE / "build-d3p-runtime.sh").read_text()
        source = source.replace("/usr/local/lib/llm-server/control-api", str(self.control))
        source = source.replace("/etc/local-ai-server", str(self.registry_parent))
        source = source.replace("/etc/containerd/config.toml", str(self.root / "etc/containerd/config.toml"))
        source = source.replace("/data", str(self.root / "data"))
        source = source.replace("/usr/bin/python3", sys.executable)
        self.runner = self.recipe / "build-d3p-runtime.sh"
        self.write_executable(self.runner, source)
        self.registration = {
            "data": {"path": str(self.root / "data"), "mount": str(self.root / "data")},
            "models": {"path": str(self.root / "data/models-large"), "mount": str(self.root / "data/models-large")},
            "roots": {"logs": str(self.root / "data/logs")},
        }
        (self.root / "registration-template.json").write_text(json.dumps(self.registration))

    @staticmethod
    def write_executable(path, source):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        path.chmod(0o755)

    def register(self):
        self.registry_parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.registry.write_text(json.dumps(self.registration))
        self.registry.chmod(0o600)

    def execute(self, *, dry_run=False):
        args = ["bash", str(self.runner)]
        if dry_run:
            args.append("--dry-run")
        result = subprocess.run(args + [str(self.run)], env=self.env,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(os.environ.get("HOME"), self.original_home)
        for event in self.events():
            self.assertEqual(event["home"], self.original_home)
        return result

    def events(self, kind=None):
        path = self.root / "events.jsonl"
        events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [event for event in events if kind is None or event["kind"] == kind]

    def assert_refused_before_docker_or_report(self):
        result = self.execute()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.events("docker"))
        self.assertFalse(self.events("report"))
        self.assertFalse(self.events("storage_guard.py"))
        self.assertFalse(list(self.run.joinpath("evidence").iterdir()))

    def test_registered_success_exact_docker_command_reports_and_home(self):
        self.register()
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.run / "build.state").read_text(), "PASS_BUILD_ONLY\n")
        self.assertEqual([Path(e["args"][0]) for e in self.events("report")],
                         [self.logs / "root-build-before.json", self.logs / "root-build-after.json"])
        self.assertFalse(self.events("storage_guard.py"))
        self.assertFalse(self.events("require-data-mounted.sh"))
        self.assertFalse(self.events("root-disk-guard.sh"))
        image = "local/llama-cpp:v0.4.1-b29c606-cu132-sm120-d3p-" + PATCH[:12]
        builds = [e["args"] for e in self.events("docker") if e["args"][0] == "build"]
        self.assertEqual(builds, [[
            "build", "--progress=plain", "--platform", "linux/amd64",
            "--build-context", "d3p=" + str(self.recipe),
            "--build-arg", "D3P_PATCH_SHA256=" + PATCH, "--build-arg", "D3P_DERIVED_TREE=" + TREE,
            "--build-arg", "CUDA_ARCHITECTURES=120a-real", "--build-arg", "BUILD_JOBS=8",
            "--build-arg", "UBUNTU_SNAPSHOT=20260914T000000Z",
            "--iidfile", str(self.run / "evidence/image.iid"), "-t", image,
            "-f", str(self.recipe / "Dockerfile.d3p"), str(self.run / "source")]])
        self.assertEqual(len(self.events("prepare-d3p-source.py")), 2)

    def test_registered_dry_run_has_no_reports_docker_or_build_evidence(self):
        self.register()
        result = self.execute(dry_run=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS_SOURCE_PREFLIGHT_ONLY", result.stdout)
        self.assertFalse(self.events("docker"))
        self.assertFalse(self.events("report"))
        self.assertFalse(self.events("flock"))
        self.assertFalse(list((self.run / "evidence").iterdir()))

    def test_registration_parent_with_missing_registry_refuses(self):
        self.registry_parent.mkdir(parents=True)
        self.assert_refused_before_docker_or_report()

    def test_malformed_registry_refuses(self):
        self.register()
        self.registry.write_text("{broken")
        self.assert_refused_before_docker_or_report()

    def test_unsafe_registry_refuses(self):
        self.register()
        self.registry.chmod(0o666)
        self.assert_refused_before_docker_or_report()

    def test_symlink_registration_parent_refuses(self):
        self.registry_parent.parent.mkdir(parents=True)
        self.registry_parent.symlink_to(self.root / "absent-registry")
        self.assert_refused_before_docker_or_report()

    def test_incomplete_verified_metadata_refuses(self):
        self.registration.pop("models")
        self.register()
        self.assert_refused_before_docker_or_report()

    def test_wrong_verified_data_path_refuses(self):
        self.registration["data"]["path"] = str(self.root / "other")
        self.register()
        self.assert_refused_before_docker_or_report()

    def test_wrong_verified_model_mount_refuses(self):
        self.registration["models"]["mount"] = str(self.root / "data")
        self.register()
        self.assert_refused_before_docker_or_report()

    def test_wrong_verified_logs_root_refuses(self):
        self.registration["roots"]["logs"] = str(self.root / "outside-logs")
        self.register()
        self.assert_refused_before_docker_or_report()

    def test_missing_closure_file_refuses(self):
        self.register()
        (self.control / CLOSURE[1]).unlink()
        self.assert_refused_before_docker_or_report()

    def test_tampered_closure_bytes_refuse(self):
        self.register()
        path = self.control / CLOSURE[0]
        path.write_bytes(path.read_bytes() + b"\n")
        self.assert_refused_before_docker_or_report()

    def test_writable_closure_ancestor_refuses(self):
        self.register()
        (self.control / "scripts").chmod(0o777)
        self.assert_refused_before_docker_or_report()

    def test_unowned_closure_file_refuses(self):
        self.register()
        self.env["D3BR_UNOWNED"] = str(self.control / CLOSURE[0])
        self.assert_refused_before_docker_or_report()

    def test_hardlinked_closure_file_refuses(self):
        self.register()
        os.link(self.control / CLOSURE[0], self.root / "linked-guard.py")
        self.assert_refused_before_docker_or_report()

    def test_symlink_closure_file_refuses(self):
        self.register()
        path = self.control / CLOSURE[0]
        target = self.root / "linked-guard.py"
        path.rename(target)
        path.symlink_to(target)
        self.assert_refused_before_docker_or_report()

    def test_missing_registered_report_directory_refuses_before_docker(self):
        self.register()
        self.logs.rmdir()
        self.assert_refused_before_docker_or_report()

    def test_symlink_registered_report_directory_refuses_before_docker(self):
        self.register()
        self.logs.rmdir()
        self.logs.symlink_to(self.run / "evidence")
        self.assert_refused_before_docker_or_report()

    def test_legacy_branch_keeps_guards_and_report_placement(self):
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.events("registered"))
        self.assertGreaterEqual(len(self.events("storage_guard.py")), 2)
        self.assertGreaterEqual(len(self.events("require-data-mounted.sh")), 2)
        self.assertEqual([Path(e["args"][0]) for e in self.events("report")],
                         [self.run / "evidence/root-build-before.md", self.run / "evidence/root-build-after.md"])

    def test_legacy_guard_failure_stops_before_docker_or_report(self):
        self.env["D3BR_FAIL"] = "storage_guard.py"
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.events("require-data-mounted.sh"))
        self.assertFalse(self.events("docker"))
        self.assertFalse(self.events("report"))

    def test_registration_disappearance_never_falls_back(self):
        self.register()
        self.env["D3BR_TRANSITION"] = "disappear"
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.events("storage_guard.py"))
        self.assertFalse(self.events("require-data-mounted.sh"))
        self.assertEqual(len(self.events("report")), 1)
        self.assertFalse((self.run / "build.exit").exists())
        self.assertNotEqual((self.run / "build.state").read_text(), "PASS_BUILD_ONLY\n")

    def test_registration_appearance_uses_registered_final_guard(self):
        self.env["D3BR_TRANSITION"] = "appear"
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual([Path(e["args"][0]) for e in self.events("report")],
                         [self.run / "evidence/root-build-before.md", self.logs / "root-build-after.json"])


class ExistingReportWriterTests(unittest.TestCase):
    """Exercise the existing writer directly with a fake storage interface only."""
    def setUp(self):
        spec = importlib.util.spec_from_file_location("d3br_registered_guard", REPO / CLOSURE[0])
        self.guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.guard)
        self.temporary = tempfile.TemporaryDirectory(prefix="d3br-report-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.logs = self.root / "logs"
        self.logs.mkdir()
        self.report = self.logs / "task/root-before.json"
        self.report.parent.mkdir()
        self.result = {"roots": {"logs": str(self.logs)}}
        self.instance = mock.Mock()
        self.instance._path.side_effect = str
        self.instance._no_symlink.side_effect = lambda value, **kwargs: Path(value)

    def test_writer_repeats_verification_before_existing_atomic_writer(self):
        self.guard.write_report(self.instance, self.result, str(self.report))
        self.assertEqual(self.instance.method_calls, [
            mock.call._path(str(self.report)),
            mock.call._no_symlink(str(self.report), protected=True),
            mock.call.verify(),
            mock.call._atomic_write(str(self.report), json.dumps(self.result, sort_keys=True, indent=2) + "\n")])

    def test_outside_logs_and_logs_itself_refuse_before_writer(self):
        for path in (self.root / "outside.json", self.logs):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "below registered logs"):
                self.guard.write_report(self.instance, self.result, str(path))
        self.instance.verify.assert_not_called()
        self.instance._atomic_write.assert_not_called()

    def test_missing_report_parent_refuses_before_writer(self):
        self.report.parent.rmdir()
        with self.assertRaisesRegex(ValueError, "parent directory is unavailable"):
            self.guard.write_report(self.instance, self.result, str(self.report))
        self.instance.verify.assert_not_called()
        self.instance._atomic_write.assert_not_called()

    def test_protection_or_reverification_failure_never_writes(self):
        for method in ("_no_symlink", "verify"):
            with self.subTest(method=method):
                target = getattr(self.instance, method)
                target.side_effect = ValueError("refused")
                with self.assertRaisesRegex(ValueError, "refused"):
                    self.guard.write_report(self.instance, self.result, str(self.report))
                self.instance._atomic_write.assert_not_called()
                target.side_effect = (lambda value, **kwargs: Path(value)) if method == "_no_symlink" else None


if __name__ == "__main__":
    unittest.main(verbosity=2)
