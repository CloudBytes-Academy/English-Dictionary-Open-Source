"""Independent expected values and the dump parser, shared by the format tests."""

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

V1_HASHES = {
    "csv/dictionary.csv": "78e25547dd4ee14e128d6b171296c60563d21a9a32f6a579c8d91c0bf08088da",
    "sqlite3/dictionary.db": "225a2be8297b3b552a70d06d13dd27a5e850949de82a91dc16a913dc4fe67b4c",
    "mysql/dictionaryStudyTool.sql": "f0b545b56fca51c9819e9104628b98f4bdeedb54264b15102e743c47d997b549",
}

# CSV and SQLite preserve the trailing space; v2 removes it. The dump also
# preserves case. Keep these differences explicit rather than normalizing them.
MALFORMED_V1 = {
    ", a , or an . pcp. it is ": 2,
    r"\d8gregarin\91": 1,
    r"\d8gregarinida": 1,
    'ey"ries': 1,
}
MALFORMED_MYSQL = {
    ", a , or an . PCP. It is ": 2,
    r"\d8Gregarin\91": 1,
    r"\d8Gregarinida": 1,
    'Ey"ries': 1,
}
MALFORMED_V2 = {
    ", a , or an . pcp. it is": 2,
    r"\d8gregarin\91": 1,
    r"\d8gregarinida": 1,
    'ey"ries': 1,
}

# Exact values and frequencies, including trailing spaces, from the dump.
TRUNCATED_WORDTYPES = {
    "imp., p. p., or auxi": 4,
    "imp. & p. p. Adored ": 1,
    "L. catechunenus, Gr.": 1,
    "imp. & p. p. & vb. n": 1,
    "imp. & p. pr. & vb. ": 1,
    "adv., prep., & conj.": 2,
    "adv. In combination ": 1,
    "2d pers. sing. pres.": 1,
    "adv. In a vanishing ": 1,
    "prep. & conj., but p": 1,
    "prep., adv., conj. &": 2,
    "imp. & p. p. Fenced ": 1,
    "pres. indic. sing., ": 1,
    "p. pr. & pr. & vb. n": 1,
    "3d pers. sing. pres.": 6,
    "prep., adv., & conj.": 1,
    "Compar. & superl. wa": 3,
    "subj. 3d pers. sing.": 1,
    "v. impersonal, pres.": 1,
    "interj., adv., or a.": 1,
    "pron., a., conj., & ": 10,
    "Archaic imp. & p. p.": 1,
}

# Parse the dump independently of the v2 builder. Restrict parsing to INSERTs
# and require every character of each payload to be consumed.
TUPLE = re.compile(r"\('((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)'\)")
ESCAPES = {"0": "\0", "b": "\b", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a"}


def parse_mysql_rows(sql):
    rows = []
    inserts = re.findall(r"^INSERT INTO `entries` VALUES (.*);$", sql, re.M)
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
            rows.append(dict(zip(("word", "wordtype", "definition"), fields)))
            offset = match.end()
            if offset < len(payload):
                if payload[offset] != "," or offset + 1 == len(payload):
                    raise AssertionError(f"Invalid tuple separator at offset {offset}")
                offset += 1
    return rows


def assert_malformed_headwords(test, rows, expected):
    # These are the punctuation classes of the four known malformed headwords.
    # Compare the complete set, so another headword in these classes fails.
    actual = Counter(
        row["word"] for row in rows if any(c in row["word"] for c in ',"\\')
    )
    test.assertEqual(actual, expected)


def assert_v1_samples(test, rows, *, mysql=False, sqlite=False):
    test.assertEqual(
        rows[56],
        {"word": "Abandoned" if mysql else "abandoned",
         "wordtype": "imp. & p. p.", "definition": "of Abandon"},
    )
    able_word = "-able" if mysql else "#name?" if sqlite else "#NAME?"
    test.assertEqual(rows[361]["word"], able_word)
    test.assertEqual(rows[361]["wordtype"], None if sqlite else "")
    computer = [r for r in rows if r["word"].lower() == "computer"]
    test.assertEqual(
        computer,
        [{"word": "Computer" if mysql else "computer",
          "wordtype": "n.", "definition": "One who computes."}],
    )
    hobble = [r for r in rows if r["word"].lower() == "hobble"]
    test.assertEqual(len(hobble), 7)
    test.assertEqual([r["wordtype"] for r in hobble[:2]], ["n. i.", "n. i."])
    test.assertFalse({"email", "smartphone"} & {r["word"].lower() for r in rows})


def assert_v2_samples(test, rows):
    by_id = {r["id"]: r for r in rows}
    abandoned = by_id["webster1913-000057"]
    test.assertEqual(
        tuple(abandoned[key] for key in ("word", "wordtype", "definition", "pos")),
        ("abandoned", "imp. & p. p.", "of Abandon", "verb"),
    )
    test.assertEqual(by_id["webster1913-000362"]["word"], "-able")
    computer = [r for r in rows if r["word"] == "computer"]
    test.assertEqual(
        Counter(r["source"] for r in computer), {"webster1913": 1, "oewn": 2},
    )
    webster = next(r for r in computer if r["source"] == "webster1913")
    test.assertEqual(
        (webster["wordtype"], webster["definition"]), ("n.", "One who computes."),
    )
    test.assertIn(
        "a machine for performing calculations automatically",
        [r["definition"] for r in computer if r["source"] == "oewn"],
    )
    hobble = [r for r in rows if r["word"] == "hobble" and r["source"] == "webster1913"]
    test.assertEqual(len(hobble), 7)
    for row_id in ("webster1913-073083", "webster1913-073084"):
        test.assertEqual(
            (by_id[row_id]["word"], by_id[row_id]["wordtype"], by_id[row_id]["pos"]),
            ("hobble", "n. i.", "verb"),
        )
    email = [r for r in rows if r["word"] == "email"]
    test.assertEqual(Counter(r["pos"] for r in email), {"noun": 3, "verb": 1})
    test.assertEqual({r["source"] for r in email}, {"oewn"})
    smartphone = [r for r in rows if r["word"] == "smartphone"]
    test.assertEqual(len(smartphone), 1)
    test.assertEqual(smartphone[0]["source"], "oewn")
