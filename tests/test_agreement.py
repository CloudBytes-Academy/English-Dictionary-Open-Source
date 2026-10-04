"""Compare the five files row by row. Every allowed difference is listed and
counted, so any other difference fails. test_v2.py already compares the
JSONL and Parquet rows.

Run with:
    uv run --with 'pyarrow>=15' --with duckdb --with pandas python -m unittest discover tests
"""

import csv
import gzip
import json
import sqlite3
import unittest
from collections import Counter

import pyarrow.compute as pc
import pyarrow.parquet as pq

from data_contract import ROOT, parse_mysql_rows

FIELDS = ("word", "wordtype", "definition")

# v1 dump rows (1-based) that have no v2 row. Each duplicate equals an earlier
# dump row after v2 cleaning. 92 are byte-identical; row 78738, `indices`
# `pl. `, matches only after case folding and whitespace collapse.
DUPLICATE_ROWS = (
    4023, 4080, 4387, 9613, 15206, 15634, 16225, 16226, 17226, 17227, 17228,
    17841, 17842, 18187, 18188, 18697, 18698, 19042, 19189, 20159, 20160,
    27191, 27192, 28291, 28296, 32013, 38651, 41234, 41546, 41601, 47039,
    49281, 62230, 62231, 64997, 65945, 67191, 67995, 71250, 72548, 73030,
    74210, 75288, 77870, 77871, 78738, 83928, 85418, 87726, 87929, 88969,
    89158, 89159, 89160, 91232, 91233, 93043, 98084, 98088, 98095, 98212,
    99280, 100661, 101872, 101873, 111553, 111555, 115534, 115535, 118423,
    118673, 120338, 125494, 125496, 131136, 131453, 137019, 143700, 145347,
    146190, 146192, 146530, 146785, 147966, 150618, 158437, 165545, 169335,
    171815, 173631, 173636, 173637, 173638,
)
EMPTY_DEFINITION_ROWS = {6905: "Antic", 114947: "Piracy"}

# Mac Roman bytes, saved as UTF-8, then read as Latin-1. Counts are
# occurrences in the dump's definitions.
MOJIBAKE = {"Â¡": ("°", 67), "Â£": ("£", 6), "Ã\x96": ("÷", 2), "Ã\x83": ("√", 11)}
# In these rows the "√" byte stands for "§" in a section reference: "§155".
SECTION_SIGN_ROWS = {38227, 55921, 137098, 142325}

V1_V2_DIFFERENCES = {
    "word lowercased": 175_584,
    "word whitespace collapsed": 2,
    "wordtype whitespace collapsed": 3_479,
    "wordtype empty -> null": 3_882,
    "definition whitespace collapsed": 75_489,
    "definition encoding repaired": 72,
}


# The sample word that also has WordNet rows in v2.
SAMPLE_WORD = "computer"


def squash(text):
    return " ".join(text.split())


def repair(text, row):
    for broken, (fixed, _) in MOJIBAKE.items():
        if broken == "Ã\x83" and row in SECTION_SIGN_ROWS:
            fixed = "§"
        text = text.replace(broken, fixed)
    return text


class AgreementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "csv/dictionary.csv").open(encoding="utf-8", newline="") as file:
            cls.csv = list(csv.DictReader(file))
        connection = sqlite3.connect(
            (ROOT / "sqlite3/dictionary.db").as_uri() + "?mode=ro", uri=True
        )
        cls.sqlite = [
            dict(zip(FIELDS, row))
            for row in connection.execute(
                "SELECT word, wordtype, definition FROM entries ORDER BY rowid"
            )
        ]
        connection.close()
        cls.mysql = parse_mysql_rows(
            (ROOT / "mysql/dictionaryStudyTool.sql").read_text(encoding="latin-1")
        )
        # Keep only the v2 rows the tests read: all Webster's rows, and the
        # WordNet sample rows. test_v2.py compares the full JSONL and Parquet.
        table = pq.read_table(ROOT / "v2/dictionary.parquet")
        cls.parquet = table.filter(pc.or_(
            pc.equal(table["source"], "webster1913"), pc.equal(table["word"], SAMPLE_WORD),
        )).to_pylist()
        del table
        with gzip.open(ROOT / "v2/dictionary.jsonl.gz", "rt", encoding="utf-8") as file:
            cls.jsonl = [
                row for row in map(json.loads, file)
                if row["id"] in ("webster1913-000362", "webster1913-010213")
                or row["word"] == SAMPLE_WORD
            ]

    @classmethod
    def tearDownClass(cls):
        # Release the rows so later test classes do not hold them too.
        del cls.csv, cls.sqlite, cls.mysql, cls.parquet, cls.jsonl

    def assert_differences(self, differences, unexpected, expected):
        # Show the first unexpected rows: they name the file that drifted.
        self.assertEqual(unexpected[:10], [], f"{len(unexpected)} unexpected differences")
        self.assertEqual(differences, expected)

    def test_csv_matches_sqlite(self):
        self.assertEqual(len(self.csv), len(self.sqlite))
        differences, unexpected = Counter(), []
        for row, (c, s) in enumerate(zip(self.csv, self.sqlite), start=1):
            for field in FIELDS:
                if c[field] == s[field]:
                    continue
                if field != "word" and c[field] == "" and s[field] is None:
                    differences[f"{field} empty -> NULL"] += 1
                elif field == "word" and (c[field], s[field]) == ("#NAME?", "#name?"):
                    differences["word #NAME? -> #name?"] += 1
                else:
                    unexpected.append((row, field, c[field], s[field]))
        self.assert_differences(differences, unexpected, {
            "wordtype empty -> NULL": 3_895,
            "definition empty -> NULL": 2,
            "word #NAME? -> #name?": 224,
        })

    def test_mysql_matches_csv(self):
        self.assertEqual(len(self.mysql), len(self.csv))
        differences, unexpected = Counter(), []
        for row, (m, c) in enumerate(zip(self.mysql, self.csv), start=1):
            if c["word"] == m["word"].lower():
                differences["word matches"] += 1
            elif c["word"] == "#NAME?":
                differences["word #NAME? in CSV"] += 1
            else:
                unexpected.append((row, "word", m["word"], c["word"]))
            if c["wordtype"] == m["wordtype"]:
                differences["wordtype matches"] += 1
            else:
                unexpected.append((row, "wordtype", m["wordtype"], c["wordtype"]))
            if c["definition"] == m["definition"]:
                differences["definition matches"] += 1
            elif c["definition"] == m["definition"].encode("latin-1").decode("utf-8"):
                # The dump has "80Â¡" where the CSV has "80¡".
                differences["definition encoding"] += 1
            else:
                unexpected.append((row, "definition", m["definition"], c["definition"]))
        self.assert_differences(differences, unexpected, {
            "word matches": 175_799,
            "word #NAME? in CSV": 224,
            "wordtype matches": 176_023,
            "definition matches": 175_951,
            "definition encoding": 72,
        })

    def test_v1_matches_v2(self):
        self.assertEqual(
            {broken: sum(r["definition"].count(broken) for r in self.mysql)
             for broken in MOJIBAKE},
            {broken: count for broken, (_, count) in MOJIBAKE.items()},
        )
        self.assertEqual(len(self.mysql), 176_023)
        v2 = {r["id"]: r for r in self.parquet if r["source"] == "webster1913"}
        cleaned, differences, unexpected = {}, Counter(), []
        duplicates, empty = [], {}
        for row, m in enumerate(self.mysql, start=1):
            expected = {
                "word": squash(m["word"]).lower(),
                "wordtype": squash(m["wordtype"]) or None,
                "definition": squash(repair(m["definition"], row)),
            }
            v2_row = v2.pop(f"webster1913-{row:06d}", None)
            if v2_row is None:
                if not expected["definition"]:
                    empty[row] = m["word"]
                elif tuple(expected.values()) in cleaned:
                    duplicates.append(row)
                else:
                    unexpected.append((row, "missing from v2", m))
                continue
            cleaned[tuple(expected.values())] = row
            actual = {field: v2_row[field] for field in FIELDS}
            if actual != expected:
                unexpected.append((row, expected, actual))
                continue
            if m["word"] != m["word"].lower():
                differences["word lowercased"] += 1
            if m["word"] != squash(m["word"]):
                differences["word whitespace collapsed"] += 1
            if m["wordtype"] and m["wordtype"] != squash(m["wordtype"]):
                differences["wordtype whitespace collapsed"] += 1
            if not m["wordtype"]:
                differences["wordtype empty -> null"] += 1
            if m["definition"] != squash(m["definition"]):
                differences["definition whitespace collapsed"] += 1
            if m["definition"] != repair(m["definition"], row):
                differences["definition encoding repaired"] += 1
        self.assertEqual(v2, {}, "v2 Webster rows with no v1 row")
        self.assertEqual(empty, EMPTY_DEFINITION_ROWS)
        self.assertEqual(duplicates, list(DUPLICATE_ROWS))
        self.assertEqual(len(cleaned) + len(duplicates) + len(empty), 176_023)
        self.assert_differences(differences, unexpected, V1_V2_DIFFERENCES)

    def test_sample_trace(self):
        v2_files = {"parquet": self.parquet, "jsonl": self.jsonl}
        v1_files = {"csv": self.csv, "sqlite": self.sqlite, "mysql": self.mysql}

        # Row 362: a spreadsheet turned `-able` into a formula error.
        expected = {"csv": "#NAME?", "sqlite": "#name?", "mysql": "-able"}
        for name, rows in v1_files.items():
            with self.subTest(sample="row 362", file=name):
                self.assertEqual(rows[361]["word"], expected[name])
        for name, rows in v2_files.items():
            with self.subTest(sample="row 362", file=name):
                row = next(r for r in rows if r["id"] == "webster1913-000362")
                self.assertEqual(row["word"], "-able")

        # Row 10213: `at`, with the thermometer at 80 degrees.
        expected = {"csv": "at 80¡;", "sqlite": "at 80¡;", "mysql": "at 80Â¡;"}
        for name, rows in v1_files.items():
            with self.subTest(sample="at", file=name):
                self.assertEqual(rows[10212]["word"].lower(), "at")
                self.assertIn(f"thermometer {expected[name]}", rows[10212]["definition"])
        for name, rows in v2_files.items():
            with self.subTest(sample="at", file=name):
                row = next(r for r in rows if r["id"] == "webster1913-010213")
                self.assertEqual(row["word"], "at")
                self.assertIn("thermometer at 80°;", row["definition"])

        # `computer`: one Webster's row in every file, plus 2 WordNet rows in v2.
        for name, rows in v1_files.items():
            with self.subTest(sample="computer", file=name):
                computer = [r for r in rows if r["word"].lower() == "computer"]
                self.assertEqual(
                    [(r["word"], r["definition"]) for r in computer],
                    [("Computer" if name == "mysql" else "computer", "One who computes.")],
                )
        for name, rows in v2_files.items():
            with self.subTest(sample="computer", file=name):
                computer = [r for r in rows if r["word"] == SAMPLE_WORD]
                self.assertEqual(
                    [r["definition"] for r in computer if r["source"] == "webster1913"],
                    ["One who computes."],
                )
                self.assertEqual(Counter(r["source"] for r in computer)["oewn"], 2)


if __name__ == "__main__":
    unittest.main()
