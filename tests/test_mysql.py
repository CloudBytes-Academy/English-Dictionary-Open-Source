"""Check the dump's structure and raw rows, without a database server."""

import hashlib
import re
import unittest
from collections import Counter

from data_contract import (
    ROOT, V1_HASHES, MALFORMED_MYSQL, TRUNCATED_WORDTYPES,
    assert_malformed_headwords, assert_v1_samples,
)

# Parse the dump independently of the v2 builder. Restrict parsing to INSERTs
# and require every character of each payload to be consumed.
TUPLE = re.compile(r"\('((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)'\)")
ESCAPES = {"0": "\0", "b": "\b", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a"}


class MySQLTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / "mysql/dictionaryStudyTool.sql"
        cls.sql = cls.path.read_text(encoding="latin-1")
        cls.rows = []
        inserts = re.findall(r"^INSERT INTO `entries` VALUES (.*);$", cls.sql, re.M)
        if not inserts:
            raise AssertionError("No entries INSERT statements found")
        for payload in inserts:
            offset = 0
            while offset < len(payload):
                match = TUPLE.match(payload, offset)
                if match is None:
                    raise AssertionError(f"Unparsed INSERT payload at offset {offset}")
                fields = [
                    re.sub(r"\\(.)", lambda m: ESCAPES.get(m[1], m[1]), s)
                    for s in match.groups()
                ]
                cls.rows.append(dict(zip(("word", "wordtype", "definition"), fields)))
                offset = match.end()
                if offset < len(payload):
                    if payload[offset] != "," or offset + 1 == len(payload):
                        raise AssertionError(f"Invalid tuple separator at offset {offset}")
                    offset += 1

    def test_original_hash(self):
        self.assertEqual(
            hashlib.sha256(self.path.read_bytes()).hexdigest(),
            V1_HASHES["mysql/dictionaryStudyTool.sql"],
        )

    def test_schema(self):
        schemas = re.findall(r"CREATE TABLE `entries` \((.*?)\) ENGINE=([^;]+);", self.sql, re.S)
        self.assertEqual(len(schemas), 1)
        columns, storage = schemas[0]
        self.assertEqual([line.strip() for line in columns.strip().splitlines()], [
            "`word` varchar(25) NOT NULL,",
            "`wordtype` varchar(20) NOT NULL,",
            "`definition` text NOT NULL",
        ])
        self.assertEqual(storage, "MyISAM DEFAULT CHARSET=latin1")

    def test_row_count(self):
        self.assertEqual(len(self.rows), 176_023)

    def test_samples(self):
        assert_v1_samples(self, self.rows, mysql=True)

    def test_known_defects(self):
        assert_malformed_headwords(self, self.rows, MALFORMED_MYSQL)
        self.assertEqual(len(TRUNCATED_WORDTYPES), 22)
        self.assertEqual(
            Counter(r["wordtype"] for r in self.rows if len(r["wordtype"]) == 20),
            TRUNCATED_WORDTYPES,
        )
        self.assertTrue(all(len(r["wordtype"]) <= 20 for r in self.rows))


if __name__ == "__main__":
    unittest.main()
