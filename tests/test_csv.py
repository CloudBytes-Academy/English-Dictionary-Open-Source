"""Pin the original CSV, including its known defects."""

import csv
import hashlib
import unittest
from data_contract import (
    ROOT, V1_HASHES, MALFORMED_V1, assert_malformed_headwords, assert_v1_samples,
)


class CSVTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "csv/dictionary.csv"
        with cls.path.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            cls.header = reader.fieldnames
            cls.rows = list(reader)

    def test_original_hash(self):
        self.assertEqual(
            hashlib.sha256(self.path.read_bytes()).hexdigest(),
            V1_HASHES["csv/dictionary.csv"],
        )

    def test_structure(self):
        self.assertEqual(self.header, ["word", "wordtype", "definition"])
        self.assertEqual(len(self.rows), 176_023)
        for row in self.rows:
            self.assertEqual(set(row), set(self.header))
            self.assertTrue(all(isinstance(value, str) for value in row.values()))
        self.assertEqual(sum(r["wordtype"] == "" for r in self.rows), 3_895)
        self.assertEqual(
            [r["word"] for r in self.rows if r["definition"] == ""], ["antic", "piracy"],
        )
        self.assertEqual(sum(r["word"] == "#NAME?" for r in self.rows), 224)
        self.assertEqual(sum("\n" in r["definition"] for r in self.rows), 75_492)
        self.assertIn("\n   capital A", self.rows[0]["definition"])

    def test_samples(self):
        assert_v1_samples(self, self.rows)

    def test_known_defects(self):
        assert_malformed_headwords(self, self.rows, MALFORMED_V1)


if __name__ == "__main__":
    unittest.main()
