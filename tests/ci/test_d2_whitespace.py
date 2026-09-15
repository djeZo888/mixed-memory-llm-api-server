"""Exercise the actual D2 workflow whitespace step using disposable Git histories."""

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/d2-lifecycle.yml"
ZERO = "0" * 40


class WhitespaceRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = WORKFLOW.read_text()
        final_step = source.split("      - name: Check whitespace\n", 1)[1]
        cls.check_script = textwrap.dedent(final_step.split("        run: |\n", 1)[1])
        if "${{" in cls.check_script:
            raise AssertionError("Event expressions must be passed through env, not shell code")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="d2-whitespace-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.new_repo("work")
        self.base = self.git("rev-parse", "HEAD")

    def run_command(self, argv, repo=None, env=None):
        command_env = os.environ.copy()
        command_env.update({
            "GIT_AUTHOR_NAME": "D2 Fixture", "GIT_COMMITTER_NAME": "D2 Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        })
        if env:
            command_env.update(env)
        return subprocess.run(argv, cwd=repo or self.repo, env=command_env,
                              text=True, capture_output=True, timeout=30, check=False)

    def git(self, *args, repo=None):
        result = self.run_command(["git", *args], repo=repo)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def new_repo(self, name, inherited=True):
        repo = self.root / name
        repo.mkdir()
        self.git("init", "--initial-branch=main", repo=repo)
        self.commit("legacy.txt", "historic evidence  \n" if inherited else "clean\n", repo)
        return repo

    def commit(self, filename, content, repo=None):
        repo = repo or self.repo
        (repo / filename).write_text(content)
        self.git("add", "--", filename, repo=repo)
        self.git("commit", "-m", "Fixture change: " + filename, repo=repo)
        return self.git("rev-parse", "HEAD", repo=repo)

    def check(self, event="push", before=None, base=None, repo=None, **overrides):
        repo = repo or self.repo
        env = {
            "D2_EVENT_NAME": event,
            "D2_HEAD_SHA": self.git("rev-parse", "HEAD", repo=repo),
            "D2_PR_BASE_SHA": base or self.base,
            "D2_PUSH_BEFORE_SHA": self.base if before is None else before,
            "D2_DEFAULT_BRANCH": "main",
        }
        env.update(overrides)
        return self.run_command(["bash", "-c", self.check_script], repo, env)

    def assert_pass(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_fail(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_whitespace_failure(self, result):
        self.assert_fail(result)
        self.assertIn("trailing whitespace", result.stdout + result.stderr)

    def test_push_multicommit_ignores_inherited_and_checks_whole_range(self):
        self.commit("first.txt", "first clean change\n")
        self.commit("second.txt", "second clean change\n")
        self.assert_pass(self.check())
        self.commit("new.txt", "introduced whitespace  \n")
        self.commit("last.txt", "clean final commit\n")
        self.assert_whitespace_failure(self.check())

    def test_pr_merge_uses_recorded_base_and_detects_new_whitespace(self):
        self.git("checkout", "-b", "contributor")
        self.commit("contribution.txt", "clean contribution\n")
        self.git("checkout", "main")
        pr_base = self.commit("target-history.txt", "inherited target whitespace  \n")
        self.git("checkout", "contributor")
        self.git("merge", "--no-ff", "main", "-m", "Synthetic PR merge")
        self.assert_pass(self.check(event="pull_request", base=pr_base))
        self.commit("new.txt", "new PR whitespace  \n")
        self.assert_whitespace_failure(self.check(event="pull_request", base=pr_base))

    def test_shallow_legacy_failure_then_full_history_passes(self):
        self.commit("new.txt", "clean contribution\n")
        shallow = self.root / "shallow"
        self.git("clone", "--depth=1", self.repo.as_uri(), str(shallow))
        legacy = self.run_command(["git", "show", "--format=", "--check", "HEAD"], shallow)
        self.assert_whitespace_failure(legacy)
        self.assert_fail(self.check(repo=shallow))
        self.git("fetch", "--unshallow", "origin", repo=shallow)
        self.assert_pass(self.check(repo=shallow))

    def test_force_push_uses_nonancestor_before(self):
        before = self.commit("old-tip.txt", "previous branch tip\n")
        self.git("checkout", "-b", "replacement", self.base)
        self.commit("replacement.txt", "replacement branch tip\n")
        self.assert_pass(self.check(before=before))
        self.commit("bad.txt", "new whitespace  \n")
        self.assert_whitespace_failure(self.check(before=before))

    def test_first_push_uses_default_branch_merge_base(self):
        default_tip = self.commit("legacy.txt", "target cleaned its historical evidence\n")
        self.git("update-ref", "refs/remotes/origin/main", default_tip)
        self.git("checkout", "-b", "feature", self.base)
        self.commit("new.txt", "clean branch contribution\n")
        self.assert_pass(self.check(before=ZERO))
        self.commit("bad.txt", "new whitespace  \n")
        self.assert_whitespace_failure(self.check(before=ZERO))

    def test_first_root_push_checks_entire_tree(self):
        fresh = self.new_repo("fresh", inherited=False)
        self.assert_pass(self.check(before=ZERO, repo=fresh))
        self.commit("bad.txt", "initial content whitespace  \n", fresh)
        self.assert_whitespace_failure(self.check(before=ZERO, repo=fresh))

    def test_first_push_missing_default_ref_checks_inherited_tree(self):
        self.commit("new.txt", "clean contribution\n")
        self.assert_whitespace_failure(self.check(before=ZERO))

    def test_first_push_default_base_equal_head_checks_entire_tree(self):
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.assert_whitespace_failure(self.check(before=ZERO))

    def test_first_push_unrelated_default_branch_checks_entire_tree(self):
        self.git("checkout", "--orphan", "unrelated")
        self.git("rm", "-rf", ".")
        unrelated = self.commit("unrelated.txt", "unrelated default history\n")
        self.git("update-ref", "refs/remotes/origin/main", unrelated)
        self.git("checkout", "main")
        self.assert_whitespace_failure(self.check(before=ZERO))

    def test_invalid_metadata_refuses_without_shell_execution(self):
        self.commit("new.txt", "clean contribution\n")
        for field in ("D2_HEAD_SHA", "D2_PR_BASE_SHA", "D2_PUSH_BEFORE_SHA"):
            event = "pull_request" if field == "D2_PR_BASE_SHA" else "push"
            for value in ("$(touch INJECTED)", "-" + "a" * 39, "a" * 39, "g" * 40):
                with self.subTest(field=field, value=value):
                    self.assert_fail(self.check(event=event, **{field: value}))
                    self.assertFalse((self.repo / "INJECTED").exists())
        for field in ("D2_HEAD_SHA", "D2_PR_BASE_SHA"):
            self.assert_fail(self.check(event="pull_request", **{field: ZERO}))
        self.assert_fail(self.check(event="workflow_dispatch"))

    def test_shell_looking_valid_default_ref_is_literal(self):
        branch = "topic;touch${IFS}INJECTED"
        self.git("check-ref-format", "refs/heads/" + branch)
        self.git("update-ref", "refs/remotes/origin/" + branch, self.base)
        self.commit("new.txt", "clean contribution\n")
        self.assert_pass(self.check(before=ZERO, D2_DEFAULT_BRANCH=branch))
        self.assertFalse((self.repo / "INJECTED").exists())
        self.assert_fail(self.check(before=ZERO, D2_DEFAULT_BRANCH="../bad"))

    def test_missing_before_is_fetched_from_local_origin(self):
        clone = self.root / "clone"
        self.git("clone", self.repo.as_uri(), str(clone))
        remote_before = self.commit("remote.txt", "remote prior branch tip\n")
        self.commit("local.txt", "local replacement tip\n", clone)
        absent = self.run_command(["git", "cat-file", "-e", remote_before], clone)
        self.assert_fail(absent)
        self.assert_pass(self.check(before=remote_before, repo=clone))
        self.git("cat-file", "-e", remote_before, repo=clone)
        self.assert_fail(self.check(before="1" * 40, repo=clone))

    def test_wrong_object_head_mismatch_and_nonancestor_pr_refuse(self):
        self.commit("new.txt", "clean contribution\n")
        blob = self.git("rev-parse", "HEAD:legacy.txt")
        self.assert_fail(self.check(before=blob))
        self.assert_fail(self.check(event="pull_request", base=blob))
        self.assert_fail(self.check(D2_HEAD_SHA=self.base))
        current = self.git("rev-parse", "HEAD")
        self.git("checkout", "-b", "other", self.base)
        divergent = self.commit("other.txt", "divergent target\n")
        self.git("checkout", "--detach", current)
        self.assert_fail(self.check(event="pull_request", base=divergent))


if __name__ == "__main__":
    unittest.main()
