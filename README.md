# Kindle Vocabulary Builder Export

Kindle Vocabulary Builder stores looked-up words in an SQLite database named
`vocab.db`. On Kindle e-ink devices connected by USB it is usually here:

```text
Kindle/system/vocabulary/vocab.db
```

The `system` folder may be hidden. Copy `vocab.db` from the Kindle to your
computer first, then run the exporter against the copy.

## Desktop application

Install the app into the conda environment, then run:

```powershell
conda activate kindle-vocab-app
kindle-vocab-app
```

The Kindle database and generated exports are local user data and are excluded
from version control.

The native Qt application supports Windows, macOS, and Linux. It uses a built-in
dark theme and does not start a web server.

Features:

- automatically finding a USB-mounted Kindle and loading
  `system/vocabulary/vocab.db` into a local cache;
- manually opening a local `vocab.db` as a fallback;
- selecting a specific book;
- searching across words, contexts, and book metadata;
- previewing words and contexts;
- exporting the current filtered selection to Anki or Quizlet.

The application checks for newly connected devices every three seconds. On
Windows it supports both ordinary drive letters and Kindle devices shown in
Explorer as `This PC > Kindle` through MTP/WPD. It also supports macOS
`/Volumes` and common Linux mount locations under `/media`, `/run/media`, and
`/mnt`.

## Export for Anki

```powershell
python .\export_kindle_vocab.py .\vocab.db .\kindle-anki.tsv --format anki --html
```

Import `kindle-anki.tsv` into Anki as tab-separated text. The fields are:

```text
word, stem, context, book_title, authors, language, looked_up_at
```

If you use `--html`, enable "Allow HTML in fields" during import.

## Export for Quizlet

```powershell
python .\export_kindle_vocab.py .\vocab.db .\kindle-quizlet.tsv --format quizlet
```

Quizlet imports term/definition pairs. Kindle's `vocab.db` usually does not
contain dictionary definitions, so this export uses the sentence context plus
book source as the definition side.

## Notes

The relevant Kindle tables are generally:

- `WORDS`: word, stem, language, timestamp
- `LOOKUPS`: lookup event, context sentence, dictionary/book keys, timestamp
- `BOOK_INFO`: title, author, language, ASIN/GUID metadata
