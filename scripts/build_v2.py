# /// script
# requires-python = ">=3.10"
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
The build is deterministic: the same inputs give byte-identical outputs.
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
        key = (word, wordtype, definition)
        if key in seen:
            stats["webster_dropped_duplicate"] += 1
            continue
        seen.add(key)
        rows.append(
            {
                "id": f"webster1913-{index:06d}",
                "word": word,
                "pos": webster_pos(wordtype),
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
