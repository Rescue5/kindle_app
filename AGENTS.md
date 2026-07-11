# Project Context

Kindle Vocabulary Builder is a local desktop app for extracting Kindle Vocabulary
Builder entries from `vocab.db`, previewing them, exporting Anki/Quizlet TSV
files, and running deterministic offline optimization only for words that were
not processed before.

The standard Kindle file is:

```text
Kindle/system/vocabulary/vocab.db
```

On Windows the Kindle may appear as either a mounted drive or an MTP/WPD device
under "This PC > Kindle". The backend already has both paths covered; do not
replace this with drive-letter-only detection.

## Communication Rules

- All agent-to-user communication must be in Russian.
- This includes intermediate questions, confirmations, status updates, summaries,
  and explanations of planned or performed actions.
- If reasoning or source material is in another language, translate it to Russian
  before presenting it to the user.
- Code, commands, identifiers, file paths, and technical terms stay in their
  original form.

## Work Log

- Before inspecting or changing the project, read `WORKLOG.md` from the repository
  root so current decisions and unfinished work are not lost.
- `WORKLOG.md` is append-only. Never rewrite, reorder, or delete previous entries.
- Every agent, including delegated agents, must append its own dated entry for
  each logical batch of work. Record the goal, decisions, changed files, checks,
  failures, remaining risks, and commit hashes when available.
- Do not record API keys, `.env` values, private vocabulary contents, full user
  paths, or other sensitive local data in the work log.
- User instructions about whether delegation is allowed always override the
  orchestration defaults below.

## Agent Orchestration

- For multi-step or parallelizable work, spawn focused subagents rather than
  doing everything in the parent thread.
- Use `AgentSwarm` when the problem can be split into independent lanes with
  distinct, non-overlapping scopes.
- Give each subagent a clear, bounded responsibility and all the context it
  needs; do not duplicate work across agents.
- Prefer read-only exploration agents for investigation, coder agents for
  file changes, and plan agents for architecture decisions.

## Stack

- Desktop shell: Tauri v2.
- UI: React 18, TypeScript, Vite, Tailwind, Radix primitives, Framer Motion,
  lucide-react.
- Backend: Python package `kindle_vocab_app`.
- Dev runtime: conda env `kindle_app` with Python, Node.js, and Rust/Cargo from
  `environment.yml`.
- Packaging/config: `pyproject.toml`, `package.json`, `src-tauri/`.
- Runtime data: local ignored app data, not repository state.

Important scripts and entry points:

```powershell
conda activate kindle_app
npm install
kindle-vocab-doctor
kindle-vocab-app
```

If the documented conda env is absent on a machine, check `conda env list`; older
local workspaces may have used a similarly named Kindle env.

Useful checks:

```powershell
npm run build
python -m compileall kindle_vocab_app
'{"action":"load_demo","payload":{}}' | python -m kindle_vocab_app.tauri_bridge
```

For NLP resources:

```powershell
python -m nltk.downloader -q wordnet omw-1.4 averaged_perceptron_tagger_eng punkt_tab
```

## Architecture Map

- `src/main.tsx` is the main UI. It contains the current workspace screen,
  inspectors, processing pipeline, export flow, status strip, and app state.
- `src/lib/backend.ts` is the frontend backend adapter. In Tauri it calls the
  `python_bridge` command; in a plain browser preview it uses mock data.
- `src/types.ts` defines the frontend contract for vocabulary entries,
  processing status, analysis payloads, and API results.
- `src/components/ui/` contains reusable UI primitives. Reuse these before
  adding new one-off controls.
- `src/design/tokens.ts` contains design tokens. UI changes should use these
  tokens instead of ad hoc colors, radii, spacing, or motion values.
- `src-tauri/src/main.rs` owns the Tauri `python_bridge(action, payload)` command.
  It launches `python -m kindle_vocab_app.tauri_bridge` and sends JSON through
  stdin/stdout.
- `kindle_vocab_app/app.py` is now a compatibility launcher for the Tauri dev
  app. It is not the real UI. Do not extend an old PySide/Tk-style UI here.
- `kindle_vocab_app/tauri_bridge.py` is the JSON action dispatcher used by the
  frontend.
- `kindle_vocab_app/kindle_device.py` detects and copies the Kindle `vocab.db`
  from mounted drives or Windows MTP/WPD.
- `kindle_vocab_app/kindle_db.py` reads the SQLite Kindle database and exports
  filtered entries.
- `kindle_vocab_app/vocab_optimizer.py` performs deterministic offline word
  filtering, scoring, TSV generation, and per-word JSON analysis.
- `kindle_vocab_app/processing_state.py` stores the durable processed snapshot.
- `kindle_vocab_app/llm_enricher.py` optionally enriches existing TSV rows
  through the DS Lab/OpenAI-compatible API.
- `kindle_vocab_app/optimizer_cli.py` exposes optimizer and enrichment CLI modes.
- `kindle_vocab_app/settings.py` persists application settings to
  `.app-data/settings.json`.
- `kindle_vocab_app/vocab_cache.py` persists the last loaded vocabulary state to
  `.app-data/vocab_cache.json` so the library is available on restart.
- `kindle_vocab_app/obsidian_sync.py` reads and writes Spaced Repetition cards in
  Obsidian markdown format, handles priority-file mapping, and backs up the
  Obsidian cards folder before writes.

## Backend Contracts

The Tauri bridge currently supports these actions:

- `scan`: find Kindle, copy `vocab.db` into `.app-data/cache`, validate it, and
  return loaded vocabulary state. Merges the result with any previously cached
  state in `.app-data/vocab_cache.json`, preserving `processing_status` and
  `analysis` for already-seen entries and skipping fresh entries whose base form
  is already represented in the cache. Falls back to the cached state when no
  device is found, and to demo state when there is neither a device nor a cache.
- `load_demo`: return demo vocabulary state without touching a Kindle or cache.
- `load_cached`: return the persisted vocabulary state from
  `.app-data/vocab_cache.json`. Falls back to demo state when no cache exists.
  The frontend calls this on startup so the last loaded vocabulary is available
  immediately.
- `optimize`: run `optimize_entries(...)` into `.app-data/optimized`, update
  `processed_snapshot.json`, write `optimized.tsv`, and emit per-entry analysis
  loaded from `word_analysis/*.json`.
- `export`: write `.app-data/kindle-anki.tsv` or `.app-data/kindle-quizlet.tsv`.
- `load_settings`: return the persisted `AppSettings` dict from
  `.app-data/settings.json` (or defaults if missing).
- `save_settings`: validate and persist a settings dict; returns `{"saved": true}`.
- `load_obsidian`: parse Spaced Repetition cards from the configured Obsidian
  vault path and return vocabulary state. Cards are treated as already processed.
- `save_cache`: persist an arbitrary vocabulary state dict to
  `.app-data/vocab_cache.json`. Used to keep the local cache in sync with
  Obsidian so that Kindle scans can skip words already present in Obsidian and
  so that falling back to local cache preserves Obsidian-processed entries.
  Returns `{"saved": true}`.
- `sync_obsidian`: append newly processed entries to the appropriate Obsidian
  priority files, skipping unprocessed or low-importance words. Backs up the
  Obsidian cards folder first (unless disabled in settings). Returns
  `{"added", "skipped", "files", "backup_path"}`.

Bridge output must be clean JSON on stdout. Do not add debug `print(...)` calls
to stdout in bridge code; use logging/stderr/file logs. The Rust bridge forces
UTF-8 via `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`.

Environment variables used by the bridge and launcher:

- `KINDLE_CARDS_PYTHON`: Python executable used by Tauri.
- `KINDLE_CARDS_WORKSPACE`: workspace root passed to Python.
- `KINDLE_VOCAB_LOG_LEVEL`: logging level, for example `DEBUG`.

## Optimizer And Data Rules

The optimizer is intentionally deterministic and explainable. Preserve that
property unless the user explicitly asks for a different model.

- Process only unseen lexical keys by default.
- Persist state in `processed_snapshot.json`.
- Preserve existing optimized TSV rows when rerunning incremental processing.
- Write per-word JSON audit files under `word_analysis/`.
- Leave translation/enrichment fields empty when local logic cannot derive them
  correctly.
- Do not fabricate LLM-derived fields.
- Wiktionary/Wiktextract support is currently a placeholder; do not describe it
  as active unless implemented.

The optimized TSV schema is template-driven and was designed to match the
attached `kindle_anki_optimized.tsv` style. Be careful when changing columns:
the app and CLI both depend on stable import/export behavior.

## LLM Enrichment

Optional enrichment uses DS Lab with an OpenAI-compatible client.

Expected `.env` keys:

```text
DSLAB_API_KEY=...
DSLAB_BASE_URL=https://api.dslab.tech/v1
DSLAB_MODEL=deepseek-v4-flash
```

Also supported: `DSLAB_REASONING_EFFORT`, `DSLAB_TIMEOUT_SECONDS`.

Never commit `.env`, API keys, generated enrichment outputs, or user dictionary
state.

## Runtime Files

Treat these as local/user data and keep them out of commits:

- `.app-data/`
- `.env`
- `vocab.db`
- `kindle-anki.tsv`
- `kindle-quizlet.tsv`
- `kindle_vocab_app.egg-info/`
- `node_modules/`
- `dist/`
- `build/`
- `src-tauri/target/`

The project intentionally tracks `.npmrc` because npm 11 requires explicit
script approval for `esbuild`; without it, fresh installs can leave Vite in a
partially usable state or emit avoidable warnings.

## UI Change Rules

These rules are mandatory for UI work in this repository:

- New features must fit into the existing information architecture. Do not add a
  separate visual language or a detached panel unless the workflow truly needs
  it.
- Reuse existing components from `src/components/ui/` and design tokens from
  `src/design/tokens.ts` before creating new primitives.
- Keep the product visually modern, dense, and work-oriented. Avoid generic
  "AI dashboard" decoration, random gradients, and decorative cards without a
  functional reason.
- Every interactive component needs deliberate hover, pressed, focused,
  disabled, and loading states.
- Every async workflow needs loading, empty, and error states.
- Do not mix business logic into presentational components when a reusable
  helper or backend action is the natural boundary.
- Major UI changes require running the app or build, capturing/reviewing the
  screen, and doing a visual polish pass before considering the work complete.

## Development Notes

- The frontend can be opened in a browser with mock data, but real Kindle
  scanning and filesystem export require Tauri.
- When changing the bridge contract, update TypeScript types, Python dispatcher,
  and Rust error handling together.
- When changing optimizer behavior, add or update a focused CLI/bridge smoke
  check. The most important regression to avoid is reprocessing already-seen
  words.
- Prefer small, explicit configuration files over hidden heuristics. Book genre
  relevance should be configured manually; do not infer genre from title alone.
- Logs are written under local app data for the app and under output-specific
  log directories for CLI runs.
