## Getting Started

You can clone the repository by running

`git clone https://github.com/justgoodin/English-Dictionary-Formatted.git`

## Database Schema

The table is named 'entries' and has the following schema

```sqlite
Column      Type             Schema
------      --------------   -------------------------------
word        varchar(25)      "word" varchar(25) NOT NULL
wordtype    varchar(20)      "wordtype" varchar(20) NOT NULL  
definition  text             "definition" text NOT NULL
```

## Importing into your program

Import will vary based on the language you are using: 

* [Python SQLite3](#Python) 

## Language specific instructions

### Python SQLite3

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



