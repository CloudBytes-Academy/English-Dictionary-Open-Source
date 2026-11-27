"""Check local signoff without running the checks or posting a status.

The refusal tests replace subprocess.run with a fake, so they build nothing,
use no network, and never call GitHub.
"""

import contextlib
import importlib.util
import io
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "local_ci", Path(__file__).resolve().parent.parent / "scripts" / "local_ci.py",
)
local_ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local_ci)


class LocalCITest(unittest.TestCase):
    def test_default_signoff(self):
        self.assertFalse(local_ci.parse_args([]).no_signoff)

    def test_no_signoff(self):
        self.assertTrue(local_ci.parse_args(["--no-signoff"]).no_signoff)

    def test_unknown_argument(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                local_ci.parse_args(["--no-signof"])
        self.assertEqual(error.exception.code, 2)

    def test_help(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                local_ci.parse_args(["--help"])
        self.assertEqual(error.exception.code, 0)


SHA = "a" * 40
REPO = "owner/repo"


class FakeGitAndGitHub:
    """Answer the git, uv and gh commands that local_ci.main runs, and record them.

    Each argument sets one condition of the run. `heads` is the HEAD that
    each `git rev-parse HEAD` returns, in order.
    """

    def __init__(self, *, dirty_before="", dirty_after="", v2_changed="",
                 rebuild_ok=True, tests_ok=True, heads=(SHA, SHA), on_github=True):
        # main() reads the status twice when it refuses a dirty tree, to show it.
        self.dirty = [dirty_before] * (2 if dirty_before else 1) + [dirty_after]
        self.v2_changed = v2_changed
        self.rebuild_ok, self.tests_ok, self.on_github = rebuild_ok, tests_ok, on_github
        self.heads = list(heads)
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        output, code = "", 0
        if command[:2] == ["git", "status"]:
            output = self.v2_changed if "--" in command else self.dirty.pop(0)
        elif command[:3] == ["git", "rev-parse", "HEAD"]:
            output = self.heads.pop(0)
        elif command == ["uv", "run", "scripts/build_v2.py"]:
            code = 0 if self.rebuild_ok else 1
        elif command == local_ci.TESTS:
            code = 0 if self.tests_ok else 1
        elif command[:3] == ["gh", "repo", "view"]:
            output = REPO
        elif command[:2] == ["gh", "api"] and "POST" not in command:
            code = 0 if self.on_github else 1
        elif command[:4] != ["gh", "api", "--method", "POST"]:
            raise AssertionError(f"unexpected command: {command}")
        return subprocess.CompletedProcess(command, code, stdout=output, stderr="")

    def posts(self):
        return [c for c in self.commands if c[:4] == ["gh", "api", "--method", "POST"]]


class SignoffTest(unittest.TestCase):
    def run_main(self, fake, *args, mysql_host=None):
        env = {k: v for k, v in os.environ.items() if k != "MYSQL_HOST"}
        if mysql_host:
            env["MYSQL_HOST"] = mysql_host
        with mock.patch.object(local_ci.subprocess, "run", fake), \
                mock.patch.object(local_ci.sys, "argv", ["local_ci.py", *args]), \
                mock.patch.dict(os.environ, env, clear=True), \
                contextlib.redirect_stdout(io.StringIO()):
            local_ci.main()

    def assert_refuses(self, fake, message):
        with self.assertRaises(SystemExit) as error:
            self.run_main(fake)
        self.assertIn(message, str(error.exception))
        self.assertEqual(fake.posts(), [])

    def test_refuses_dirty_worktree(self):
        fake = FakeGitAndGitHub(dirty_before=" M README.md")
        self.assert_refuses(fake, "The worktree is not clean")
        self.assertNotIn(["uv", "run", "scripts/build_v2.py"], fake.commands)

    def test_refuses_when_rebuild_fails(self):
        self.assert_refuses(FakeGitAndGitHub(rebuild_ok=False), "FAILED: rebuild v2")

    def test_refuses_when_rebuild_changes_v2(self):
        fake = FakeGitAndGitHub(v2_changed=" M v2/dictionary.parquet")
        self.assert_refuses(fake, "the rebuild changed v2/")
        self.assertNotIn(local_ci.TESTS, fake.commands)

    def test_refuses_when_tests_fail(self):
        self.assert_refuses(FakeGitAndGitHub(tests_ok=False), "FAILED: offline tests")

    def test_refuses_when_head_moves(self):
        fake = FakeGitAndGitHub(heads=(SHA, "b" * 40))
        self.assert_refuses(fake, "The commit or worktree changed during the run")

    def test_refuses_when_worktree_changes_during_run(self):
        fake = FakeGitAndGitHub(dirty_after="?? new-file")
        self.assert_refuses(fake, "The commit or worktree changed during the run")

    def test_refuses_commit_github_does_not_have(self):
        self.assert_refuses(FakeGitAndGitHub(on_github=False), f"GitHub does not have {SHA}")

    def test_posts_signoff_when_everything_passes(self):
        fake = FakeGitAndGitHub()
        self.run_main(fake)
        self.assertEqual(fake.posts(), [[
            "gh", "api", "--method", "POST", f"repos/{REPO}/statuses/{SHA}", "--silent",
            "-f", "state=success", "-f", "context=signoff",
            "-f", "description=Local CI: build and tests without MariaDB",
        ]])

    def test_description_drops_mariadb_note_when_mysql_host_is_set(self):
        fake = FakeGitAndGitHub()
        self.run_main(fake, mysql_host="db.example")
        self.assertEqual(fake.posts()[0][-1], "description=Local CI: build and tests")

    def test_no_signoff_runs_checks_without_posting(self):
        fake = FakeGitAndGitHub(dirty_before=" M README.md")
        self.run_main(fake, "--no-signoff")
        self.assertIn(local_ci.TESTS, fake.commands)
        self.assertEqual(fake.posts(), [])


if __name__ == "__main__":
    unittest.main()
