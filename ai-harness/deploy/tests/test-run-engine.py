#!/usr/bin/env python3
"""Launcher contract tests with a fake Podman; no container or network calls."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import signal
import tempfile
import time
import unittest

sys.dont_write_bytecode = True


LAUNCHER = Path(__file__).resolve().parents[1] / "run-engine.sh"
REVISION = "ae65651df5f97ae1085ab4e19964f4b78c769a4e"
IMAGE_ID = "sha256:" + "a" * 64
PATCHSET = json.loads((LAUNCHER.parent / "patches/identity.json").read_text())["patchSetSha256"]
TOKEN = "fixture-ephemeral-inference-token-only"


class RedactorContract(unittest.TestCase):
    def test_private_helper_help_needs_no_environment(self):
        result = subprocess.run([sys.executable, str(LAUNCHER.parent / "engine/redact-acp.py"), "--help"],
                                env={}, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Private ACP supervisor", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_chunk_boundaries_json_escaping_and_utf8_are_preserved(self):
        module_spec = importlib.util.spec_from_file_location("redact_acp", LAUNCHER.parent / "engine/redact-acp.py")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        for token in (TOKEN, 'fixture-quote-"-backslash-\\-unicode-ž'):
            for encode_ascii in (False, True):
                payload = (json.dumps({"jsonrpc": "2.0", "text": "Δ starts", "token": token},
                                      ensure_ascii=encode_ascii) + "\n").encode()
                expected = payload.replace(json.dumps(token, ensure_ascii=encode_ascii)[1:-1].encode(), b"[REDACTED]")
                for size in (1, 2, 7, len(token), 65536):
                    with self.subTest(token_kind=len(token), chunk_size=size, encode_ascii=encode_ascii):
                        redactor = module.Redactor(token)
                        actual = b"".join(redactor.feed(payload[index:index + size]) for index in range(0, len(payload), size))
                        actual += redactor.feed(b"", final=True)
                        self.assertEqual(actual, expected)

    def test_nonsecret_short_acp_message_has_no_token_length_delay(self):
        module_spec = importlib.util.spec_from_file_location("redact_acp", LAUNCHER.parent / "engine/redact-acp.py")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        message = b'{"id":1}\n'
        self.assertEqual(module.Redactor(TOKEN).feed(message), message)


@unittest.skipIf(os.geteuid() == 0, "launcher deliberately refuses root")
class LauncherContract(unittest.TestCase):
    def setUp(self):
        # Stay outside platform /tmp symlinks and administrative mount roots.
        self.temp = tempfile.TemporaryDirectory(prefix="ai-harness-launcher-test-", dir=Path.home().resolve())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = self.root / "profile with spaces"
        self.workspace = self.root / "workspace with spaces"
        self.home = self.root / "host-home"
        self.bin = self.root / "bin"
        for directory in (self.profile, self.workspace, self.home, self.bin):
            directory.mkdir(mode=0o700)
        self.settings = {"rootless": "true", "revision": REVISION, "image_id": IMAGE_ID, "patchset": PATCHSET, "exit": 0}
        self.settings_path = self.bin / "settings.json"
        self.log = self.bin / "calls.jsonl"
        mock = self.bin / "podman"
        mock.write_text(f"#!{sys.executable}\n" + r'''
import json, os, pathlib, signal, sys, time
base = pathlib.Path(__file__).resolve().parent
settings = json.loads((base / "settings.json").read_text())
with (base / "calls.jsonl").open("a") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "env": dict(os.environ)}) + "\n")
args = sys.argv[1:]
assert args.pop(0) == "--remote=false", args
if args[0] == "info":
    if settings.get("leak_preflight"):
        sys.stderr.write(os.environ["AI_HARNESS_GATEWAY_TOKEN"])
    print(settings["rootless"])
elif args[:2] == ["image", "inspect"]:
    if settings.get("missing_image"):
        sys.exit(125)
    print(settings["image_id"] + "|" + settings["revision"] + "|" + settings["patchset"])
elif args[0] == "run":
    if settings.get("startup_stdout"):
        os.write(1, settings["startup_stdout"].encode())
    (base / "run.pid").write_text(str(os.getpid()))
    if settings.get("hang"):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        while True:
            time.sleep(1)
    if settings.get("leak_streams"):
        token = os.environ["AI_HARNESS_GATEWAY_TOKEN"].encode()
        for stream in (1, 2):
            for part in (b"before-", token[:11], token[11:], b"-after\n"):
                os.write(stream, part)
                time.sleep(0.01)
    sys.stdout.write(sys.stdin.read())
    sys.stderr.write("fixture engine stderr\n")
    sys.exit(settings["exit"])
elif args[0] == "rm":
    if settings.get("cleanup_failure"):
        sys.exit(125)
elif args[:2] == ["container", "exists"]:
    sys.exit(settings.get("exists_exit", 1))
else:
    raise AssertionError(args)
''')
        mock.chmod(0o700)
        self.env = dict(os.environ, PATH=f"{self.bin}:/usr/bin:/bin", HOME=str(self.home),
                        AI_HARNESS_GATEWAY_TOKEN=TOKEN, AI_HARNESS_SESSION_ID="session-fixture-01")
        self.env.pop("AI_HARNESS_GATEWAY_URL", None)

    def invoke(self, args=None, env=None, text=""):
        self.settings_path.write_text(json.dumps(self.settings))
        if args is None:
            args = ["--profile-dir", str(self.profile), "--workspace", str(self.workspace)]
        return subprocess.run(["/bin/bash", str(LAUNCHER), *args], env=env or self.env,
                              input=text, capture_output=True, text=True, check=False)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_acp_transport_mounts_and_environment_allowlist(self):
        forbidden = {
            "OPENAI_API_KEY": "fixture-real-upstream-must-not-pass",
            "MINIMAX_API_KEY": "fixture-provider-must-not-pass",
            "AI_HARNESS_INFERENCE_KEY_FILE": "/private/server-key",
            "SSH_AUTH_SOCK": "/private/ssh-agent.sock",
            "CONTAINER_HOST": "ssh://unexpected-host/run/podman.sock",
            "CONTAINER_CONNECTION": "unexpected-connection",
            "DOCKER_HOST": "unix:///private/docker.sock",
            "HTTP_PROXY": "http://unexpected-proxy",
            "NODE_OPTIONS": "--inspect=0.0.0.0:9229",
        }
        self.env.update(forbidden)
        request = '{"jsonrpc":"2.0","id":1,"method":"initialize"}\n'
        result = self.invoke(text=request)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, request)
        self.assertEqual(result.stderr, "fixture engine stderr\n")
        calls = self.calls()
        self.assertEqual(len(calls), 5)
        for call in calls:
            self.assertFalse(forbidden.keys() & call["env"].keys())
            self.assertNotIn(TOKEN, " ".join(call["argv"]))
            if call["argv"][1] in ("rm", "container"):
                self.assertNotIn("AI_HARNESS_GATEWAY_TOKEN", call["env"])
            else:
                self.assertEqual(call["env"]["AI_HARNESS_GATEWAY_TOKEN"], TOKEN)
            self.assertEqual(call["env"]["XDG_RUNTIME_DIR"], f"/run/user/{os.getuid()}")
        argv = calls[-3]["argv"]
        container_name = argv[argv.index("--name") + 1]
        self.assertRegex(container_name, r"^ai-harness-[0-9a-f]{32}$")
        self.assertEqual(calls[-2]["argv"], ["--remote=false", "rm", "--force", "--time", "20", "--ignore", container_name])
        self.assertEqual(calls[-1]["argv"], ["--remote=false", "container", "exists", container_name])
        mounts = [argv[index + 1] for index, item in enumerate(argv) if item == "--volume"]
        self.assertEqual(mounts, [f"{self.profile}:{self.profile}:rw,rprivate", f"{self.workspace}:{self.workspace}:rw,rprivate"])
        self.assertEqual(argv[-1], IMAGE_ID)
        self.assertEqual(argv[argv.index("--network") + 1], "slirp4netns:allow_host_loopback=true")
        self.assertEqual(argv[argv.index("--user") + 1], f"{os.getuid()}:{os.getgid()}")
        self.assertEqual(argv[argv.index("--workdir") + 1], str(self.workspace))
        self.assertIn("--pull=never", argv)
        self.assertIn("--read-only", argv)
        self.assertIn("--init", argv)
        self.assertIn("no-new-privileges", argv)
        self.assertIn("seccomp=" + str(LAUNCHER.parent / "security/chromium-seccomp.json"), argv)
        self.assertEqual(argv[argv.index("--cap-drop") + 1], "ALL")
        self.assertNotIn("--privileged", argv)
        self.assertNotIn("--env-host", argv)
        self.assertNotIn("--no-sandbox", argv)
        self.assertNotIn("-t", argv)
        container_env = [argv[index + 1] for index, item in enumerate(argv) if item == "--env"]
        self.assertCountEqual(container_env, [
            f"HOME={self.profile}/state/home", f"MINIMAX_DATA_DIR={self.profile}/state",
            "PATH=/opt/ai-harness-python/bin:/opt/ai-harness/tools/runtime/node_modules/.bin:/opt/ai-harness/bin:/usr/local/bin:/usr/bin:/bin", "TERM=dumb", "NO_COLOR=1",
            "MCODE_DISABLE_TELEMETRY=1", "DO_NOT_TRACK=1", "MCODE_CHROME_PATH=/usr/bin/chromium", "PYTHONDONTWRITEBYTECODE=1",
            "AI_HARNESS_GATEWAY_URL", "AI_HARNESS_GATEWAY_TOKEN", "AI_HARNESS_SESSION_ID",
        ])
        self.assertEqual((self.profile / "state" / "home").stat().st_mode & 0o777, 0o700)

    def test_legacy_profile_layout_refused_without_hiding_history(self):
        (self.profile / "config.yaml").write_text('{"fixture_history":"preserve"}')
        result = self.invoke()
        self.assertEqual(result.returncode, 64)
        self.assertIn("explicit migration", result.stderr)
        self.assertFalse((self.profile / "state").exists())
        self.assertEqual((self.profile / "config.yaml").read_text(), '{"fixture_history":"preserve"}')

    def test_symlinked_engine_state_rejected(self):
        (self.profile / "state").symlink_to(self.home, target_is_directory=True)
        result = self.invoke()
        self.assertEqual(result.returncode, 64)
        self.assertNotIn("run", [call["argv"][1] for call in self.calls()])

    def test_engine_exit_status_propagates(self):
        self.settings["exit"] = 17
        request = '{"jsonrpc":"2.0","id":1}\n'
        result = self.invoke(text=request)
        self.assertEqual(result.returncode, 17)
        self.assertEqual(result.stdout, request)
        self.assertEqual(result.stderr, "fixture engine stderr\n")
        self.assertEqual(self.calls()[-1]["argv"][1:3], ["container", "exists"])

    def test_help_does_not_start_podman(self):
        result = self.invoke(["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("ACP stdio", result.stdout)
        self.assertFalse(self.calls())

    def test_missing_and_duplicate_arguments_fail_before_podman(self):
        cases = [[], ["--profile-dir"], ["--bad-option"],
                 ["--profile-dir", str(self.profile), "--profile-dir", str(self.profile), "--workspace", str(self.workspace)]]
        for args in cases:
            with self.subTest(args=args):
                self.assertEqual(self.invoke(args).returncode, 64)
                self.assertFalse(self.calls())

    def test_gateway_and_session_are_required_and_restricted(self):
        cases = [("AI_HARNESS_GATEWAY_TOKEN", ""), ("AI_HARNESS_GATEWAY_TOKEN", "short-token"),
                 ("AI_HARNESS_GATEWAY_TOKEN", "fixture\nsecret-control"),
                 ("AI_HARNESS_SESSION_ID", ""), ("AI_HARNESS_SESSION_ID", "path/invalid"),
                 ("AI_HARNESS_GATEWAY_URL", "http://10.156.100.60:30002/v1")]
        for name, value in cases:
            with self.subTest(name=name, value=value):
                env = dict(self.env, **{name: value})
                result = self.invoke(env=env)
                self.assertEqual(result.returncode, 64)
                self.assertFalse(self.calls())
                self.assertNotIn(value, result.stderr) if value else None

    def test_dotted_session_identifier_is_opaque_metadata(self):
        self.env["AI_HARNESS_SESSION_ID"] = "session.fixture-01"
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls()[-3]["env"]["AI_HARNESS_SESSION_ID"], "session.fixture-01")

    def test_streams_redact_split_token_without_corrupting_acp(self):
        self.settings.update(leak_streams=True, leak_preflight=True)
        request = '{"jsonrpc":"2.0","id":1}\n'
        result = self.invoke(text=request)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "before-[REDACTED]-after\n" + request)
        self.assertEqual(result.stderr, "before-[REDACTED]-after\nfixture engine stderr\n")
        self.assertNotIn(TOKEN, result.stdout + result.stderr)

    def test_cleanup_failure_cannot_report_success(self):
        self.settings["cleanup_failure"] = True
        result = self.invoke()
        self.assertEqual(result.returncode, 125)
        self.assertIn("settlement unconfirmed", result.stderr)
        self.assertNotIn(TOKEN, result.stderr)

    def invoke_signal(self, number):
        self.settings["hang"] = True
        self.settings["startup_stdout"] = '{"jsonrpc":"2.0","method":"fixture/native-notification"}\n'
        (self.bin / "run.pid").unlink(missing_ok=True)
        self.log.unlink(missing_ok=True)
        self.settings_path.write_text(json.dumps(self.settings))
        process = subprocess.Popen(["/bin/bash", str(LAUNCHER), "--profile-dir", str(self.profile),
                                    "--workspace", str(self.workspace)], env=self.env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        deadline = time.monotonic() + 5
        while not (self.bin / "run.pid").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue((self.bin / "run.pid").exists())
        child_pid = int((self.bin / "run.pid").read_text())
        started = time.monotonic()
        process.send_signal(number)
        stdout, stderr = process.communicate(timeout=8)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 8)
        self.assertEqual(stdout, self.settings["startup_stdout"].encode())
        self.assertNotIn(TOKEN.encode(), stdout + stderr)
        with self.assertRaises(ProcessLookupError):
            os.kill(child_pid, 0)
        calls = self.calls()
        run_args = calls[-3]["argv"]
        name = run_args[run_args.index("--name") + 1]
        self.assertEqual(calls[-2]["argv"], ["--remote=false", "rm", "--force", "--time", "20", "--ignore", name])
        self.assertEqual(calls[-1]["argv"], ["--remote=false", "container", "exists", name])
        return process.returncode, stdout, stderr

    def test_requested_signals_acknowledge_only_verified_exact_cleanup(self):
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            with self.subTest(signal=number):
                code, _stdout, stderr = self.invoke_signal(number)
                self.assertEqual(code, 0, stderr)
                self.assertEqual(stderr, b"")

    def test_requested_signal_cleanup_failure_is_125(self):
        self.settings["cleanup_failure"] = True
        code, _stdout, stderr = self.invoke_signal(signal.SIGTERM)
        self.assertEqual(code, 125)
        self.assertIn(b"settlement unconfirmed", stderr)

    def test_requested_signal_absence_uncertainty_is_125(self):
        for exists_exit in (0, 125):
            with self.subTest(exists_exit=exists_exit):
                self.settings["exists_exit"] = exists_exit
                code, _stdout, stderr = self.invoke_signal(signal.SIGTERM)
                self.assertEqual(code, 125)
                self.assertIn(b"settlement unconfirmed", stderr)

    def test_normal_exit_absence_uncertainty_cannot_report_success(self):
        for exists_exit in (0, 125):
            with self.subTest(exists_exit=exists_exit):
                self.settings["exists_exit"] = exists_exit
                request = '{"jsonrpc":"2.0","id":1}\n'
                result = self.invoke(text=request)
                self.assertEqual(result.returncode, 125)
                self.assertEqual(result.stdout, request)
                self.assertIn("settlement unconfirmed", result.stderr)

    def test_nonroot_container_engine_required(self):
        self.settings["rootless"] = "false"
        self.assertEqual(self.invoke().returncode, 64)
        self.assertEqual(len(self.calls()), 1)
        self.assertFalse((self.profile / "state" / "home").exists())

    def test_image_revision_and_identity_checked(self):
        for updates in ({"revision": "wrong"}, {"image_id": "mutable-tag"}, {"missing_image": True},
                        {"patchset": ""}, {"patchset": "<no value>"}, {"patchset": "b" * 64}):
            with self.subTest(updates=updates):
                self.settings.update(updates)
                self.assertEqual(self.invoke().returncode, 64)
                self.assertFalse(any("run" in call["argv"] for call in self.calls()))
                self.assertFalse((self.profile / "state" / "home").exists())
                self.settings = {"rootless": "true", "revision": REVISION, "image_id": IMAGE_ID,
                                 "patchset": PATCHSET, "exit": 0}

    def test_unsafe_mount_paths_rejected(self):
        nested = self.profile / "nested"
        nested.mkdir()
        credentials = self.home / ".ssh"
        credentials.mkdir()
        config = self.home / ".config" / "containers"
        config.mkdir(parents=True)
        link = self.root / "linked-workspace"
        link.symlink_to(self.workspace, target_is_directory=True)
        for path in (self.home, self.root, self.profile, nested, credentials, config, link):
            with self.subTest(path=path):
                result = self.invoke(["--profile-dir", str(self.profile), "--workspace", str(path)])
                self.assertEqual(result.returncode, 64, result.stderr)
                self.assertFalse(self.calls())
        for path in ("relative", f"{self.workspace}/", f"{self.workspace}/../{self.workspace.name}"):
            with self.subTest(path=path):
                self.assertEqual(self.invoke(["--profile-dir", str(self.profile), "--workspace", path]).returncode, 64)
                self.assertFalse(self.calls())

    def test_symlinked_engine_home_rejected(self):
        (self.profile / "state").mkdir()
        (self.profile / "state" / "home").symlink_to(self.home, target_is_directory=True)
        self.assertEqual(self.invoke().returncode, 64)
        self.assertFalse(any("run" in call["argv"] for call in self.calls()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
