# Agent Work Log

This file is an append-only engineering journal for agents working on the
project. Read it before starting work and append a dated entry after every
logical batch. Do not store secrets or private vocabulary data here.

## 2026-07-11 - Codex - Lifecycle and synchronization redesign started

### Goal

Replace the overloaded entry status model with independent lexeme freshness,
processing, source membership, and destination synchronization states. Preserve
Kindle contexts, integrate Obsidian without replacing the library, and make
connector/process UI states factual.

### Audit

- Reviewed commits `2311f25` and `4e25a5f` and the current ignored runtime cache.
- Confirmed that `processing_status` currently mixes novelty and processing.
- Confirmed that `export_status` is reused for file export and Obsidian sync.
- Confirmed that enabling Obsidian replaces frontend library state before a
  client-side lemma merge, losing reliable provenance.
- Confirmed that the cache merge drops fresh Kindle occurrences when a base form
  already exists.
- Confirmed that a missing Kindle returns cached data without a separate physical
  connection state.
- Confirmed that pipeline progress is timer-driven and cancel only ignores the
  eventual response.

### Decisions

- One library row represents one lemma; forms and contexts are occurrences.
- A lemma is new only until the next successful Kindle synchronization.
- Obsidian-imported cards are known, processed, and synchronized.
- Obsidian content wins on conflicts; Kindle contributes forms and occurrences.
- Offline processing remains a manual action.
- The main Obsidian action synchronizes all eligible pending lexemes, regardless
  of the current table filter.
- This implementation is performed by Codex without subagents, per user request.

### Verification Before Changes

- `npm.cmd run build`: passed.
- `conda run -n kindle_app python tests/test_obsidian_sync_smoke.py`: passed.
- `pytest` is not installed in the `kindle_app` conda environment; backend tests
  will use the standard-library `unittest` runner.

### Next

- Introduce catalog schema v2 and migration.
- Replace bridge and frontend contracts.
- Add real progress/cancellation, UI integration, tests, and visual QA.

## 2026-07-11 - Codex - Lifecycle and synchronization redesign implemented

### Backend And Runtime

- Replaced cache v1 entries with catalog v2 lexemes, occurrences, freshness,
  processing, source membership, and independent destination states.
- Added atomic v1 migration with a one-time `.v1.bak` backup and source
  reconciliation from cached Kindle data and configured Obsidian cards.
- Changed Kindle synchronization to preserve known processing while adding new
  forms and contexts. A successful sync advances the novelty batch.
- Changed Obsidian import to merge into the catalog with Obsidian analysis as the
  authority instead of replacing frontend state.
- Added per-lexeme Obsidian outcomes: `added`, `already_present`, `blocked`, and
  `failed`. Existing cards are never overwritten.
- Added optimizer progress callbacks and structured progress events on stderr;
  stdout remains clean bridge JSON.
- Changed the Tauri bridge to stream progress events and terminate the child
  Python process when `cancel_python_bridge(job_id)` is called.
- Improved Obsidian card rendering so the English base form survives round-trip
  parsing for enriched and `NN_PENDING` cards.

### Frontend

- Replaced the old entry contract with `LexemeRecord` and independent connector,
  processing, freshness, source, and destination types.
- Split the former monolithic `src/main.tsx` into a controller hook, pure domain
  selectors, and focused workspace components.
- Removed the bottom-left source card and timer-driven pipeline.
- Added factual Kindle/Obsidian connector controls, five-second focused-window
  probing, combined row states, grouped contexts, global Obsidian sync, and a
  compact operation rail with cancel, retry, and dismiss states.
- Added a real Obsidian enable switch to Settings.
- Added deterministic browser preview scenarios for mixed, disconnected, slow,
  and one-time operation-error states.

### Local Data Migration

- Migrated the ignored local catalog successfully: 1,022 legacy rows became 997
  lexemes without deleting occurrences.
- Reconciliation produced 809 `ready + synced` lexemes and 188
  `pending + not_synced` lexemes.
- Runtime data and its backup remain ignored and are not part of commits.

### Tests And Visual QA

- `python -m compileall kindle_vocab_app`: passed.
- `python -m unittest discover -s tests -v`: 8 tests passed.
- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `cargo check`: passed.
- `git diff --check`: passed; only expected Windows line-ending warnings.
- Browser QA at 1280x720 passed with no console errors and no body overflow.
- Verified filtering, manual processing, global Obsidian sync, disconnected
  Kindle, operation error plus successful retry, cancellation restoring pending
  state, settings navigation, and the Obsidian enable switch.
- Visual polish removed a horizontal table scrollbar, prevented metadata wrapping,
  and improved the narrow inspector's Obsidian status layout.

### Failures Encountered

- `pytest` was unavailable, so backend tests use standard `unittest`.
- Two simultaneous `conda run` commands conflicted over a conda temporary file;
  all conda checks are now run sequentially.
- Vitest dependency installation and execution initially lacked sandbox access;
  both succeeded with the approved external npm cache access.
- PowerShell `Start-Process` inherited duplicate `Path`/`PATH` keys; the local
  Vite server was started through an approved detached Windows process instead.

### Remaining Risk

- Browser preview validates frontend workflows; the Tauri-specific child-process
  cancellation path is covered by Rust compilation and code review, not an
  automated end-to-end WebView test.

## 2026-07-11 - Codex - Redesign finalized

### Commits

- `37d64dd` - work-log protocol and mandatory agent rules.
- `4031d24` - catalog v2, backend lifecycle, progress/cancel bridge, and tests.
- `fc4603b` - React domain/controller/component refactor and Vitest coverage.

### Final Verification

- Re-ran the production frontend build after the final controller and retry
  changes: passed.
- Final Browser screenshots cover a mixed Kindle/Obsidian library with an
  inspected processed lemma and a disconnected Kindle with cached data retained.
- Final Browser console error/warning collection was empty.
- `.kimi-code/`, `.vscode/`, generated screenshots, runtime cache, migration
  backup, logs, and user dictionary data were intentionally left untracked.
