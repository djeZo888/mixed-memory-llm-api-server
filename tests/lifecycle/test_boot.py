"""Rendered boot contract fixtures; live Linux systemd/reboot remains NOT_TESTED."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from storage_fixtures import ROOT, RegisteredFixture
from lifecycle.boot_unit import RECOVERY_FILES, RECOVERY_ROOT, mount_unit_name, render_boot_unit
from lifecycle.storage_binding import BindingError


def parse_unit(text):
    sections = {}
    section = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = sections.setdefault(line[1:-1], {})
        else:
            key, value = line.split("=", 1)
            section.setdefault(key, []).append(value)
    return sections


def seconds(value):
    for suffix, multiplier in (("min", 60), ("h", 3600), ("s", 1)):
        if value.endswith(suffix):
            return int(value[:-len(suffix)]) * multiplier
    return int(value)


class BootSourceTests(unittest.TestCase):
    def fixture(self, **kwargs):
        fixture = RegisteredFixture(**kwargs)
        self.addCleanup(fixture.close)
        binding = fixture.binding()
        source = binding.path("services", "mixed-memory-llm-api-server")
        for relative in RECOVERY_FILES:
            # These are tiny synthetic trusted source bytes, not execution
            # fixtures. Renderer must compare data and recovery byte identity.
            for root in (source, RECOVERY_ROOT):
                path = fixture.local(root + "/" + relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# synthetic source identity: " + relative + "\n")
                path.chmod(0o644)
        instance_path = binding.path("services", "llm-manager/deployment-instance.json")
        fixture.jsonfile(instance_path, {"schema_version": 1, "id": "fixture-instance",
                                         "storage_identity": binding.identity})
        return fixture, binding, source, instance_path

    def test_single_namespace_does_not_create_nonexistent_mount_dependency(self):
        for models in ("/srv/ai/models", "/srv/ai"):
            fixture, binding, source, instance = self.fixture(models=models)
            unit = parse_unit(render_boot_unit(binding, source, instance))["Unit"]
            self.assertEqual(unit["RequiresMountsFor"], ["/srv/ai"])
            self.assertEqual(unit["ConditionPathIsMountPoint"], ["/srv/ai"])
            self.assertEqual(unit["BindsTo"], ["srv-ai.mount"])

    def test_nested_and_sibling_exact_mounts_order_and_stop_the_boot_owner(self):
        for model_mount in ("/srv/ai/models-large", "/mnt/ai-models"):
            fixture, binding, source, instance = self.fixture(models=model_mount, split=True)
            unit = parse_unit(render_boot_unit(binding, source, instance))["Unit"]
            self.assertEqual(set(unit["RequiresMountsFor"][0].split()), {"/srv/ai", model_mount})
            self.assertEqual(set(unit["ConditionPathIsMountPoint"]), {"/srv/ai", model_mount})
            mount_units = {"srv-ai.mount", mount_unit_name(model_mount)}
            self.assertEqual(set(" ".join(unit["BindsTo"]).split()), mount_units)
            self.assertTrue(mount_units <= set(" ".join(unit["After"]).split()))
            self.assertIn("docker.service", " ".join(unit["Requires"]).split())

    def test_escape_is_exact_and_unsupported_directive_delimiters_refused(self):
        for path, expected in (("/data/models-large", r"data-models\x2dlarge.mount"),
                               ("/.ai-root/models", r"\x2eai\x2droot-models.mount"),
                               ("/srv/ai_data/v1.2", "srv-ai_data-v1.2.mount")):
            self.assertEqual(mount_unit_name(path), expected)
        for path in ("/", "/srv/a b", "/srv/a%u", "/srv/a\nb", "/srv/a\\b", "/srv/../data", "/srv//data"):
            with self.subTest(path=path), self.assertRaises(BindingError):
                mount_unit_name(path)

    def test_boot_stop_code_and_workdir_remain_available_after_data_loss(self):
        fixture, binding, source, instance = self.fixture()
        text = render_boot_unit(binding, source, instance)
        service = parse_unit(text)["Service"]
        self.assertEqual(service["Type"], ["oneshot"])
        self.assertEqual(service["RemainAfterExit"], ["yes"])
        self.assertNotIn("Restart", service)
        self.assertEqual(service["WorkingDirectory"], ["/"])
        for directive, action, code_root in (("ExecStart", "boot-start", source),
                                             ("ExecStop", "boot-stop", RECOVERY_ROOT)):
            argv = shlex.split(service[directive][0])
            self.assertEqual(argv[:5], ["/usr/bin/python3", "-I", "-B", code_root + "/scripts/llmctl", action])
            self.assertIn("--yes", argv)
            self.assertEqual(argv[argv.index("--instance") + 1], instance)
        self.assertNotIn("docker", " ".join(service["ExecStart"] + service["ExecStop"]))
        self.assertNotIn("git checkout", text)
        # Runtime recovery behavior is tested by Manager fixtures. This proves
        # the rendered stop entrypoint itself is not located on vanished data.
        fixture.runner.blocks[3]["mountpoints"] = [None]
        self.assertTrue(fixture.local(RECOVERY_ROOT + "/scripts/llmctl").is_file())
        with self.assertRaises(BindingError):
            render_boot_unit(binding, source, instance)

    def test_conservative_timeouts_and_no_root_journal_output(self):
        fixture, binding, source, instance = self.fixture()
        service = parse_unit(render_boot_unit(binding, source, instance))["Service"]
        deployment_timeouts = [json.loads(path.read_text())["launch"]["timeout_seconds"]
                               for path in (ROOT / "configs/deployments").glob("*.json")]
        self.assertGreater(seconds(service["TimeoutStartSec"][0]), max(deployment_timeouts))
        self.assertGreaterEqual(seconds(service["TimeoutStopSec"][0]), 150)
        self.assertLessEqual(seconds(service["TimeoutStopSec"][0]), 600)
        self.assertEqual(service["StandardOutput"], ["null"])
        self.assertEqual(service["StandardError"], ["null"])
        self.assertEqual(service["UMask"], ["0077"])
        for path in (ROOT / "configs/deployments").glob("*.json"):
            deployment = json.loads(path.read_text())
            self.assertEqual(deployment["docker_restart_policy"], "no")
            self.assertEqual(deployment["logs"], {"driver": "json-file", "max_size": "20m", "max_file": 3})

    def test_wrong_instance_identity_or_path_fails_closed(self):
        fixture, binding, source, instance = self.fixture()
        value = {"storage_identity": binding.identity}
        value["storage_identity"]["models"]["uuid"] = "wrong-uuid"
        fixture.jsonfile(instance, value)
        with self.assertRaisesRegex(BindingError, "instance_storage_identity_mismatch"):
            render_boot_unit(binding, source, instance)
        with self.assertRaisesRegex(BindingError, "boot_instance_path_mismatch"):
            render_boot_unit(binding, source, instance + ".other")

    def test_untrusted_source_or_recovery_snapshot_refused(self):
        for mutation in ("source_mode", "source_symlink", "source_missing", "recovery_missing", "recovery_mode", "recovery_stale", "recovery_extra", "instance_mode"):
            with self.subTest(mutation=mutation):
                fixture, binding, source, instance = self.fixture()
                code = fixture.local(source + "/scripts/lifecycle/manager.py")
                recovery = fixture.local(RECOVERY_ROOT + "/scripts/lifecycle/manager.py")
                if mutation == "source_mode":
                    code.chmod(0o666)
                elif mutation == "source_symlink":
                    code.unlink()
                    code.symlink_to(recovery)
                elif mutation == "source_missing":
                    code.unlink()
                elif mutation == "recovery_missing":
                    recovery.unlink()
                elif mutation == "recovery_mode":
                    recovery.chmod(0o666)
                elif mutation == "recovery_stale":
                    recovery.write_text("# stale source\n")
                elif mutation == "recovery_extra":
                    recovery.with_name("unexpected.py").write_text("# not in reviewed recovery closure\n")
                else:
                    fixture.local(instance).chmod(0o644)
                with self.assertRaises(BindingError):
                    render_boot_unit(binding, source, instance)

    def test_inert_source_service_requires_installer_render(self):
        text = (ROOT / "scripts/lifecycle/llmctl-boot.service").read_text()
        self.assertNotIn("[Service]", text)
        self.assertIn("render_boot_unit", text)

    def test_hidden_mount_on_individual_source_file_is_refused(self):
        fixture, binding, source, instance = self.fixture()
        fixture.runner.add_disk('/dev/sdd', '8:48', '/dev/sdd1', '8:49',
                                'hidden-uuid', source + '/scripts/lifecycle/manager.py')
        with self.assertRaisesRegex(BindingError, 'path_crosses_unregistered_mount'):
            render_boot_unit(binding, source, instance)

    def test_real_shared_writer_and_admission_are_required_in_both_snapshots(self):
        for module in ('storage_io.py', 'prerequisites.py'):
            for location in ('source', 'recovery'):
                with self.subTest(module=module, location=location):
                    fixture, binding, source, instance = self.fixture()
                    root = source if location == 'source' else RECOVERY_ROOT
                    fixture.local(root + '/scripts/install/' + module).unlink()
                    with self.assertRaisesRegex(BindingError, 'installed_source_snapshot_incomplete'):
                        render_boot_unit(binding, source, instance)

    def test_recovery_snapshot_contains_actual_isolated_cli_import_closure(self):
        fixture, binding, source, instance = self.fixture()
        for relative in RECOVERY_FILES:
            value = (ROOT / relative).read_bytes()
            for directory in (source, RECOVERY_ROOT):
                fixture.local(directory + "/" + relative).write_bytes(value)
        render_boot_unit(binding, source, instance)
        result = subprocess.run([sys.executable, "-I", "-B",
                                 str(fixture.local(RECOVERY_ROOT + "/scripts/llmctl")),
                                 "boot-stop", "--help"], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("boot-stop", result.stdout)

    def test_recovery_snapshot_imports_real_admission_with_explicit_worker_paths(self):
        fixture, binding, source, instance = self.fixture()
        for relative in RECOVERY_FILES:
            content = (ROOT / relative).read_bytes()
            for directory in (source, RECOVERY_ROOT):
                fixture.local(directory + "/" + relative).write_bytes(content)
        render_boot_unit(binding, source, instance)
        policy_directory = fixture.root / 'synthetic-policy'
        policy_directory.mkdir(mode=0o700)
        script = """
import inspect, json, pathlib, sys
scripts = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(scripts))
import install.prerequisites as prerequisites
assert pathlib.Path(prerequisites.__file__) == scripts / 'install/prerequisites.py'
admission = prerequisites.assert_package_admission
parameters = inspect.signature(admission).parameters
assert list(parameters) == ['data_dir', 'storage_guard', 'policy_path']
assert parameters['policy_path'].kind is inspect.Parameter.KEYWORD_ONLY
assert parameters['policy_path'].default is None
calls = []
def guard():
    calls.append('checked')
data, policy = pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
admission(data, guard, policy_path=policy)
gate = data / 'services/installer/package-execution-gate.json'
gate.write_text('{}')
gate.chmod(0o600)
try:
    admission(data, guard, policy_path=policy)
except prerequisites.PrerequisiteError as error:
    assert error.code == 'package_transaction_recovery_required'
else:
    raise AssertionError('real admission ignored the execution gate')
assert len(calls) == 4
assert not policy.exists()
print(json.dumps({'isolated_admission': 'passed', 'guard_calls': len(calls)}))
"""
        result = subprocess.run(
            [sys.executable, '-I', '-B', '-c', script,
             str(fixture.local(RECOVERY_ROOT + '/scripts')), str(fixture.local(binding.path('data'))),
             str(policy_directory / 'policy-rc.d')], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'isolated_admission': 'passed', 'guard_calls': 4})
        self.assertEqual(list(policy_directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
