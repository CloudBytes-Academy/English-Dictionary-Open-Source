"""Check local signoff arguments without running the checks or posting a status."""

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
