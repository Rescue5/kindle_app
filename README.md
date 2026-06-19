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
- exporting the current filtered selection to Anki or Quizlet;
- optimizing only previously unseen words into `optimized.tsv` plus per-word
  JSON analysis files.

The application checks for newly connected devices every three seconds. On
Windows it supports both ordinary drive letters and Kindle devices shown in
Explorer as `This PC > Kindle` through MTP/WPD. It also supports macOS
`/Volumes` and common Linux mount locations under `/media`, `/run/media`, and
`/mnt`.

## Optimized Export

The optimizer keeps a local `processed_snapshot.json` so already processed
lemmas and phrases are not processed again. It writes:

- `optimized.tsv`: same columns as the existing optimized Anki template;
- `word_analysis/*.json`: detailed deterministic scoring audit per new word.

Translations and generated example sentences can be filled by DeepSeek V4 Flash
through the DS Lab OpenAI-compatible API. Put your key into `.env`:

```dotenv
DSLAB_API_KEY=your_key_here
DSLAB_BASE_URL=https://api.dslab.tech/v1
DSLAB_MODEL=deepseek-v4-flash
```

The scoring uses local deterministic signals: normalization, context-aware
POS tagging when NLTK data is available, WordNet lemmatization and Lesk sense
selection, `wordfreq` Zipf frequencies, simple proper-noun and OCR/noise
checks, phrase detection, and optional book genre preferences from
`kindle_vocab_app/config/processing.toml`.

CLI usage:

```powershell
kindle-vocab-optimize .\vocab.db .\.app-data\optimized
```

To run the local analysis and then fill translations, generated context, and
revised importance with DeepSeek:

```powershell
kindle-vocab-optimize .\vocab.db .\.app-data\optimized --llm
```

To enrich an already generated `optimized.tsv` without reading the Kindle
database again:

```powershell
kindle-vocab-optimize .\.app-data\optimized --enrich-existing-tsv .\.app-data\optimized\optimized.tsv
```

To seed the snapshot from an existing optimized TSV:

```powershell
kindle-vocab-optimize .\vocab.db .\.app-data\optimized --seed-optimized-tsv C:\path\to\kindle_anki_optimized.tsv
```

For best offline WordNet/POS behavior, install NLTK resources once:

```powershell
python -m nltk.downloader -q wordnet omw-1.4 averaged_perceptron_tagger_eng punkt_tab
```

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
