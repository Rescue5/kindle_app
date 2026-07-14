# Kindle Vocabulary Builder

Kindle Vocabulary Builder stores looked-up words in an SQLite database named
`vocab.db`. On Kindle e-ink devices connected by USB it is usually here:

```text
Kindle/system/vocabulary/vocab.db
```

The `system` folder may be hidden. The desktop app can copy this database from a
connected Kindle into a local cache automatically.

## Fresh clone setup

Prerequisites:

- Miniconda or Anaconda.
- WebView2 Runtime on Windows. It is usually already installed on modern
  Windows systems.

Fast setup from the repository root:

```powershell
.\scripts\setup-dev.ps1
conda activate kindle_app
kindle-vocab-app
```

On macOS/Linux, use:

```bash
bash scripts/setup-dev.sh
conda activate kindle_app
kindle-vocab-app
```

Manual setup, if you do not want to run the script:

```powershell
conda env create -f environment.yml
conda activate kindle_app
python -m pip install -e .
npm install
npm rebuild esbuild
python -c "import nltk; [nltk.download(package, quiet=True) for package in ('wordnet', 'omw-1.4', 'averaged_perceptron_tagger_eng', 'punkt_tab')]"
kindle-vocab-doctor
kindle-vocab-app
```

`environment.yml` installs Python, Node.js, and Rust/Cargo into the conda
environment. If `kindle-vocab-doctor` reports that `cargo` is missing, rerun
`.\scripts\setup-dev.ps1` so the environment is updated from the current file.

If you see this error:

```text
ModuleNotFoundError: No module named 'kindle_vocab_app'
```

the Python package is not installed in the active environment. Run this from the
repository root:

```powershell
conda activate kindle_app
python -m pip uninstall -y kindle-vocab-app
python -m pip install -e .
```

Then verify the package is importable:

```powershell
python -c "import kindle_vocab_app; print(kindle_vocab_app.__file__)"
```

## Runtime diagnostics

Run this when setup succeeds but the app still does not start:

```powershell
conda activate kindle_app
kindle-vocab-doctor
```

The doctor checks Python imports, Node/npm, Cargo/Rust, NLTK resources, Vite, and
Tauri `cargo metadata`.

## Local environment

LLM enrichment is optional. Copy `.env.example` to `.env` only if you want DS Lab
/ DeepSeek enrichment:

```powershell
Copy-Item .env.example .env
```

Fill `DSLAB_API_KEY` in `.env`. The local deterministic optimizer and the
desktop UI do not require an API key.

The Kindle database and generated exports are local user data and are excluded
from version control.

## Desktop application

The desktop shell is built with React, TypeScript, Tailwind, and Tauri. Python
stays responsible for Kindle database access, deterministic scoring, exports,
and DS Lab / DeepSeek enrichment through the local Tauri bridge.

Logs are written to the local app data directory:

```text
<AppLocalData>/logs/kindle_vocab_app.log
```

The CLI writes logs under the selected output directory:

```text
<output_dir>/logs/kindle_vocab_app.log
```

Set `KINDLE_VOCAB_LOG_LEVEL=DEBUG` to include detailed per-word processing
events.

Features:

- automatically finding a USB-mounted Kindle and loading
  `system/vocabulary/vocab.db` into a local cache;
- manually opening a local `vocab.db` as a fallback;
- selecting a specific book;
- searching across words, contexts, and book metadata;
- previewing words and contexts;
- exporting the current filtered selection to Anki or Quizlet;
- automatically processing previously unseen canonical words in a resumable
  background queue while the application is open;
- storing the authoritative library in `.app-data/kindle_cards.sqlite3`;
- synchronizing accepted words one-way from SQLite to Obsidian without importing
  or overwriting vocabulary from the vault;
- writing `optimized.tsv` plus per-word JSON analysis files as export/audit
  artifacts.

The application checks for newly connected devices with a passive probe once a
minute. On
Windows it supports both ordinary drive letters and Kindle devices shown in
Explorer as `This PC > Kindle` through MTP/WPD. It also supports macOS
`/Volumes` and common Linux mount locations under `/media`, `/run/media`, and
`/mnt`.

## Optimized Export

The desktop application keeps processed lemmas and its resumable queue in
SQLite so already processed items are not processed again. The standalone CLI
retains `processed_snapshot.json` compatibility. The optimizer writes:

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
