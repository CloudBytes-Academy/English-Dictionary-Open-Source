"""Read and check the gzipped JSON Lines with the Python standard library."""

import gzip
import json
import unittest
from collections import Counter

from data_contract import ROOT, MALFORMED_V2, assert_malformed_headwords, assert_v2_samples


class JSONLTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(ROOT / "v2/dictionary.jsonl.gz", "rt", encoding="utf-8") as file:
            cls.rows = [json.loads(line) for line in file]

    def test_structure(self):
        required = {"id", "word", "definition", "source"}
        optional = {"pos", "wordtype", "synset_id"}
        for row in self.rows:
            self.assertEqual(set(row), required | optional | {"examples"})
            self.assertTrue(all(isinstance(row[key], str) for key in required))
            self.assertTrue(all(
                row[key] is None or isinstance(row[key], str) for key in optional
            ))
            self.assertIsInstance(row["examples"], list)
            self.assertTrue(all(isinstance(example, str) for example in row["examples"]))
        self.assertEqual(
            Counter(r["source"] for r in self.rows), {"webster1913": 175_928, "oewn": 212_659},
        )

    def test_samples(self):
        assert_v2_samples(self, self.rows)

    def test_known_defects(self):
        webster = [r for r in self.rows if r["source"] == "webster1913"]
        assert_malformed_headwords(self, webster, MALFORMED_V2)


if __name__ == "__main__":
    unittest.main()
