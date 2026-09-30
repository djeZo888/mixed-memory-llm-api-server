#!/usr/bin/env python3
"""Exercise the actual emitted maintainer-script policy without root or apt."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "bootstrap-host.sh"


class PackageStartPolicy(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="h001-policy-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = SCRIPT.read_text()
        policy = source.split('cat > "$policy" <<POLICY\n', 1)[1].split('\nPOLICY\n', 1)[0]
        policy = policy.replace('$work', str(self.root)).replace('\\$', '$')
        self.policy = self.root / 'policy-rc.d'
        self.policy.write_text(policy + '\n')
        self.policy.chmod(0o700)

    def call(self, *args):
        return subprocess.run([str(self.policy), *args], capture_output=True, text=True)

    def test_nginx_start_is_denied_with_or_without_quiet(self):
        for args in [('nginx', 'start'), ('--quiet', 'nginx', 'start'),
                     ('--quiet', 'nginx.service', 'restart'), ('/etc/init.d/nginx', 'start')]:
            with self.subTest(args=args):
                self.assertEqual(self.call(*args).returncode, 101)

    def test_unrelated_service_follows_original_policy_with_unchanged_arguments(self):
        previous = self.root / 'policy-rc.d.original'
        previous.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 42\n')
        previous.chmod(0o700)
        result = self.call('--quiet', 'unrelated', 'start')
        self.assertEqual(result.returncode, 42)
        self.assertEqual(result.stdout.splitlines(), ['--quiet', 'unrelated', 'start'])
        self.assertEqual(self.call('--quiet', 'nginx', 'start').returncode, 101)

    def test_unrelated_service_has_normal_default_policy(self):
        self.assertEqual(self.call('unrelated', 'start').returncode, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
