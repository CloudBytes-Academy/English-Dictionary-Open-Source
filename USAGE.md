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

To import in a file object, we recommend using DictReader

```python
from csv import DictReader

data = []
with open("sandbox/dictionary.csv") as file:
    rows = DictReader(file)
    for row in rows:
        data.append(row)
        
# produces a list of dictionaries where each element is organised as
# {"word":"word", "wordtype": "type of word", "definition": "definition of word"}
print(data) 
```

However, you can also use a generic CSV reader to import the data as a list of lists

```python
from csv import reader

data = []
with open("sandbox/dictionary.csv") as file:
    rows = reader(file)
    for row in rows:
        data.append(row)
        
# produces a list of lists where each element is organised as
# [word, wordtype, definition]
print(data) 
```

### SQLite3

To import in a python script using SQLite3 library, follow the instructions below

```python
import sqlite3 as SQL

conn = SQL.connect("sqlite3/dictionary.db") #Or change to other path-to-.db-file
db = conn.cursor()

# Sample Usage
db.execute("SELECT * from entries")
output = db.fetchall()
print(output)
db.close()
```

## DuckDB

[DuckDB](https://duckdb.org/) queries the Parquet file with SQL, from disk or straight from GitHub. Over HTTP it downloads only the parts of the file it needs.

```sql
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
