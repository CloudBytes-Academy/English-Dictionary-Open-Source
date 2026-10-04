"""Run every Python and SQL example in USAGE.md against the files in this repo."""

import contextlib
import subprocess
import sys
import unittest

import duckdb

from data_contract import RAW_MAIN, ROOT, usage_blocks


class UsageExamplesTest(unittest.TestCase):
    def test_python_examples(self):
        for number, code in enumerate(usage_blocks("python"), 1):
            with self.subTest(block=number, first_line=code.splitlines()[0]):
                result = subprocess.run(
                    [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr[-2000:])
                self.assertTrue(result.stdout.strip(), "the example printed nothing")

    def test_sql_examples(self):
        # The remote example runs offline here against the same file in the
        # checkout. remote_checks.py runs it against GitHub.
        email, synonyms = usage_blocks("sql")
        email = email.replace(f"{RAW_MAIN}/", "")
        with contextlib.chdir(ROOT):
            email_rows = duckdb.sql(email).fetchall()
            synonym_rows = duckdb.sql(synonyms).fetchall()
        self.assertEqual(
            sorted((word, pos, source) for word, pos, _, source in email_rows),
            [("email", "noun", "oewn")] * 3 + [("email", "verb", "oewn")],
        )
        self.assertEqual({word for (word,) in synonym_rows}, {"glad", "felicitous", "well-chosen"})
        self.assertEqual(len(synonym_rows), 3)


if __name__ == "__main__":
    unittest.main()
