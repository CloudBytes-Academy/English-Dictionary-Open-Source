"""Check the public download URLs. These need network, so run them separately:
    uv run --with 'pyarrow>=15' --with duckdb --with pandas \
        python -m unittest discover tests -p 'remote_*.py'

At least 13 public repos download the v1 files by URL. The old UberPython
raw URLs do not answer with an HTTP redirect: GitHub serves the moved files
from them directly. The old repository page answers with a 301.
"""

import hashlib
import unittest
import urllib.request

import duckdb

from data_contract import RAW_MAIN, V1_HASHES, usage_blocks

OLD_REPO = "UberPython/English-Dictionary-Open-Source"
NEW_REPO = "CloudBytes-Academy/English-Dictionary-Open-Source"


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.status, response.url, response.read()


class RemoteAccessTest(unittest.TestCase):
    def assert_pinned(self, url, name):
        status, _, body = fetch(url)
        self.assertEqual(status, 200)
        self.assertEqual(hashlib.sha256(body).hexdigest(), V1_HASHES[name])

    def test_raw_urls_serve_pinned_files(self):
        for name in ("csv/dictionary.csv", "sqlite3/dictionary.db"):
            with self.subTest(name=name):
                self.assert_pinned(f"{RAW_MAIN}/{name}", name)

    def test_old_raw_urls_serve_pinned_files(self):
        for name in ("csv/dictionary.csv", "sqlite3/dictionary.db"):
            with self.subTest(name=name):
                self.assert_pinned(f"https://raw.githubusercontent.com/{OLD_REPO}/main/{name}", name)

    def test_old_repository_redirects(self):
        status, url, _ = fetch(f"https://github.com/{OLD_REPO}")
        self.assertEqual((status, url), (200, f"https://github.com/{NEW_REPO}"))

    def test_duckdb_reads_parquet_over_https(self):
        query = usage_blocks("sql")[0]
        self.assertIn(f"{RAW_MAIN}/v2/dictionary.parquet", query)
        rows = duckdb.sql(query).fetchall()
        self.assertEqual(
            sorted((word, pos, source) for word, pos, _, source in rows),
            [("email", "noun", "oewn")] * 3 + [("email", "verb", "oewn")],
        )


if __name__ == "__main__":
    unittest.main()
