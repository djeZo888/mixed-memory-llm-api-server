"""Real preparation parser and ContainerPackages argv; all commands mocked.

No apt execution, storage anchor lifetime, or systemd behavior is tested here.
Run: python3 -m unittest discover -s tests/install -p test_package_preparation.py -v
"""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from install.container import ContainerPackages
from install.core import InstallError, Runner


class PackagePreparationTests(unittest.TestCase):
    modes = (["update"],
             ["-s", "--no-install-recommends", "--no-remove", "install", "fixture=1.0"],
             ["--download-only", "--yes", "--no-install-recommends", "--no-remove", "install", "fixture=1.0"])

    def test_exact_root_sandbox_option_allowed_for_each_preparation_mode(self):
        with patch("install.core.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "prepared")) as command:
            for mode in self.modes:
                argv = ["apt-get", "-o", "APT::Sandbox::User=root", *mode]
                with self.subTest(mode=mode):
                    self.assertEqual(Runner(writable=True).run(argv), "prepared")
                    self.assertEqual(command.call_args.args[0], argv)
            self.assertEqual(command.call_count, len(self.modes))

    def test_altered_sandbox_values_and_other_controls_rejected(self):
        options = ["APT::Sandbox::User=" + value for value in
                   ("", "_apt", "0", "Root", "root ", "root=other", "root\0")]
        options += ["APT::Sandbox::user=root", "APT::Sandbox::Group=root",
                    "APT::Sandbox::Seccomp=false", "DPkg::Pre-Invoke::=arbitrary-command",
                    "APT::Get::List-Cleanup=true"]
        with patch("install.core.subprocess.run") as command:
            for mode in self.modes:
                for option in options:
                    with self.subTest(mode=mode, option=option), self.assertRaisesRegex(
                            InstallError, "owned_package_transaction_required"):
                        Runner(writable=True).run(["apt-get", "-o", option, *mode])
            command.assert_not_called()

    def test_root_sandbox_does_not_allow_mode_or_later_option_overrides(self):
        prefix = ["apt-get", "-o", "APT::Sandbox::User=root"]
        rejected = [
            ["-o", "APT::Get::Simulate=false", *self.modes[1]],
            ["-o", "APT::Get::Download-Only=false", *self.modes[2]],
            [*self.modes[1], "-o", "APT::Get::Simulate=false"],
            [*self.modes[2], "-o", "APT::Get::Download-Only=false"],
            ["-o", "APT::Sandbox::User=_apt", "update"],
            ["update", "-o", "APT::Sandbox::User=_apt"],
            ["install", "update"], ["install", "fixture=1.0"],
            ["--no-download", "--yes", "--no-install-recommends", "--no-remove", "install", "fixture=1.0"],
        ]
        with patch("install.core.subprocess.run") as command:
            for args in rejected:
                with self.subTest(args=args), self.assertRaisesRegex(
                        InstallError, "owned_package_transaction_required"):
                    Runner(writable=True).run([*prefix, *args])
            command.assert_not_called()

    def test_actual_container_staging_argv_passes_real_runner_parser(self):
        lock = {"requested": {"docker": {"fixture": "1.0"}}, "groups": {"docker": ["fixture"]},
                "packages": {"fixture": {"version": "1.0", "size_bytes": 100,
                                           "installed_bytes": 1000, "sha256": "a" * 64}},
                "ubuntu_snapshot": "fixture-snapshot"}
        runner = Runner(writable=True)
        subject = ContainerPackages({"data_dir": "/fixture/data"}, runner, lambda: None, lock=lock)
        anchor_path = "/proc/123/fd/456"

        def command_result(argv, **kwargs):
            if argv == ["id", "-u"]:
                output = "0"
            elif argv[:3] == ["df", "-B1", "--output=avail"]:
                output = "Avail\n" + str(100 * 1024 ** 3)
            elif argv[0] == "apt-cache":
                output = "Version: 1.0\nSHA256: " + "a" * 64 + "\nSize: 100\n"
            elif argv[0] == "apt-get":
                output = "Inst fixture (1.0 fixture [amd64])\n" if "-s" in argv else ""
            elif argv == ["dpkg-query", "-W", "-f=${Status}\t${Version}", "fixture"]:
                output = "install ok installed\t1.0"
            else:
                self.fail("Unexpected command: " + repr(argv))
            return subprocess.CompletedProcess(argv, 0, output)

        # The real stage constructs all preparation argv and uses real Runner.run.
        # Mock filesystem/source setup and the owned mutation seam separately;
        # this fixture makes no assertion about parent /proc anchor persistence.
        with patch("install.container.AnchoredRoot") as anchor, \
                patch.object(subject, "_paths"), \
                patch.object(subject, "package_transaction", return_value="") as transaction, \
                patch.object(runner, "_package_preparation", wraps=runner._package_preparation) as parser, \
                patch("install.core.subprocess.run", side_effect=command_result) as command:
            anchor.return_value.__enter__.return_value.proc_path.return_value = anchor_path
            result = subject._install("docker")
            self.assertEqual(result["changed_packages"], {"fixture": "1.0"})
            staging = [call for call in command.call_args_list if call.args[0][0] == "apt-get"]
            self.assertEqual(len(staging), 3)
            self.assertEqual([call.args[0] for call in parser.call_args_list],
                             [call.args[0] for call in staging])
            for call, mode in zip(staging, self.modes):
                argv = call.args[0]
                self.assertEqual(argv[-len(mode):], mode)
                self.assertEqual(argv.count("APT::Sandbox::User=root"), 1)
                self.assertIn("Dir::Cache=" + anchor_path + "/cache/installer-apt", argv)
                self.assertEqual(call.kwargs["env"]["TMPDIR"], anchor_path + "/cache/installer-apt/tmp")
            transaction.assert_called_once()
            mutation_argv = transaction.call_args.args[0]
            self.assertIn("--no-download", mutation_argv)
            command.reset_mock()
            with self.assertRaisesRegex(InstallError, "owned_package_transaction_required"):
                runner.run(mutation_argv)
            command.assert_not_called()
        self.assertIsNone(subject._anchor)


if __name__ == "__main__":
    unittest.main()
