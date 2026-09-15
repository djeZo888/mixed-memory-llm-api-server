"""Offline N1C URL/auth regressions; no socket, package install, or inference."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from test_bootstrap import snapshot


CLIENT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("n1c_common_tests", CLIENT / "client_common.py")
common = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(common)


def client_module(name):
    spec = importlib.util.spec_from_file_location("n1c_" + name + "_tests", CLIENT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"client_common": common}):
        spec.loader.exec_module(module)
    return module


bootstrap = client_module("bootstrap")
launcher = client_module("launch")
PRIVATE_URL = "http://10.156.100.60:30002/v1"


@contextlib.contextmanager
def no_process_or_network():
    """Fail if validation accidentally reaches a process, resolver, or socket."""
    with contextlib.ExitStack() as stack:
        for target in ("subprocess.run", "subprocess.Popen", "socket.socket", "socket.getaddrinfo",
                       "socket.create_connection"):
            stack.enter_context(mock.patch(target, side_effect=AssertionError("Unexpected process/network")))
        for module in (bootstrap, launcher):
            stack.enter_context(mock.patch.object(module, "run_capture", side_effect=AssertionError("Unexpected process")))
        yield


class EndpointPolicyTests(unittest.TestCase):
    def assert_rejected(self, values):
        with no_process_or_network():
            for value in values:
                with self.subTest(value=repr(value)):
                    with self.assertRaises(common.ClientError):
                        common.endpoint(value)
                    with self.assertRaises(common.ClientError):
                        common.endpoint_kind(value)

    def test_existing_loopbacks_and_https_preserve_exact_spelling(self):
        hosts = ("localhost", "LOCALHOST", "LocalHost", "127.0.0.1", "[::1]")
        with no_process_or_network():
            for host in hosts:
                for scheme in ("http", "https", "HTTP", "HTTPS", "hTtPs"):
                    for port in ("1", "443", "65535", "00001", "030002"):
                        value = scheme + "://" + host + ":" + port + "/v1"
                        with self.subTest(value=value):
                            self.assertEqual(common.endpoint(value), value)
                            self.assertEqual(common.endpoint_kind(value), "loopback")

    def test_only_explicit_rfc1918_networks_including_boundaries(self):
        hosts = ("10.0.0.0", "10.0.0.1", "10.156.100.60", "10.255.255.255",
                 "172.16.0.0", "172.16.0.1", "172.31.255.254", "172.31.255.255",
                 "192.168.0.0", "192.168.0.1", "192.168.255.254", "192.168.255.255")
        with no_process_or_network():
            for host in hosts:
                for scheme in ("http", "https"):
                    for port in ("1", "30002", "65535", "00001"):
                        value = scheme + "://" + host + ":" + port + "/v1"
                        with self.subTest(value=value):
                            self.assertEqual(common.endpoint(value), value)
                            self.assertEqual(common.endpoint_kind(value), "private")

    def test_public_link_local_reserved_multicast_and_other_loopback_are_rejected(self):
        hosts = ("9.255.255.255", "11.0.0.0", "172.15.255.255", "172.32.0.0",
                 "192.167.255.255", "192.169.0.0", "0.0.0.0", "0.0.0.1", "8.8.8.8",
                 "100.64.0.1", "100.127.255.255", "127.0.0.2", "127.1.2.3",
                 "169.254.0.1", "169.254.169.254", "192.0.0.1", "192.0.0.9",
                 "192.0.2.1", "198.18.0.1", "198.51.100.1", "203.0.113.1",
                 "224.0.0.0", "239.255.255.255", "240.0.0.1", "255.255.255.255")
        self.assert_rejected("http://" + host + ":30002/v1" for host in hosts)

    def test_dns_new_ipv6_and_mapped_ipv4_are_rejected(self):
        hosts = ("ai-vm", "ai-vm.local", "example.org", "10.156.100.60.example.org", "localhost.", "localhoſt",
                 "[::]", "[::2]", "[0:0:0:0:0:0:0:1]", "[::ffff:10.156.100.60]",
                 "[::ffff:127.0.0.1]", "[fc00::1]", "[fd00::1]", "[fe80::1]",
                 "[fe80::1%en0]", "[::1%25lo0]", "[2001:db8::1]", "[2001:4860:4860::8888]")
        self.assert_rejected("https://" + host + ":443/v1" for host in hosts)

    def test_noncanonical_ipv4_aliases_are_rejected(self):
        hosts = ("010.156.100.60", "10.0156.100.60", "10.156.0100.60", "10.156.100.060",
                 "10.0.0.01", "10.00.0.1", "0x0a.156.100.60", "10.0x9c.100.60",
                 "0x0a9c643c", "167772161", "10.1", "10.1.2", "10.65537",
                 "10.156.100.60.", "10.156.100.60..", "+10.156.100.60", "10.156.100.-60",
                 "10.156.100.256", "10.156.100", "10..100.60", "[10.156.100.60]",
                 "10%2e156%2e100%2e60", "%31%30.156.100.60", "１０.156.100.60",
                 "10。156.100.60", "10.156.100.60%00", "0177.0.0.1", "2130706433", "127.1")
        self.assert_rejected("http://" + host + ":30002/v1" for host in hosts)

    def test_credentials_query_and_fragment_delimiters_are_always_rejected(self):
        for host in ("localhost", "10.156.100.60"):
            base = "https://" + host + ":443/v1"
            self.assert_rejected(base + suffix for suffix in ("?", "#", "?#", "?x=1", "#x", "?x=#y"))
            self.assert_rejected("http://" + userinfo + "@" + host + ":80/v1"
                                 for userinfo in ("", "user", ":", "user:", ":synthetic", "user:synthetic"))

    def test_exact_path_scheme_authority_and_ports(self):
        self.assert_rejected(("", "10.156.100.60:30002/v1", "//10.156.100.60:30002/v1",
                              "ftp://10.156.100.60:21/v1", "httpſ://10.156.100.60:443/v1", "http:/10.156.100.60:80/v1",
                              "http:////10.156.100.60:80/v1", "http://:80/v1"))
        for host in ("localhost", "10.156.100.60", "[::1]"):
            self.assert_rejected("http://" + host + suffix + "/v1" for suffix in
                                 ("", ":", ":0", ":00000", ":65536", ":999999", ":-1", ":+1",
                                  ":1.0", ":0x50", ":8e1", ":80:81", ":８０", ":abc"))
            self.assert_rejected("http://" + host + ":80" + path for path in
                                 ("", "/", "/v1/", "/v2", "/V1", "//v1", "/./v1", "/a/../v1",
                                  "/%761", "/v%31", "/v1%3f", "/v1%23", "/v1/../v1", "/{env:API}"))

    def test_whitespace_controls_backslashes_and_nonstring_types(self):
        for space in (" ", "\t", "\r", "\n", "\v", "\f", "\u00a0", "\u2003", "\x00", "\x1f"):
            self.assert_rejected((space + PRIVATE_URL, PRIVATE_URL + space,
                                  "http://10.156." + space + "100.60:30002/v1",
                                  "http://10.156.100.60:30002/" + space + "v1"))
        self.assert_rejected(("http://10.156.100.60\\:80/v1", "http://10.156.100.60:80\\/v1",
                              None, True, False, 1, 0.5, [], {}, (PRIVATE_URL,),
                              PRIVATE_URL.encode(), bytearray(PRIVATE_URL.encode()), Path("/v1")))


class PrivateEndpointAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="n1c-endpoint-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.prefix = self.root / "private client with spaces"
        self.prompt = self.root / "synthetic prompt"
        common.write_new(self.prompt, b"Synthetic fixture prompt; no model request is sent.")
        self.settings = {
            "version": common.VERSION, "base_url": PRIVATE_URL, "model": "synthetic-vendor/fixture",
            "auth": {"kind": "file", "reference": str(self.root / "protected synthetic key")},
            "context_tokens": 16384, "output_tokens": 1024,
            "lock_sha256": hashlib.sha256((CLIENT / "package-lock.json").read_bytes()).hexdigest(),
        }

    def args(self, *extra, auth=None, url=PRIVATE_URL):
        return bootstrap.parser().parse_args([
            "--prefix", str(self.prefix), "--base-url", url, "--model", self.settings["model"],
            "--context-tokens", "16384", "--output-tokens", "1024",
            *(auth or ["--api-key-file", self.settings["auth"]["reference"]]), *extra,
        ])

    def installed_fixture(self, settings=None):
        """Synthetic metadata only; no npm invocation or executable is installed."""
        settings = settings or self.settings
        self.prefix.mkdir(mode=0o700)
        for name in ("bin", "xdg", "xdg/config", "xdg/data", "xdg/cache", "xdg/state", "xdg/config/opencode",
                     "npm", "npm/cache", "npm/logs", "tmp", "bun-cache", "managed", "discovery-home"):
            (self.prefix / name).mkdir(mode=0o700)
        for name, value in (("bootstrap.json", settings), ("opencode.json", common.config_for(settings)),
                            ("models.json", {})):
            common.write_new(self.prefix / name, common.json_bytes(value))
        for package in ("opencode-ai", "@opencode-ai/plugin", common.native_package()):
            directory = common.runtime_dir(self.prefix) / "node_modules" / package
            directory.mkdir(parents=True, mode=0o700)
            common.write_new(directory / "package.json", common.json_bytes({"version": common.VERSION}))
        for name in ("package.json", "package-lock.json"):
            shutil.copyfile(CLIENT / name, common.runtime_dir(self.prefix) / name)
        for target, source in (("opencode-client", "launch.py"), ("client_common.py", "client_common.py")):
            shutil.copyfile(CLIENT / source, self.prefix / "bin" / target)

    def assert_refused_before_effects(self, call, exceptions=(common.ClientError,)):
        before = snapshot(self.root)
        output, error = io.StringIO(), io.StringIO()
        with no_process_or_network(), contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            with self.assertRaises(exceptions):
                call()
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(error.getvalue(), "")
        self.assertEqual(snapshot(self.root), before)

    def launch_args(self, command, plan=False):
        options = ["--workspace", str(self.root)]
        if plan:
            options.append("--plan")
        if command == "run":
            options += ["--prompt-file", str(self.prompt)]
        return launcher.parser().parse_args([*options, command])

    def test_private_auth_disabled_bootstrap_refuses_dry_run_and_apply_before_effects(self):
        for url in (PRIVATE_URL, "https://172.16.0.1:443/v1", "http://192.168.1.1:80/v1"):
            for extra in ((), ("--dry-run",)):
                with self.subTest(url=url, dry_run=bool(extra)):
                    args = self.args(*extra, auth=["--auth-disabled"], url=url)
                    self.assert_refused_before_effects(lambda: bootstrap.bootstrap(args))

    def test_malformed_bootstrap_endpoint_refuses_before_output_or_process(self):
        for value in (None, True, [], {}, "http://10.156.100.60:80/v1?", "http://example.org:80/v1"):
            for dry_run in (False, True):
                args = self.args()
                args.base_url, args.dry_run = value, dry_run
                with self.subTest(value=repr(value), dry_run=dry_run):
                    self.assert_refused_before_effects(lambda: bootstrap.bootstrap(args))

    def test_private_file_and_env_plans_do_not_load_or_print_reference_or_value(self):
        synthetic = "synthetic-n1c-sentinel-for-privacy"
        for auth in (["--api-key-file", self.settings["auth"]["reference"]], ["--api-key-env", "N1C_TEST_REFERENCE"]):
            before = snapshot(self.root)
            output = io.StringIO()
            with no_process_or_network(), mock.patch.object(common, "load_key", side_effect=AssertionError("Unexpected key read")), \
                    mock.patch.dict(os.environ, {"N1C_TEST_REFERENCE": synthetic}), contextlib.redirect_stdout(output):
                bootstrap.bootstrap(self.args("--dry-run", auth=auth))
            plan = json.loads(output.getvalue())
            self.assertEqual(plan["base_url"], PRIVATE_URL)
            self.assertFalse(plan["mutations"])
            self.assertNotIn(auth[1], output.getvalue())
            self.assertNotIn(synthetic, output.getvalue())
            self.assertEqual(snapshot(self.root), before)

    def test_config_preserves_exact_private_url_and_only_existing_key_placeholder(self):
        for scheme in ("http", "https"):
            for auth in (self.settings["auth"], {"kind": "env", "reference": "N1C_TEST_REFERENCE"}):
                settings = dict(self.settings, base_url=scheme + "://192.168.1.2:0443/v1", auth=auth)
                with no_process_or_network():
                    config = common.config_for(settings)
                self.assertEqual(config["provider"]["local"]["options"], {
                    "baseURL": settings["base_url"], "apiKey": "{env:" + common.KEY_ENV + "}",
                })
                self.assertNotIn(auth["reference"], json.dumps(config))
                self.assertNotIn("rejectUnauthorized", json.dumps(config))

    def test_shared_validation_refuses_malformed_auth_shape_and_references(self):
        bad_auth = (None, True, [], "disabled", {}, {"kind": None}, {"kind": []}, {"kind": "unknown"},
                    {"kind": "disabled"}, {"kind": "disabled", "reference": "N1C_TEST_REFERENCE"},
                    {"kind": "env"}, {"kind": "env", "reference": None}, {"kind": "env", "reference": 1},
                    {"kind": "env", "reference": ""}, {"kind": "env", "reference": "lowercase"},
                    {"kind": "env", "reference": "HOME"}, {"kind": "env", "reference": common.KEY_ENV},
                    {"kind": "env", "reference": "N1C_TEST_REFERENCE=synthetic"},
                    {"kind": "env", "reference": "N1C_TEST_REFERENCE", "value": "synthetic"},
                    {"kind": "file"}, {"kind": "file", "reference": None}, {"kind": "file", "reference": []},
                    {"kind": "file", "reference": ""}, {"kind": "file", "reference": "relative"},
                    {"kind": "file", "reference": "/synthetic\nkey"},
                    {"kind": "file", "reference": "/synthetic\x00key"})
        with no_process_or_network():
            for auth in bad_auth:
                settings = dict(self.settings, auth=auth)
                with self.subTest(auth=repr(auth)), self.assertRaises(common.ClientError):
                    common.validate_endpoint_auth(settings)
                with self.subTest(config_auth=repr(auth)), self.assertRaises(common.ClientError):
                    common.config_for(settings)
            for settings in (None, False, [], "settings", {}, {"base_url": PRIVATE_URL}, {"auth": {"kind": "disabled"}}):
                with self.subTest(settings=repr(settings)), self.assertRaises(common.ClientError):
                    common.validate_endpoint_auth(settings)

    def test_loopback_disabled_auth_remains_valid_but_malformed_shape_does_not(self):
        for url in ("http://localhost:30002/v1", "https://[::1]:443/v1"):
            settings = dict(self.settings, base_url=url, auth={"kind": "disabled"})
            with no_process_or_network():
                common.validate_endpoint_auth(settings)
                self.assertNotIn("apiKey", common.config_for(settings)["provider"]["local"]["options"])
                for auth in (None, {}, {"kind": "env", "reference": ""}, {"kind": "disabled", "value": "synthetic"}):
                    with self.subTest(url=url, auth=auth), self.assertRaises(common.ClientError):
                        common.validate_endpoint_auth(dict(settings, auth=auth))

    def test_installed_malformed_endpoint_and_auth_fail_before_all_launch_modes(self):
        self.installed_fixture()
        variants = [None, [], {}, dict(self.settings, auth={"kind": "disabled"}),
                    dict(self.settings, auth={"kind": "env", "reference": "HOME"}),
                    dict(self.settings, auth={"kind": "file", "reference": "relative"})]
        variants += [dict(self.settings, base_url=value) for value in
                     (None, True, [], "http://8.8.8.8:80/v1", "http://10.156.100.60:80/v1?",
                      "http://010.156.100.60:80/v1", "https://[fd00::1]:443/v1")]
        for settings in variants:
            (self.prefix / "bootstrap.json").write_bytes(common.json_bytes(settings))
            with self.subTest(settings=repr(settings)):
                self.assert_refused_before_effects(lambda: common.verify_install(self.prefix))
                for command in ("version", "help", "run-help", "config-help", "check", "chat", "run"):
                    for plan in (False, True):
                        args = self.launch_args(command, plan)
                        self.assert_refused_before_effects(lambda: launcher.launch(args, prefix=self.prefix))
                self.assert_refused_before_effects(lambda: bootstrap.bootstrap(self.args("--dry-run")))

    def test_matching_tampered_manifest_and_generated_config_cannot_bypass_policy(self):
        self.installed_fixture()
        for url, auth in ((PRIVATE_URL, {"kind": "disabled"}),
                          ("http://8.8.8.8:80/v1", self.settings["auth"]),
                          (PRIVATE_URL + "?", self.settings["auth"])):
            # Adversarial fixture edits intentionally model tampering, not a reconfiguration method.
            settings = dict(self.settings, base_url=url, auth=auth)
            config = common.config_for(self.settings)
            config["provider"]["local"]["options"]["baseURL"] = url
            if auth["kind"] == "disabled":
                del config["provider"]["local"]["options"]["apiKey"]
            (self.prefix / "bootstrap.json").write_bytes(common.json_bytes(settings))
            (self.prefix / "opencode.json").write_bytes(common.json_bytes(config))
            with self.subTest(url=url, auth=auth["kind"]):
                self.assert_refused_before_effects(lambda: launcher.launch(self.launch_args("chat"), prefix=self.prefix))

    def test_tampered_config_only_is_refused_without_repair(self):
        self.installed_fixture()
        config = common.config_for(self.settings)
        config["provider"]["local"]["options"]["baseURL"] = "http://192.168.1.2:30002/v1"
        (self.prefix / "opencode.json").write_bytes(common.json_bytes(config))
        self.assert_refused_before_effects(lambda: launcher.launch(self.launch_args("chat", True), prefix=self.prefix))

    def test_private_identical_repeat_is_read_only_and_changes_require_new_prefix(self):
        self.installed_fixture()
        before = snapshot(self.root)
        output = io.StringIO()
        with no_process_or_network(), contextlib.redirect_stdout(output):
            bootstrap.bootstrap(self.args("--dry-run"))
        self.assertEqual(json.loads(output.getvalue())["action"], "verify")
        with mock.patch.object(bootstrap, "run_capture", return_value=common.VERSION) as run, \
                mock.patch("socket.socket", side_effect=AssertionError("Unexpected network")), contextlib.redirect_stdout(io.StringIO()):
            bootstrap.bootstrap(self.args())
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], [str(common.binary_path(self.prefix)), "--version"])
        self.assertEqual(snapshot(self.root), before)
        for url in ("http://10.156.100.61:30002/v1", "https://10.156.100.60:30002/v1", "http://10.156.100.60:30003/v1"):
            for extra in ((), ("--dry-run",)):
                self.assert_refused_before_effects(lambda: bootstrap.bootstrap(self.args(*extra, url=url)))

    def test_private_file_auth_actual_run_refuses_missing_empty_and_unsafe_keys(self):
        self.installed_fixture()
        path = Path(self.settings["auth"]["reference"])
        args = self.launch_args("run")
        self.assert_refused_before_effects(lambda: launcher.launch(args, prefix=self.prefix), (common.ClientError, OSError))
        for raw in (b"", b"synthetic\n", b" synthetic", b"synthetic ", b"x\tx", b"\x00", b"\xff", b"x" * 8193):
            path.write_bytes(raw)
            path.chmod(0o600)
            self.assert_refused_before_effects(lambda: launcher.launch(args, prefix=self.prefix))
        path.write_bytes(b"synthetic-n1c-key-not-a-credential")
        path.chmod(0o644)
        self.assert_refused_before_effects(lambda: launcher.launch(args, prefix=self.prefix))
        path.chmod(0o600)
        alias = self.root / "key alias"
        os.link(path, alias)
        self.assert_refused_before_effects(lambda: launcher.launch(args, prefix=self.prefix))
        alias.unlink()
        path.rename(alias)
        path.symlink_to(alias)
        self.assert_refused_before_effects(lambda: launcher.launch(args, prefix=self.prefix))
        path.unlink()
        alias.rename(path)
        self.root.chmod(0o755)
        self.assert_refused_before_effects(lambda: launcher.launch(args, prefix=self.prefix))
        self.root.chmod(0o700)

    def test_private_env_auth_actual_run_refuses_absent_empty_and_invalid_values(self):
        self.settings["auth"] = {"kind": "env", "reference": "N1C_TEST_REFERENCE"}
        self.installed_fixture()
        args = self.launch_args("run")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assert_refused_before_effects(lambda: launcher.launch(args, prefix=self.prefix))
        for value in ("", "synthetic\n", " synthetic", "synthetic ", "x\tx", "é", "x" * 8193):
            with mock.patch.dict(os.environ, {"N1C_TEST_REFERENCE": value}):
                self.assert_refused_before_effects(lambda: launcher.launch(args, prefix=self.prefix))

    def test_native_tls_verification_controls_are_not_added(self):
        # A plain synthetic mapping avoids setting any real OS environment value.
        controls = {"NODE_TLS_REJECT_UNAUTHORIZED": "0", "NODE_OPTIONS": "--require /synthetic/bypass",
                    "NODE_EXTRA_CA_CERTS": "/synthetic/ca.pem", "BUN_TLS_REJECT_UNAUTHORIZED": "0"}
        with no_process_or_network(), mock.patch.object(common.os, "environ", controls):
            env = common.isolated_env(self.prefix)
        for name in controls:
            self.assertNotIn(name, env)


if __name__ == "__main__":
    unittest.main()
