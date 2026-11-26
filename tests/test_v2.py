"""Checks on the built v2 files.

Run after building:
    uv run --with-requirements tests/requirements.txt python -m unittest discover tests
"""

import gzip
import hashlib
import json
import re
import unittest
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from data_contract import MALFORMED_V2, assert_malformed_headwords, assert_v2_samples

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "v2"
POS = {
    "noun", "verb", "adjective", "adverb", "preposition", "conjunction",
    "pronoun", "interjection", "prefix", "suffix", "article", None,
}


class V2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = pq.read_table(V2 / "dictionary.parquet").to_pylist()
        cls.webster = [r for r in cls.rows if r["source"] == "webster1913"]
        cls.words = {r["word"] for r in cls.rows}

    def test_jsonl_matches_parquet(self):
        with gzip.open(V2 / "dictionary.jsonl.gz", "rt", encoding="utf-8") as f:
            jsonl = [json.loads(line) for line in f]
        self.assertEqual(jsonl, self.rows)

    def test_checksums(self):
        for line in (V2 / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ")
            self.assertEqual(hashlib.sha256((V2 / name).read_bytes()).hexdigest(), digest, name)

    def test_row_counts(self):
        counts = Counter(r["source"] for r in self.rows)
        # 176,023 dump rows - 2 empty definitions - 93 exact duplicates.
        self.assertEqual(counts, {"webster1913": 175_928, "oewn": 212_659})

    def test_parquet_schema(self):
        expected = pa.schema([
            pa.field("id", pa.string(), nullable=False),
            pa.field("word", pa.string(), nullable=False),
            pa.field("pos", pa.string()),
            pa.field("wordtype", pa.string()),
            pa.field("definition", pa.string(), nullable=False),
            pa.field("examples", pa.list_(pa.string()), nullable=False),
            pa.field("synset_id", pa.string()),
            pa.field("source", pa.string(), nullable=False),
        ])
        self.assertEqual(pq.read_schema(V2 / "dictionary.parquet").remove_metadata(), expected)

    def test_samples(self):
        assert_v2_samples(self, self.rows)

    def test_known_defects(self):
        assert_malformed_headwords(self, self.webster, MALFORMED_V2)

    def test_parquet_written_by_pinned_pyarrow(self):
        # Other pyarrow versions write different bytes, which breaks the
        # byte-identical rebuild that the README promises.
        script = (ROOT / "scripts" / "build_v2.py").read_text(encoding="utf-8")
        pinned = re.search(r'"pyarrow==([\d.]+)"', script).group(1)
        created_by = pq.ParquetFile(V2 / "dictionary.parquet").metadata.created_by
        self.assertEqual(created_by, f"parquet-cpp-arrow version {pinned}")

    def test_parquet_carries_data_license(self):
        metadata = pq.read_schema(V2 / "dictionary.parquet").metadata
        license_text = metadata[b"license"].decode("utf-8")
        self.assertEqual(license_text, (V2 / "LICENSE-DATA.md").read_text(encoding="utf-8"))
        self.assertIn("https://creativecommons.org/licenses/by/4.0/", license_text)
        self.assertIn("WordNet 3.1 Copyright 2011 by Princeton University", license_text)
        self.assertIn("The origin of the content should also be acknowledged", license_text)

    def test_ids_unique(self):
        self.assertEqual(len({r["id"] for r in self.rows}), len(self.rows))

    def test_sorted_by_word_then_source(self):
        keys = [(r["word"].casefold(), r["source"] != "webster1913") for r in self.rows]
        self.assertEqual(keys, sorted(keys))

    def test_definitions_are_single_clean_lines(self):
        for r in self.rows:
            for text in [r["word"], r["definition"], *r["examples"]]:
                self.assertTrue(text, r["id"])
                self.assertEqual(text, " ".join(text.split()), r["id"])

    def test_spreadsheet_corruption_is_gone(self):
        self.assertNotIn("#name?", {w.casefold() for w in self.words})
        self.assertTrue({"-able", "-ance", "-ate"} <= self.words)

    def test_mojibake_is_gone(self):
        for r in self.rows:
            for text in [r["word"], r["definition"], *r["examples"]]:
                self.assertFalse(set(text) & {"Â", "Ã", "\x83", "\x96"}, r["id"])
        at = [r["definition"] for r in self.webster if r["word"] == "at"]
        self.assertTrue(any("at 80°;" in d for d in at))

    def test_pos_vocabulary(self):
        self.assertLessEqual({r["pos"] for r in self.rows}, POS)
        hobble = {r["pos"] for r in self.webster if r["word"] == "hobble"}
        self.assertEqual(hobble, {"verb", "noun"})

    def test_pos_from_definition_labels(self):
        # 562 rows get pos from the grammar label at the start of the
        # definition, such as "imp. of Bind.". 559 of them have no word type,
        # counted here. The other 3 have a word type that is not a part of
        # speech, such as "writ", whose word type is "obs.".
        no_type = [r for r in self.webster if r["wordtype"] is None]
        self.assertEqual(Counter(r["pos"] for r in no_type if r["pos"]), {
            "verb": 439, "adjective": 113, "noun": 7,
        })
        by_id = {r["id"]: r for r in self.webster}
        samples = {
            "webster1913-018287": ("bore", "verb"),  # imp. of 1st & 2d Bear.
            "webster1913-173987": ("witen", "verb"),  # pl. pres. of Wit.
            "webster1913-163871": ("turves", "noun"),  # pl. of Turf.
            "webster1913-141686": ("simpering", "adjective"),  # a. &. n. from Simper, v.
            "webster1913-139648": ("shalt", "verb"),  # 2d per. sing. of Shall.
            "webster1913-174930": ("wrote", "verb"),  # imp. & archaic p. p. of Write.
            "webster1913-149934": ("stont", None),  # 3d pers. sing. present of Stand.
            "webster1913-094770": ("medievalism", None),  # Alt. of Medievalist
            "webster1913-016509": ("black letter", None),  # no label
        }
        for row_id, expected in samples.items():
            with self.subTest(row_id=row_id):
                self.assertEqual((by_id[row_id]["word"], by_id[row_id]["pos"]), expected)
        self.assertEqual(sum(r["pos"] is None for r in self.webster), 3_357)

    def test_no_duplicate_webster_rows(self):
        keys = Counter((r["word"], r["wordtype"], r["definition"]) for r in self.webster)
        self.assertEqual(keys.most_common(1)[0][1], 1)

    def test_source_fields(self):
        for r in self.rows:
            if r["source"] == "webster1913":
                self.assertEqual((r["examples"], r["synset_id"]), ([], None), r["id"])
                self.assertEqual(r["word"], r["word"].lower(), r["id"])
            else:
                self.assertEqual(r["source"], "oewn")
                self.assertIsNone(r["wordtype"], r["id"])
                self.assertIsNotNone(r["synset_id"], r["id"])

    def test_slashed_headwords(self):
        # 43 rows got their spelling back from the Gutenberg text. These 17
        # headwords keep their "/", because the Gutenberg text does not confirm a spelling.
        slashed = sorted({r["word"] for r in self.webster if "/" in r["word"]})
        self.assertEqual(slashed, [
            "ballist/", "basilic/", "di/////", "di/planted", "dou/ted", "emyd//",
            "eying / eyeing", "glabell/", "gloss/", "gonothec/",
            "nuch/", "nudge/", "nymph/", "prepare/", "pseudofilari/", "pup/", "review/d",
        ])
        restored = {r["id"]: r["word"] for r in self.webster}
        self.assertEqual(
            [restored[f"webster1913-{n:06d}"] for n in (9661, 35948, 66471, 95027, 121954)],
            ["assafoetida", "creche", "globigerin\u00e6", "meliboean", "provencal"],
        )

    def test_modern_words_present(self):
        oewn = {r["word"] for r in self.rows if r["source"] == "oewn"}
        self.assertTrue({"smartphone", "email", "blog", "internet"} <= oewn)


if __name__ == "__main__":
    unittest.main()
