"""Query each format the way people use it: SQLite, MariaDB, pandas, and DuckDB.

The MariaDB import runs only when MYSQL_HOST names a server, because it needs
one. Set MYSQL_TCP_PORT, MYSQL_USER (default root), and MYSQL_PWD as needed.
"""

import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import unittest
import uuid
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import duckdb
import pandas as pd
import pyarrow.parquet as pq

from data_contract import RAW_MAIN, ROOT, usage_blocks

PARQUET = ROOT / "v2/dictionary.parquet"
JSONL = ROOT / "v2/dictionary.jsonl.gz"


class SQLiteQueryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "sqlite3/dictionary.db"
        cls.connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        cls.addClassCleanup(cls.connection.close)

    def plan(self, query):
        return [row[3] for row in self.connection.execute("EXPLAIN QUERY PLAN " + query)]

    def test_word_lookup_uses_index(self):
        query = "SELECT * FROM entries WHERE word = 'computer'"
        self.assertEqual(
            self.connection.execute(query).fetchall(),
            [("computer", "n.", "One who computes.")],
        )
        self.assertEqual(
            self.plan(query), ["SEARCH entries USING INDEX ix_entries_word (word=?)"],
        )

    def test_lowercase_lookup_scans_table(self):
        # The README documents this full scan. The index is on word, not lower(word).
        query = "SELECT * FROM entries WHERE lower(word) = 'computer'"
        self.assertEqual(len(self.connection.execute(query).fetchall()), 1)
        self.assertEqual(self.plan(query), ["SCAN entries"])


@unittest.skipUnless(os.environ.get("MYSQL_HOST"), "MYSQL_HOST is not set")
class MariaDBImportTest(unittest.TestCase):
    def client(self, *args, stdin=None):
        program = shutil.which("mariadb") or shutil.which("mysql")
        if program is None:
            self.fail("MYSQL_HOST is set, but no mariadb or mysql client is on PATH")
        user = os.environ.get("MYSQL_USER", "root")
        return subprocess.run(
            [program, f"--user={user}", "--batch", "--skip-column-names", *args],
            stdin=stdin, capture_output=True, text=True, check=True,
        ).stdout

    def test_dump_imports(self):
        # A new name per run, so the test never drops a database it did not create.
        database = f"english_dictionary_test_{uuid.uuid4().hex}"
        self.client("-e", f"CREATE DATABASE {database}")
        self.addCleanup(self.client, "-e", f"DROP DATABASE {database}")
        with (ROOT / "mysql/dictionaryStudyTool.sql").open("rb") as dump:
            self.client(database, stdin=dump)
        count = self.client(database, "-e", "SELECT COUNT(*) FROM entries")
        self.assertEqual(count.strip(), "176023")


class ParquetQueryTest(unittest.TestCase):
    def test_pandas(self):
        df = pd.read_parquet(PARQUET)
        self.assertEqual(len(df), 388_587)
        email = df[df["word"].str.lower() == "email"]
        self.assertEqual(Counter(email["pos"]), {"noun": 3, "verb": 1})

    def test_duckdb(self):
        rows = duckdb.sql(
            f"SELECT pos FROM '{PARQUET}' WHERE lower(word) = 'email'"
        ).fetchall()
        self.assertEqual(Counter(pos for (pos,) in rows), {"noun": 3, "verb": 1})


class JSONLQueryTest(unittest.TestCase):
    """Three readers must return the Parquet rows, in the Parquet order."""

    @classmethod
    def setUpClass(cls):
        cls.ids = pq.read_table(PARQUET, columns=["id"]).column("id").to_pylist()

    def test_standard_library(self):
        with gzip.open(JSONL, "rt", encoding="utf-8") as file:
            ids = [json.loads(line)["id"] for line in file]
        self.assertEqual(ids, self.ids)

    def test_pandas(self):
        df = pd.read_json(JSONL, lines=True, dtype=False)
        self.assertEqual(df["id"].tolist(), self.ids)

    def test_duckdb(self):
        rows = duckdb.sql(f"SELECT id FROM read_json('{JSONL}')").fetchall()
        self.assertEqual([row_id for (row_id,) in rows], self.ids)


class RangeHandler(BaseHTTPRequestHandler):
    """Serve the Parquet file with HTTP range support, and count the bytes sent."""

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(PARQUET.stat().st_size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        data = PARQUET.read_bytes()
        unit, _, span = self.headers.get("Range", "").partition("=")
        if unit == "bytes":
            first, _, last = span.partition("-")
            start = int(first)
            end = int(last) if last else len(data) - 1
            body = data[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{start + len(body) - 1}/{len(data)}")
        else:
            body = data
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(body)
        with self.server.lock:
            self.server.bytes_sent += len(body)
            self.server.requests += 1

    def log_message(self, *args):
        pass


class ParquetOverHTTPTest(unittest.TestCase):
    """The USAGE.md query reads a small part of the file over HTTP.

    Readers skip blocks of rows by their min/max statistics. A layout change
    that defeats this makes DuckDB fetch the whole 18.5 MB file.
    """

    BUDGET = 3_000_000

    def test_usage_query_stays_within_byte_budget(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
        server.lock = threading.Lock()
        server.bytes_sent = server.requests = 0
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        query = usage_blocks("sql")[0]
        remote = f"{RAW_MAIN}/v2/dictionary.parquet"
        self.assertIn(remote, query)
        local = f"http://127.0.0.1:{server.server_port}/dictionary.parquet"
        with duckdb.connect() as connection:
            connection.execute("SET enable_http_metadata_cache = false")
            rows = connection.execute(query.replace(remote, local)).fetchall()

        self.assertEqual(len(rows), 4)
        self.assertLess(server.bytes_sent, self.BUDGET, f"{server.requests} requests")


if __name__ == "__main__":
    unittest.main()
