# Open-Source English Dictionary

An open source English language dictionary with 176,023 definitions. 

This is based on the Source Forge Project: [MySQL English Dictionary ](https://sourceforge.net/projects/mysqlenglishdictionary/), which in turn in based on the [The Online Plain Text English Dictionary (OPTED)](http://www.mso.anu.edu.au/~ralph/OPTED/) dictionary.

OPTED is a public domain English word list dictionary, based on the public domain portion of "The Project Gutenberg e-text of Webster's Unabridged Dictionary" which is in turn based on the 1913 US Webster's Unabridged Dictionary. See [Project Gutenberg](https://www.gutenberg.org/). 

Since the dictionary is based on 1913 edition, it does not include any modern words (Yet!, but in a future release will include the database Princeton University's [WordNet](https://wordnet.princeton.edu/download/current-version).

## Data Structure

The dictionary has 3 fields

1. word
2. word type
3. definition

## Dictionary Format & Repository Structure

There are 3 formats available as of now

1. [CSV](https://github.com/justgoodin/English-Dictionary-Formatted/tree/main/csv): A single file with all the words in standard CSV format
2. [SQLITE3](https://github.com/justgoodin/English-Dictionary-Formatted/tree/main/sqlite3): A single file formatted as a SQLITE3 database
3. [MYSQL](https://github.com/justgoodin/English-Dictionary-Formatted/tree/main/mysql): MySQL dump that can be imported directly inside MySQL / MariaDB



s

