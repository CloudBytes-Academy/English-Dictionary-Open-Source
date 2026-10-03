# Data license for v2

The code in this repository is MIT licensed (see [LICENSE](../LICENSE)).
The data in `v2/` comes from two sources with different terms. Each row's
`source` column tells you which one it came from.

| `source` | Origin | License |
| --- | --- | --- |
| `webster1913` | Webster's Revised Unabridged Dictionary (1913), via [Project Gutenberg](https://www.gutenberg.org/ebooks/29765) and [OPTED](http://www.mso.anu.edu.au/~ralph/OPTED/) | Public domain |
| `oewn` | [Open English WordNet](https://github.com/globalwordnet/english-wordnet) 2025+ edition | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and the WordNet 3.1 license below |

`dictionary.parquet` and `dictionary.jsonl.gz` contain both sources, so if you
redistribute them you must keep the attribution and notices below. If you
need data with no conditions, keep only the rows where
`source = 'webster1913'`, or use the v1 files in `csv/`, `sqlite3/`, or `mysql/`.

## Open English WordNet attribution

Rows with `source = 'oewn'` are adapted from Open English WordNet 2025+,
Copyright (c) 2019-present, The Open English WordNet Team, licensed under
CC BY 4.0. Changes: definitions and examples were converted to one row per
sense, whitespace was normalized, and part-of-speech codes were renamed
(`n`, `v`, `a`, `s`, `r` to `noun`, `verb`, `adjective`, `adverb`).

Citation:

> John P. McCrae, Alexandre Rademaker, Francis Bond, Ewa Rudnicka and
> Christiane Fellbaum (2019). [English WordNet 2019 – An Open-Source WordNet
> for English](https://aclanthology.org/2019.gwc-1.31/). In *Proceedings of the
> 10th Global WordNet Conference – GWC 2019*, Wrocław.

## WordNet license

Open English WordNet is derived from Princeton WordNet. Its license file
([WNDB_License.txt](https://github.com/globalwordnet/english-wordnet/blob/main/WNDB_License.txt))
requires this notice to appear on all copies:

```
This software and database is being provided to you, the LICENSEE, by
the Open English Wordnet team under the Creative Commons Attribution 4.0
International License (CC-BY 4.0).

Open English Wordnet 2023 Copyright 2023 by the Open English Wordnet team.

Permission to use, copy, modify and distribute this software and
database and its documentation for any purpose and without fee or
royalty is hereby granted, provided that you agree to comply with
the following copyright notice and statements, including the disclaimer,
and that the same appear on ALL copies of the software, database and
documentation, including modifications that you make for internal
use or for distribution.

WordNet 3.1 Copyright 2011 by Princeton University.  All rights reserved.

THIS SOFTWARE AND DATABASE IS PROVIDED "AS IS" AND PRINCETON
UNIVERSITY MAKES NO REPRESENTATIONS OR WARRANTIES, EXPRESS OR
IMPLIED.  BY WAY OF EXAMPLE, BUT NOT LIMITATION, PRINCETON
UNIVERSITY MAKES NO REPRESENTATIONS OR WARRANTIES OF MERCHANT-
ABILITY OR FITNESS FOR ANY PARTICULAR PURPOSE OR THAT THE USE
OF THE LICENSED SOFTWARE, DATABASE OR DOCUMENTATION WILL NOT
INFRINGE ANY THIRD PARTY PATENTS, COPYRIGHTS, TRADEMARKS OR
OTHER RIGHTS.

The name of Princeton University or Princeton may not be used in
advertising or publicity pertaining to distribution of the software
and/or database.  Title to copyright in this software, database and
any associated documentation shall at all times remain with
Princeton University and LICENSEE agrees to preserve same.
```
