"""Check every count the README gives about the data against the data files.

Each figure is found by the sentence it sits in, so changing a number in the
README, or changing the data, fails a test. A rewritten sentence fails too,
until its pattern here is updated.
"""

import csv
import importlib.util
import re
import sqlite3
import unittest

import pyarrow.parquet as pq

from data_contract import ROOT, parse_mysql_rows

spec = importlib.util.spec_from_file_location("build_v2", ROOT / "scripts" / "build_v2.py")
build_v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_v2)


def number(text):
    return int(text.replace(",", ""))


class ReadmeFiguresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        rows = pq.read_table(ROOT / "v2/dictionary.parquet").to_pylist()
        webster = [r for r in rows if r["source"] == "webster1913"]
        oewn = [r for r in rows if r["source"] == "oewn"]
        dump = parse_mysql_rows((ROOT / "mysql/dictionaryStudyTool.sql").read_text(encoding="latin-1"))
        with (ROOT / "csv/dictionary.csv").open(encoding="utf-8", newline="") as file:
            v1 = list(csv.DictReader(file))

        webster_words = {r["word"].casefold() for r in webster}
        only_oewn = {r["word"].casefold() for r in oewn} - webster_words
        word_types = {r["wordtype"] for r in webster if r["wordtype"]}
        no_pos = [r for r in webster if r["pos"] is None]
        by_id = {r["id"]: r for r in webster}
        # Dump rows whose headword had "/" and whose v2 row does not.
        restored = [
            row["word"].lower() for number_, row in enumerate(dump, 1)
            if "/" in row["word"]
            and "/" not in by_id.get(f"webster1913-{number_:06d}", {"word": "/"})["word"]
        ]
        # Rows whose whole definition is "of" and a name, but have no base_word.
        unlinked = []
        for r in webster:
            match = re.fullmatch(r"of (\S.*?)\.?", r["definition"])
            if match and r["base_word"] is None:
                unlinked.append((r["word"], match.group(1).lower()))
        empty = sum(not row["definition"].strip() for row in dump)
        connection = sqlite3.connect((ROOT / "sqlite3/dictionary.db").as_uri() + "?mode=ro", uri=True)
        null_wordtype, null_definition = connection.execute(
            "SELECT sum(wordtype IS NULL), sum(definition IS NULL) FROM entries"
        ).fetchone()
        connection.close()
        # v2 rows whose v1 CSV word was "#NAME?".
        name_rows = [
            by_id[f"webster1913-{number_:06d}"]["word"] for number_, row in enumerate(v1, 1)
            if row["word"] == "#NAME?" and f"webster1913-{number_:06d}" in by_id
        ]

        cls.actual = {
            "v2 definitions": len(rows),
            "v2 words": len(webster_words | {r["word"].casefold() for r in oewn}),
            "v1 definitions": len(v1),
            # The dump, because the CSV and SQLite files show 145 words as "#NAME?".
            "v1 words": len({row["word"].lower() for row in dump}),
            "v1 words shown as #NAME?": len({
                dump[number_ - 1]["word"].lower() for number_, row in enumerate(v1, 1)
                if row["word"] == "#NAME?"
            }),
            "Webster's rows": len(webster),
            "WordNet rows": len(oewn),
            "words only in WordNet": len(only_oewn),
            "single words only in WordNet": sum(" " not in w for w in only_oewn),
            "phrases only in WordNet": sum(" " in w for w in only_oewn),
            "#NAME? words restored": len(set(name_rows)),
            "#NAME? rows restored": len(name_rows),
            "headwords repaired": len(set(restored)),
            "rows with repaired headwords": len(restored),
            "duplicate rows removed": len(dump) - empty - len(webster),
            "v1 SQLite NULL word types": null_wordtype,
            "v1 SQLite NULL definitions": null_definition,
            "empty definitions removed": empty,
            "word types mapped": sum(build_v2.webster_pos(w) is not None for w in word_types),
            "word types": len(word_types),
            "pos values": len({r["pos"] for r in webster if r["pos"]}),
            "pos from definitions": sum(
                r["pos"] is not None and build_v2.webster_pos(r["wordtype"] or "") is None
                for r in webster
            ),
            "base_word links": sum(r["base_word"] is not None for r in webster),
            "headwords with /": len({r["word"] for r in webster if "/" in r["word"]}),
            "rows with no pos": len(no_pos),
            "no pos, no word type": sum(r["wordtype"] is None for r in no_pos),
            "no pos, other word type": sum(r["wordtype"] is not None for r in no_pos),
            "unlinked word forms": len(unlinked),
            "unlinked, name themselves": sum(word == name for word, name in unlinked),
            "unlinked, broken headword": sum(
                word.startswith("-") and word != name for word, name in unlinked
            ),
        }
        cls.actual["unlinked, not a headword"] = (
            cls.actual["unlinked word forms"]
            - cls.actual["unlinked, name themselves"]
            - cls.actual["unlinked, broken headword"]
        )

    # Each figure: the README text around it, with the number as a group.
    FIGURES = {
        "v2 definitions": r"\*\*v2\*\* \(2026\): ([\d,]+) definitions of",
        "v2 words": r"\*\*v2\*\* \(2026\): [\d,]+ definitions of ([\d,]+) words",
        "v1 definitions": r"\*\*v1\*\* \(2021\): ([\d,]+) definitions of",
        "v1 words": r"\*\*v1\*\* \(2021\): [\d,]+ definitions of ([\d,]+) words",
        "v1 words shown as #NAME?": r"still show ([\d,]+) of those words as `#NAME\?`",
        "Webster's rows": r"\| Webster's 1913 \| ([\d,]+) \|",
        "WordNet rows": r"\| Open English WordNet 2025\+ \| ([\d,]+) \|",
        "words only in WordNet": r"Adds ([\d,]+) words that Webster's does not have",
        "single words only in WordNet": r"does not have: ([\d,]+) single words",
        "phrases only in WordNet": r"and ([\d,]+) phrases, such as `domestic dog`",
        "#NAME? words restored": r"Restores ([\d,]+) words, in [\d,]+ rows, such as `-able`",
        "#NAME? rows restored": r"Restores [\d,]+ words, in ([\d,]+) rows, such as `-able`",
        "headwords repaired": r"Repairs ([\d,]+) headwords, in [\d,]+ rows",
        "rows with repaired headwords": r"Repairs [\d,]+ headwords, in ([\d,]+) rows",
        "duplicate rows removed": r"Removes ([\d,]+) duplicate rows",
        "empty definitions removed": r"duplicate rows and ([\d,]+) empty definitions",
        "v1 SQLite NULL word types": r"The SQLite file contains ([\d,]+) rows\s+with a NULL `wordtype`",
        "v1 SQLite NULL definitions": r"with a NULL `wordtype` and ([\d,]+) with a NULL `definition`",
        "word types mapped": r"Maps ([\d,]+) of the [\d,]+ word-type spellings",
        "word types": r"Maps [\d,]+ of the ([\d,]+) word-type spellings",
        "pos values": r"to the ([\d,]+) values in `pos`",
        "pos from definitions": r"Fills in `pos` for ([\d,]+) rows",
        "base_word links": r"Links ([\d,]+) word forms to their base word",
        "headwords with /": r"- ([\d,]+) Webster's headwords, and some definitions, still contain `/`",
        "rows with no pos": r"- ([\d,]+) Webster's rows have no `pos`",
        "no pos, no word type": r"have no `pos`: ([\d,]+) have no word type",
        "no pos, other word type": r"have no word type, and ([\d,]+) have one that is not a part of speech",
        "unlinked word forms": r"- ([\d,]+) Webster's word forms whose whole definition is `of`",
        "unlinked, name themselves": r"have no `base_word`: ([\d,]+) name themselves",
        "unlinked, broken headword": r"([\d,]+) have a broken headword such as `-ances`",
        "unlinked, not a headword": r"and ([\d,]+) name something that is not a single headword",
    }

    def test_every_figure_matches_the_data(self):
        for name, pattern in self.FIGURES.items():
            with self.subTest(figure=name):
                matches = re.findall(pattern, self.readme)
                self.assertEqual(len(matches), 1, f"{name}: the README sentence was not found once")
                self.assertEqual(number(matches[0]), self.actual[name], name)

    def test_every_figure_is_checked(self):
        self.assertEqual(set(self.FIGURES), set(self.actual))


if __name__ == "__main__":
    unittest.main()
