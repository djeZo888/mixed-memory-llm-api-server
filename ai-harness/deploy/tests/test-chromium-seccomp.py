#!/usr/bin/env python3
"""Verify the reviewed Chromium-only seccomp delta; no host/container calls.

Use --source-profile PATH to also compare the retained original host snapshot.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest


SECURITY = Path(__file__).resolve().parents[1] / "security"
SOURCE_SHA256 = "cc374cf23846ce1f62f4dc807a8e2b8673c783c6f56cb475467621035d281e6c"
PROFILE_SHA256 = "0474c063b32acee85a1eb5ccfc35f7b1f66278af8da722c45b1d25eb2ae1cfbb"
UNCHANGED_SHA256 = "615f55e6d11dc878108ab7368c0da74e7288b9a65e168ded110a39b0569337c8"
SOURCE_PROFILE = None


def without_chroot(profile):
    """Remove only whole singleton chroot rules; retain every other JSON value."""
    return {
        **profile,
        "syscalls": [rule for rule in profile["syscalls"] if rule["names"] != ["chroot"]],
    }


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ChromiumSeccompContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (SECURITY / "chromium-seccomp.json").read_bytes()
        cls.profile = json.loads(cls.raw)
        cls.identity = json.loads((SECURITY / "identity.json").read_text())

    def test_reviewed_file_and_source_pins(self):
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), PROFILE_SHA256)
        self.assertEqual(self.identity["profileSha256"], PROFILE_SHA256)
        self.assertEqual(self.identity["sourceSha256"], SOURCE_SHA256)
        self.assertEqual(self.identity["withoutChrootCanonicalSha256"], UNCHANGED_SHA256)
        self.assertEqual(self.identity["source"], "ai-harness:/usr/share/containers/seccomp.json")

    def test_all_non_chroot_policy_matches_reviewed_host_snapshot(self):
        unchanged = without_chroot(self.profile)
        self.assertEqual(len(unchanged["syscalls"]), 33)
        self.assertEqual(canonical_sha256(unchanged), UNCHANGED_SHA256)

    def test_only_one_unconditional_chroot_allow(self):
        rules = [rule for rule in self.profile["syscalls"] if "chroot" in rule["names"]]
        self.assertEqual(rules, [{
            "names": ["chroot"],
            "action": "SCMP_ACT_ALLOW",
            "args": [],
            "comment": "Chromium nested user-namespace sandbox chroot; container remains cap-drop ALL and no-new-privileges.",
            "includes": {},
            "excludes": {},
        }])
        self.assertEqual(len(self.profile["syscalls"]), 34)

    def test_default_deny_and_errno_are_retained(self):
        self.assertEqual(self.profile["defaultAction"], "SCMP_ACT_ERRNO")
        self.assertEqual(self.profile["defaultErrnoRet"], 38)
        self.assertEqual(self.profile["defaultErrno"], "ENOSYS")

    def test_optional_original_snapshot_comparison(self):
        if SOURCE_PROFILE is None:
            self.skipTest("Pass --source-profile PATH for original host snapshot comparison")
        raw = SOURCE_PROFILE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SOURCE_SHA256)
        source = json.loads(raw)
        rules = [rule for rule in source["syscalls"] if "chroot" in rule["names"]]
        self.assertEqual(rules, [
            {"names": ["chroot"], "action": "SCMP_ACT_ALLOW", "args": [],
             "comment": "", "includes": {"caps": ["CAP_SYS_CHROOT"]}, "excludes": {}},
            {"names": ["chroot"], "action": "SCMP_ACT_ERRNO", "args": [],
             "comment": "", "includes": {}, "excludes": {"caps": ["CAP_SYS_CHROOT"]},
             "errnoRet": 1, "errno": "EPERM"},
        ])
        self.assertEqual(canonical_sha256(without_chroot(source)), UNCHANGED_SHA256)
        self.assertEqual(without_chroot(source), without_chroot(self.profile))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--source-profile", type=Path)
    options, remaining = parser.parse_known_args()
    SOURCE_PROFILE = options.source_profile
    unittest.main(argv=[sys.argv[0], *remaining])
