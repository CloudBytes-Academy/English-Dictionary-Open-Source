"""Test the v2 build's helper functions on real examples from the dictionary.

The other tests check only the finished files. These point at the rule that
broke. They import scripts/build_v2.py and need no network.
"""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "build_v2", Path(__file__).resolve().parent.parent / "scripts" / "build_v2.py",
)
build_v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_v2)


class PartOfSpeechTest(unittest.TestCase):
    def assert_pos(self, cases):
        for wordtype, pos in cases.items():
            with self.subTest(wordtype=wordtype):
                self.assertEqual(build_v2.webster_pos(wordtype), pos)

    def test_common_word_types(self):
        self.assert_pos({
            "n.": "noun", "pl.": "noun", "n. pl.": "noun",
            "v. t.": "verb", "v. i.": "verb", "imp. & p. p.": "verb",
            "p. pr. & vb. n.": "verb", "3d pers. sing. pres.": "verb",
            "a.": "adjective", "p. a.": "adjective", "superl.": "adjective",
            "compar.": "adjective", "adv.": "adverb", "prep.": "preposition",
            "conj.": "conjunction", "pron.": "pronoun", "interj.": "interjection",
            "pref.": "prefix", "suffix.": "suffix", "definite article.": "article",
        })

    def test_typos_in_the_source(self):
        # Spellings as they appear in the dump: "n ." "supperl." "inerj." "b. t."
        self.assert_pos({
            "n .": "noun", "supperl.": "adjective", "inerj.": "interjection",
            "ad.": "adverb", "b. t.": "verb",
        })

    def test_first_part_of_speech_named_wins(self):
        self.assert_pos({"a. & n.": "adjective", "adv. & a.": "adverb"})

    # In the dump, only these three word types match more than one rule, so
    # these are the tests that fail if the rules are reordered.
    def test_n_i_and_n_t_are_verb_typos(self):
        # "Hobble, n. i., To walk lame": a typo for "v. i.", not a noun.
        self.assert_pos({"n. i.": "verb", "n. t.": "verb"})

    def test_p_pl_is_a_plural_noun(self):
        self.assert_pos({"p. pl.": "noun"})

    def test_not_a_part_of_speech(self):
        self.assert_pos({"": None, "obs.": None, "See": None})


class EncodingRepairTest(unittest.TestCase):
    def assert_repaired(self, cases):
        for broken, fixed in cases.items():
            with self.subTest(text=broken):
                self.assertEqual(build_v2.fix_encoding(broken), fixed)

    def test_garbled_characters(self):
        # Counts in the dump: ° 67 times, £ 6, ÷ 2, and the √ byte 11.
        self.assert_repaired({
            "at 80Â¡;": "at 80°;", "Â£150": "£150",
            "the sign of division Ã\x96,": "the sign of division ÷,", "Ã\x832": "√2",
        })

    def test_section_sign(self):
        # The √ byte also stood for § before a section number: "§155".
        self.assert_repaired({"Ã\x83155": "§155", "Ã\x83 155": "§ 155"})

    def test_plain_text_is_unchanged(self):
        self.assert_repaired({"One who computes.": "One who computes."})


class DumpTextTest(unittest.TestCase):
    def test_unescape_sql(self):
        cases = {
            r"it\'s": "it's", r"a\nb": "a\nb", r"tab\there": "tab\there",
            r"back\\slash": "back\\slash", r"\0": "\0",
        }
        for escaped, text in cases.items():
            with self.subTest(text=escaped):
                self.assertEqual(build_v2.unescape_sql(escaped), text)

    def test_row_pattern_reads_quoted_values(self):
        # Two rows as they appear in mysql/dictionaryStudyTool.sql.
        sql = (
            "INSERT INTO `entries` VALUES ('Abandon','v. t.','To cast or drive out; "
            r"to banish; to expel; to reject.'),('L\'envoi','n.','Alt. of L\'envoy');"
        )
        self.assertEqual(build_v2.ROW_RE.findall(sql), [
            ("Abandon", "v. t.", "To cast or drive out; to banish; to expel; to reject."),
            (r"L\'envoi", "n.", r"Alt. of L\'envoy"),
        ])

    def test_squash_collapses_whitespace(self):
        # The first CSV row's definition has a hard line break and indent.
        self.assertEqual(
            build_v2.squash("The first letter of the English and of many other alphabets. The\n   capital A"),
            "The first letter of the English and of many other alphabets. The capital A",
        )


class WordNetTest(unittest.TestCase):
    def test_part_of_speech_codes(self):
        # "s" is WordNet's code for a satellite adjective.
        self.assertEqual(build_v2.OEWN_POS, {
            "n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb",
        })


if __name__ == "__main__":
    unittest.main()
