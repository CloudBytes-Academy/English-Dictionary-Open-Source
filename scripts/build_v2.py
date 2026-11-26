# /// script
# requires-python = ">=3.10,<3.15"  # pyarrow 25.0.1 has wheels for 3.10-3.14 only
# dependencies = ["pyarrow==25.0.1"]  # pinned: other versions write different Parquet bytes
# ///
"""Build the v2 dictionary (JSONL + Parquet) from two sources.

1. Webster's 1913 Unabridged, read from the original MySQL dump in mysql/
   (public domain).
2. Open English WordNet 2025+ (CC BY 4.0), downloaded once into .cache/ and
   verified against a pinned SHA-256.

Usage:
    uv run scripts/build_v2.py

Writes v2/dictionary.jsonl.gz, v2/dictionary.parquet and v2/SHA256SUMS.
With the pinned pyarrow, the same inputs give a byte-identical Parquet file
and the same JSONL rows. The gzip bytes come from the interpreter's zlib, so
they can differ: Python 3.14+ on Windows links zlib-ng, which writes a
different dictionary.jsonl.gz.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
WEBSTER_DUMP = ROOT / "mysql" / "dictionaryStudyTool.sql"
CACHE = ROOT / ".cache"
OUT = ROOT / "v2"

OEWN_URL = (
    "https://github.com/globalwordnet/english-wordnet/releases/download/"
    "2025-edition/english-wordnet-2025-plus.xml.gz"
)
OEWN_SHA256 = "31f4af16c54b532fd5484d4cc33aee588a31bb5b70683ae8197842fde5b586bc"

SOURCE_RANK = {"webster1913": 0, "oewn": 1}

SCHEMA = pa.schema(
    [
        pa.field("id", pa.string(), nullable=False),
        pa.field("word", pa.string(), nullable=False),
        pa.field("pos", pa.string()),
        pa.field("wordtype", pa.string()),
        pa.field("definition", pa.string(), nullable=False),
        pa.field("examples", pa.list_(pa.string()), nullable=False),
        pa.field("synset_id", pa.string()),
        pa.field("source", pa.string(), nullable=False),
    ]
)

# --- Webster 1913 -----------------------------------------------------------

ROW_RE = re.compile(
    r"\('((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)'\)", re.S
)
ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0"}

# Webster's raw word types are abbreviations with many typos ("supperl.",
# "n .", "b. t."). Match the first part of speech named, after removing
# spaces and lowercasing. Order matters: "adv" before "a.", "p.a" before "p.p".
POS_RULES = [
    (r"definitearticle|def\.art", "article"),
    (r"aprefix|prefix|pref\.", "prefix"),
    (r"suffix", "suffix"),
    (r"adv|ads\.|ad\.$|dv\.|interrog\.adv", "adverb"),
    (r"adj|a\.|a/|a&|a$|fem\.a\.", "adjective"),
    (r"superl|supperl|super\.|compar|comp\.", "adjective"),
    (r"p\.a\.|p\.a$|p\.&a\.", "adjective"),
    (r"n\.[it]\.$", "verb"),  # typos for "v. i." / "v. t.": "Hobble, n. i., To walk lame"
    (r"n\.|n$|n&|n/|npl|n,|pl\.|p\.pl\.|sing\.(&|/|or)|sing\.$|syntacticallysing", "noun"),
    (r"prep", "preposition"),
    (r"conj", "conjunction"),
    (r"pron|indef\.pron|possessivepron|pers\.pron|obj|object|dat\.&obj", "pronoun"),
    (r"interj|inerj", "interjection"),
    (
        r"v\.|v$|v/|v&|vb|imp|p\.p|pp|p\.?pr|pr\.p|p\]|p,pr|pres|inf|3d|2d"
        r"|imperative|participle|strong|obs\.?(strong)?(imp|p\.p)|archaicimp"
        r"|b\.t|e\.t|e\.i|sing\.pres|subj|indic",
        "verb",
    ),
]
POS_RULES = [(re.compile(p), pos) for p, pos in POS_RULES]

# Headwords where a letter was lost before the data reached OPTED, so the
# dump has "/" in its place. Each correction is the spelling in the Project
# Gutenberg text of the 1913 Webster's (ebook 29765), found by matching the
# row's definition to its Gutenberg entry. Gutenberg prints ligatures as two
# letters and drops accents ("ASSAFOETIDA", "CRECHE"), so these do too.
# Where an entry gives two spellings, the dump's other rows decide which one
# the slash stands for: "melibean" is a separate row, "Alt. of Melib/an", so
# "melib/an" is "meliboean". Some slashes stood for no letter at all, only a
# stress mark, as in "cor/niculate". The other headwords with "/" stay as they
# are, because the Gutenberg text does not confirm a spelling, as in "pl. Ballist.".
HEADWORD_FIXES = {
    "adder fly/": "adder fly",
    "alen/on lace": "alencon lace",
    "assaf/tida": "assafoetida",
    "cor/niculate": "corniculate",
    "cr/che": "creche",
    "dendroc/la": "dendrocoela",
    "feather-brained/": "feather-brained",
    "feather-edge/": "feather-edge",
    "feather-edged/": "feather-edged",
    "feather-few/": "feather-few",
    "fedaliza/tion": "feudalization",  # Gutenberg "Feu*dal*i*za/tion": the dump also lost the "u"
    "gairish/ness": "gairishness",
    "globigerin/": "globigerin\u00e6",  # Gutenberg: "pl. Globigerinae" with the ae ligature
    "lav/sium": "lavoesium",
    "lima/on": "limacon",
    "m/tin": "matin",
    "melib/an": "meliboean",
    "melop/ia": "melopoeia",
    "mesam/boid": "mesamoeboid",
    "mesogl/a": "mesogloea",
    "mesophl/um": "mesophloeum",
    "orthopn/a": "orthopnoea",
    "otorrh/a": "otorrhoea",
    "pound/keeper": "poundkeeper",
    "precogita/tion": "precogitation",
    "prosopop/ia": "prosopopoeia",
    "proven/al": "provencal",
    "rh/tian": "rhaetian",
    "rh/tic": "rhaetic",
    "rh/tizite": "rhaetizite",
    "shortened /": "shortened",
    "tox/mia": "toxaemia",
    "tracer/y": "tracery",
    "tri/cia": "trioecia",
    "tri/cious": "trioecious",
    "vouch/or": "vouchor",
    "zu/is": "zunis",
}


# Some rows have no word type, and Webster's put the grammar label at the
# start of the definition instead: "imp. of Bind.", "a. & n. from Flow, v. i.".
# For rows with no part of speech, read that label with the same rules as
# word types. A label is grammar abbreviations followed by "of", "from" or
# "fr.", so a definition such as "A plant of the genus ..." is not one. It may
# include the words Webster's uses to describe the form, such as "old imp."
# or "imp. & archaic p. p.", which are dropped before the rules read it, and
# brackets or slashes, as in "imp. (/ rare p. p.) of Smite.". Labels in plain
# words, such as "the preterit of Eat", are not read.
LABEL_QUALIFIER = r"(?:the|old|strong|original|archaic|rare|poet\.|obs\.)"
DEFINITION_LABEL_RE = re.compile(
    r"(?:\.\s+)?\(?"  # one row starts with a stray ". ": ". imp. & p. p. of Read."
    r"(?:(?:" + LABEL_QUALIFIER + r"|(?:imp|pret|pres|indic|p|pr|pl|sing|compar|superl|a|n|vb|pers|per)\.|(?:1st|2d|3d)\.?|&\.?|or|a(?= &))[ ,/()]*)+"
    r"(?=of\b|from\b|fr\.)",
    re.I,
)
# The rules read these labels wrongly or not at all.
LABEL_POS = {
    "pret.": "verb",
    "pl. pres.": "verb",  # "witen": "pl. pres. of Wit", a verb, not a plural noun
    "1st & 3d pers. sing. pres.": "verb",
}


def unescape_sql(s: str) -> str:
    return re.sub(r"\\(.)", lambda m: ESCAPES.get(m.group(1), m.group(1)), s)


def fix_encoding(s: str) -> str:
    """Undo double encoding: Mac Roman bytes, saved as UTF-8, read as Latin-1.

    "80Â¡" becomes "80°" and "Ã\\x832" becomes "√2".
    """
    if s.isascii():
        return s
    s = s.encode("latin-1").decode("utf-8")
    s = "".join(
        bytes([ord(c)]).decode("mac_roman") if 127 < ord(c) < 256 else c for c in s
    )
    # The same byte also stood for "§" in section references: "§155".
    return re.sub(r"√(?=\s*\d{3})", "§", s)


def squash(s: str) -> str:
    return " ".join(s.split())


def webster_pos(wordtype: str) -> str | None:
    key = re.sub(r"\s+", "", wordtype.lower())
    for pattern, pos in POS_RULES:
        if pattern.match(key):
            return pos
    return None


def definition_label_pos(definition: str) -> str | None:
    match = DEFINITION_LABEL_RE.match(definition)
    if match is None:
        return None
    label = match.group(0).lower().removeprefix(". ")
    label = re.sub(r"\b" + LABEL_QUALIFIER + r"\s*|[()/]", " ", label)
    label = " ".join(label.split()).strip(" ,")
    return LABEL_POS.get(label) or webster_pos(label)


def load_webster() -> tuple[list[dict], Counter]:
    sql = WEBSTER_DUMP.read_text(encoding="latin-1")
    stats = Counter()
    rows, seen = [], set()
    for index, match in enumerate(ROW_RE.finditer(sql), start=1):
        word, wordtype, definition = (
            squash(fix_encoding(unescape_sql(field))) for field in match.groups()
        )
        stats["webster_input"] += 1
        if not definition:
            stats["webster_dropped_empty"] += 1
            continue
        word = word.lower()
        if word in HEADWORD_FIXES:
            word = HEADWORD_FIXES[word]
            stats["webster_headword_restored"] += 1
        key = (word, wordtype, definition)
        if key in seen:
            stats["webster_dropped_duplicate"] += 1
            continue
        seen.add(key)
        pos = webster_pos(wordtype)
        if pos is None:
            pos = definition_label_pos(definition)
            stats["webster_pos_from_definition"] += pos is not None
        rows.append(
            {
                "id": f"webster1913-{index:06d}",
                "word": word,
                "pos": pos,
                "wordtype": wordtype or None,
                "definition": definition,
                "examples": [],
                "synset_id": None,
                "source": "webster1913",
                "_seq": index,
            }
        )
    return rows, stats


# --- Open English WordNet -----------------------------------------------------

OEWN_POS = {"n": "noun", "v": "verb", "a": "adjective", "s": "adjective", "r": "adverb"}


def fetch_oewn() -> Path:
    path = CACHE / OEWN_URL.rsplit("/", 1)[1]
    if not path.exists():
        CACHE.mkdir(exist_ok=True)
        print(f"downloading {OEWN_URL}", file=sys.stderr)
        urllib.request.urlretrieve(OEWN_URL, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != OEWN_SHA256:
        sys.exit(f"{path} has SHA-256 {digest}, expected {OEWN_SHA256}")
    return path


def load_oewn() -> tuple[list[dict], Counter]:
    entries, synsets = [], {}
    with gzip.open(fetch_oewn()) as f:
        for _, el in ET.iterparse(f):
            if el.tag == "LexicalEntry":
                lemma = el.find("Lemma")
                senses = [(s.get("id"), s.get("synset")) for s in el.iter("Sense")]
                entries.append((lemma.get("writtenForm"), lemma.get("partOfSpeech"), senses))
                el.clear()
            elif el.tag == "Synset":
                synsets[el.get("id")] = (
                    "; ".join(squash(d.text or "") for d in el.iter("Definition")),
                    [squash(e.text or "") for e in el.iter("Example") if (e.text or "").strip()],
                )
                el.clear()

    stats = Counter()
    rows = []
    for written_form, pos, senses in entries:
        for sense_id, synset_id in senses:
            definition, examples = synsets[synset_id]
            if not definition:
                stats["oewn_dropped_empty"] += 1
                continue
            rows.append(
                {
                    "id": sense_id,
                    "word": squash(written_form),
                    "pos": OEWN_POS[pos],
                    "wordtype": None,
                    "definition": definition,
                    "examples": examples,
                    "synset_id": synset_id,
                    "source": "oewn",
                    "_seq": len(rows),
                }
            )
    stats["oewn_senses"] = len(rows)
    return rows, stats


# --- Output -------------------------------------------------------------------


def write_jsonl_gz(rows: list[dict], path: Path) -> None:
    # mtime=0 and an empty filename keep the gzip header deterministic.
    with open(path, "wb") as raw, gzip.GzipFile(
        filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9
    ) as gz:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            gz.write(line.encode("utf-8") + b"\n")


def write_parquet(rows: list[dict], path: Path) -> None:
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    # The WordNet notice must appear on all copies, so the file carries the
    # data license itself, not only the repository.
    table = table.replace_schema_metadata(
        {"license": (OUT / "LICENSE-DATA.md").read_text(encoding="utf-8")}
    )
    # Rows are sorted by word, so small row groups let readers that fetch
    # byte ranges over HTTP (DuckDB, Polars) skip most of the file.
    pq.write_table(
        table, path, compression="zstd", row_group_size=20_000, write_statistics=True
    )


def main() -> None:
    webster, stats = load_webster()
    oewn, oewn_stats = load_oewn()
    stats.update(oewn_stats)

    rows = webster + oewn
    rows.sort(
        key=lambda r: (r["word"].casefold(), SOURCE_RANK[r["source"]], r["word"], r["_seq"])
    )
    for row in rows:
        del row["_seq"]

    OUT.mkdir(exist_ok=True)
    jsonl, parquet = OUT / "dictionary.jsonl.gz", OUT / "dictionary.parquet"
    write_jsonl_gz(rows, jsonl)
    write_parquet(rows, parquet)
    sums = "".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in (jsonl, parquet)
    )
    (OUT / "SHA256SUMS").write_text(sums)

    webster_words = {r["word"].casefold() for r in webster}
    oewn_words = {r["word"].casefold() for r in oewn}
    stats["webster_rows"] = len(webster)
    stats["total_rows"] = len(rows)
    stats["unique_words"] = len(webster_words | oewn_words)
    stats["words_only_in_oewn"] = len(oewn_words - webster_words)
    stats["webster_pos_unmapped"] = sum(r["pos"] is None for r in webster)
    for name, value in sorted(stats.items()):
        print(f"{name:28} {value:>9,}")


if __name__ == "__main__":
    main()
