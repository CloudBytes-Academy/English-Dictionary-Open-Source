## Python

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

