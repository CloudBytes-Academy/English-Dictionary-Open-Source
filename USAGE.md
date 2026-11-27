## Python

### Parquet

Read the v2 dictionary with pandas (`pip install pandas pyarrow`)

```python
import pandas as pd

df = pd.read_parquet("v2/dictionary.parquet")

# All definitions of a word, Webster's first, then Open English WordNet
print(df[df["word"].str.lower() == "computer"][["pos", "definition", "source"]])

# Only the public-domain Webster's rows
webster = df[df["source"] == "webster1913"]
```

### JSONL

The JSONL file needs only the Python standard library

```python
import gzip
import json

with gzip.open("v2/dictionary.jsonl.gz", "rt", encoding="utf-8") as file:
    for line in file:
        row = json.loads(line)
        if row["word"].lower() == "blog":
            print(row["pos"], row["definition"])
```

### CSV

The CSV file needs only the Python standard library. Each row has three columns: `word`, `wordtype` and `definition`. Words are lowercase.

Look up one word:

```python
import csv

with open("csv/dictionary.csv", encoding="utf-8", newline="") as file:
    for row in csv.DictReader(file):
        if row["word"] == "computer":
            print(row["wordtype"], row["definition"])
```

Or load every row into a list, with one dictionary per row:

```python
import csv

with open("csv/dictionary.csv", encoding="utf-8", newline="") as file:
    rows = list(csv.DictReader(file))

print(len(rows), "rows")
print(rows[56])  # {'word': 'abandoned', 'wordtype': 'imp. & p. p.', 'definition': 'of Abandon'}
```

The v1 files have some known problems that v2 fixes. For example, a spreadsheet turned 145 words, in 224 rows, into `#NAME?` in the CSV file. Those are the only words there that are not lowercase. The SQLite file stores them as `#name?`.

### SQLite3

The SQLite file also needs only the Python standard library. It has one table, `entries`, with the same three columns as the CSV file.

Look up one word:

```python
import sqlite3

connection = sqlite3.connect("sqlite3/dictionary.db")

query = "SELECT wordtype, definition FROM entries WHERE word = ?"
for wordtype, definition in connection.execute(query, ("computer",)):
    print(wordtype, definition)

connection.close()
```

The `?` stands for the word you look up. Passing the word separately, as `("computer",)`, is safer than pasting it into the query text. The table has an index on `word`, so the lookup is fast. Words are lowercase, so look them up in lowercase too.

## DuckDB

[DuckDB](https://duckdb.org/) queries the Parquet file with SQL, from disk or straight from GitHub. Over HTTP it downloads only the parts of the file it needs. The first line keeps that download small on DuckDB 2.0 and later: without it, DuckDB reads ahead and downloads about 11 MB of the 18.6 MB file, instead of about 2 MB. On DuckDB 1.5 or earlier, leave the first line out, because there it downloads the whole file.

```sql
SET disable_parquet_prefetching = true;
SELECT word, pos, definition, source
FROM 'https://raw.githubusercontent.com/CloudBytes-Academy/English-Dictionary-Open-Source/main/v2/dictionary.parquet'
WHERE lower(word) = 'email';
```

Synonyms are the rows that share a `synset_id`

```sql
SELECT DISTINCT b.word
FROM 'v2/dictionary.parquet' a
JOIN 'v2/dictionary.parquet' b USING (synset_id)
WHERE lower(a.word) = 'happy' AND lower(b.word) <> 'happy';
```
