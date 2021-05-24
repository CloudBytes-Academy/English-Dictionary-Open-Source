## Python

### SQLite3

To import in a python script, follow the instructions below

```python
import sqlite3 as SQL

conn = SQL.connect("sqlite3/dictionary.db") #Or change to other path-to-.db-file
db = conn.cursor()

# Sample Usage
db.execute("SELECT * from entries")
output = db.fetchall()
print(output)
```

