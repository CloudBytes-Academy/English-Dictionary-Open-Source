# Open-Source English Dictionary

An open source English language dictionary in CSV, SQLite, MySQL, JSONL, and Parquet.

- **v2** (2026): 388,587 definitions of 221,507 words. It combines the public-domain 1913 Webster's Unabridged Dictionary with modern words from [Open English WordNet](https://github.com/globalwordnet/english-wordnet) 2025+, a free, maintained word database. JSONL and Parquet.
- **v1** (2021): 176,023 definitions of 111,573 words from the 1913 Webster's only. CSV, SQLite, and MySQL. These files are unchanged.

## Getting Started

```bash
git clone https://github.com/CloudBytes-Academy/English-Dictionary-Open-Source
```

Or download the v2 data and its license:

```bash
curl -LO https://raw.githubusercontent.com/CloudBytes-Academy/English-Dictionary-Open-Source/main/v2/dictionary.parquet
curl -LO https://raw.githubusercontent.com/CloudBytes-Academy/English-Dictionary-Open-Source/main/v2/LICENSE-DATA.md
```

Find the [usage instructions here](USAGE.md).

## v2

### Files

| File | Description |
| --- | --- |
| [v2/dictionary.parquet](v2/dictionary.parquet) | Parquet, one row per definition, sorted by word. Opens in pandas, Polars, DuckDB, and Spark. Carries the data license in its metadata, under the key `license`. |
| [v2/dictionary.jsonl.gz](v2/dictionary.jsonl.gz) | The same rows as gzipped JSON Lines, one JSON object per line. |
| [v2/SHA256SUMS](v2/SHA256SUMS) | Checksums of both files. |
| [v2/LICENSE-DATA.md](v2/LICENSE-DATA.md) | Data license and required attribution. |

### Schema

| Column | Type | Description |
| --- | --- | --- |
| `id` | string | Stable ID. `webster1913-000057` (row number in the v1 MySQL dump) or the Open English WordNet sense ID, such as `oewn-email__2.32.00..`. |
| `word` | string | Headword. Webster's words are lowercase. Open English WordNet words keep their case, such as `Paris`. Compare words case-insensitively. |
| `pos` | string or null | Part of speech: `noun`, `verb`, `adjective`, `adverb`, `preposition`, `conjunction`, `pronoun`, `interjection`, `prefix`, `suffix`, or `article`. |
| `wordtype` | string or null | Webster's original abbreviation, such as `v. t.` or `imp. & p. p.`. Null for Open English WordNet rows. |
| `definition` | string | Definition on one line. |
| `examples` | list of strings | Example sentences. Empty for Webster's rows. |
| `synset_id` | string or null | Open English WordNet synset (group of synonyms). Rows with the same `synset_id` are synonyms. Null for Webster's rows. |
| `source` | string | `webster1913` or `oewn`. |

Example rows:

```json
{"id":"webster1913-031182","word":"computer","pos":"noun","wordtype":"n.","definition":"One who computes.","examples":[],"synset_id":null,"source":"webster1913"}
{"id":"oewn-computer__1.06.00..","word":"computer","pos":"noun","wordtype":null,"definition":"a machine for performing calculations automatically","examples":[],"synset_id":"oewn-03086983-n","source":"oewn"}
```

### Contents

| Source | Rows | Notes |
| --- | --- | --- |
| Webster's 1913 | 175,928 | From the v1 MySQL dump, cleaned. |
| Open English WordNet 2025+ | 212,659 | Adds 109,790 words that Webster's does not have: 42,668 single words, such as `smartphone`, `email`, and `blog`, and 67,122 phrases, such as `domestic dog`. |

### What v2 fixes in the Webster's data

- Restores 224 words, such as `-able` and `-ance`, that a spreadsheet had turned into `#NAME?` in the v1 CSV and SQLite files.
- Repairs garbled characters: `80Â¡` becomes `80°`, and `Ã2` becomes `√2`. Also `£`, `÷`, and `§`.
- Joins definitions that had hard line breaks onto one line.
- Removes 93 duplicate rows and 2 empty definitions.
- Maps 271 of the 293 word-type spellings, including typos such as `supperl.` and `n .`, to the 11 values in `pos`. The original is kept in `wordtype`.

### Known issues

- 54 Webster's headwords, and some definitions, contain `/` where an accented letter was lost before this data reached OPTED, such as `assaf/tida` for *assafœtida*.
- 3,919 Webster's rows have no `pos`: 3,882 have no word type, and 37 have one that is not a part of speech, such as `obs.` or `See`.
- About 16,000 Webster's rows are inflected forms whose definition only names the base word, such as `abandoned`, `imp. & p. p.`, `of Abandon`.
- Open English WordNet examples belong to the whole synonym group, so an example can use a synonym instead of the headword.

### Rebuild

The build is reproducible. With the pinned pyarrow version, which uv installs, rebuilds give a byte-identical `dictionary.parquet` (verified on Linux with Python 3.11 to 3.13). `dictionary.jsonl.gz` always holds the same rows, but its compressed bytes depend on the zlib library in your Python: Python 3.14 and later on Windows uses zlib-ng, which writes a different file, so its line in `SHA256SUMS` changes there. The build also checks the download against a pinned SHA-256. It needs [uv](https://docs.astral.sh/uv/).

```bash
uv run scripts/build_v2.py
uv run --with 'pyarrow>=15' --with duckdb --with pandas python -m unittest discover tests
```

The tests that read the public URLs need network, so they run separately:

```bash
uv run --with 'pyarrow>=15' --with duckdb --with pandas python -m unittest discover tests -p 'remote_*.py'
```

The MariaDB import test runs only when `MYSQL_HOST` names a server. It connects over TCP and also reads `MYSQL_TCP_PORT` (default `3306`), `MYSQL_USER` (default `root`), and `MYSQL_PWD`.

## v1

The v1 dictionary has 3 fields

1. **word**: In lowercase
2. **word type**: Abbreviations describe the type, e.g. verb, noun, etc.
3. **definition**: Definition of the word in sentence case

### Database Schema

Both databases use a table named `entries`, but their column types and nullability differ.

| Column | SQLite | MySQL dump |
| --- | --- | --- |
| `word` | `TEXT`, nullable | `varchar(25) NOT NULL` |
| `wordtype` | `TEXT`, nullable | `varchar(20) NOT NULL` |
| `definition` | `TEXT`, nullable | `text NOT NULL` |

SQLite has an index named `ix_entries_word` on `word`. A query on `lower(word)`
cannot use it and scans the whole table. The SQLite file contains 3,895 rows
with a NULL `wordtype` and 2 with a NULL `definition`. CSV and the MySQL dump
use empty strings for these values. The MySQL dump uses MyISAM and latin1.

### Dictionary Format & Repository Structure

| Format & Link                                                | Description                                                  |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| [CSV](csv) | A single file with all the words in standard CSV format      |
| [SQLITE3](sqlite3) | A single file formatted as a SQLITE3 database                |
| [MYSQL](mysql) | MySQL dump that can be imported directly inside MySQL / MariaDB |

## Usage Instructions

| Language                                                     | Instructions are available for                               |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| [Python](USAGE.md#python) | [Parquet](USAGE.md#parquet), [JSONL](USAGE.md#jsonl), [CSV](USAGE.md#csv), [SQLITE3](USAGE.md#sqlite3) |
| [SQL](USAGE.md#duckdb) | [DuckDB](USAGE.md#duckdb), querying Parquet without downloading it first |

## History

v1 is based on the Source Forge Project: [MySQL English Dictionary](https://sourceforge.net/projects/mysqlenglishdictionary/), which in turn is based on [The Online Plain Text English Dictionary (OPTED)](http://www.mso.anu.edu.au/~ralph/OPTED/).

OPTED is a public domain English word list dictionary, based on the public domain portion of "The Project Gutenberg e-text of Webster's Unabridged Dictionary" which is in turn based on the 1913 US Webster's Unabridged Dictionary. See [Project Gutenberg](https://www.gutenberg.org/).

## License

- **Code**: [MIT](LICENSE).
- **v1 data and Webster's rows in v2**: public domain in the USA. OPTED asks redistributors to acknowledge OPTED, Project Gutenberg, and the 1913 Webster's, and to contact Project Gutenberg before commercial use. See [v2/LICENSE-DATA.md](v2/LICENSE-DATA.md).
- **Open English WordNet rows in v2** (`source = 'oewn'`): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), plus the WordNet notice. If you share the v2 files, keep [v2/LICENSE-DATA.md](v2/LICENSE-DATA.md) with them.

## Credits

1. **[Project Gutenberg](https://www.gutenberg.org/)**: For providing the original [1913 US Webster's Unabridged Dictionary](https://www.gutenberg.org/ebooks/29765). Make sure you read the Project Gutenberg's [README](https://www.gutenberg.org/files/29765/29765-ReadMe.txt) for license and other details if you care considering using this for commercial purposes.
2. **[x16bkkamz6rkb78](https://sourceforge.net/u/x16bkkamz6rkb78/profile/)**: For compiling the MySQL dump and releasing on [Source Forge](https://sourceforge.net/projects/mysqlenglishdictionary/).
3. **[dumblob](https://github.com/dumblob)**: For providing the extraordinarily elegant [mysql2sqlite](https://github.com/dumblob/mysql2sqlite) tool for converting the MySQL dump to SQLite3.
4. **[The Open English WordNet Team](https://github.com/globalwordnet/english-wordnet)**: For Open English WordNet, the source of the modern words in v2. See [v2/LICENSE-DATA.md](v2/LICENSE-DATA.md) for the citation.
