"""Read the original SQLite file without creating or changing it."""

import hashlib
import sqlite3
import unittest
from data_contract import (
    ROOT, V1_HASHES, MALFORMED_V1, assert_malformed_headwords, assert_v1_samples,
)


class SQLiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "sqlite3/dictionary.db"
        cls.connection = sqlite3.connect(cls.path.as_uri() + "?mode=ro", uri=True)
        cls.addClassCleanup(cls.connection.close)
        cls.rows = [
            dict(zip(("word", "wordtype", "definition"), row))
            for row in cls.connection.execute(
                "SELECT word, wordtype, definition FROM entries ORDER BY rowid"
            )
        ]

    def test_original_hash(self):
        self.assertEqual(
            hashlib.sha256(self.path.read_bytes()).hexdigest(),
            V1_HASHES["sqlite3/dictionary.db"],
        )

    def test_schema(self):
        objects = self.connection.execute(
            "SELECT type, name FROM sqlite_master ORDER BY type, name"
        ).fetchall()
        self.assertEqual(objects, [("index", "ix_entries_word"), ("table", "entries")])
        self.assertEqual(self.connection.execute("PRAGMA table_info(entries)").fetchall(), [
            (0, "word", "TEXT", 0, None, 0),
            (1, "wordtype", "TEXT", 0, None, 0),
            (2, "definition", "TEXT", 0, None, 0),
        ])
        self.assertEqual(
            self.connection.execute("PRAGMA index_info(ix_entries_word)").fetchall(),
            [(0, 0, "word")],
        )

    def test_structure(self):
        self.assertEqual(len(self.rows), 176_023)
        self.assertEqual(len({r["word"] for r in self.rows}), 111_573)
        self.assertEqual(sum(r["wordtype"] is None for r in self.rows), 3_895)
        self.assertEqual(
            [r["word"] for r in self.rows if r["definition"] is None], ["antic", "piracy"],
        )
        self.assertEqual(sum(r["word"] == "#name?" for r in self.rows), 224)

    def test_samples(self):
        assert_v1_samples(self, self.rows, sqlite=True)

    def test_known_defects(self):
        assert_malformed_headwords(self, self.rows, MALFORMED_V1)


if __name__ == "__main__":
    unittest.main()
