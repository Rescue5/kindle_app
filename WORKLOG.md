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
- Final console error/warning collection was empty.
- `.kimi-code/`, `.vscode/`, generated screenshots, runtime cache, migration
  backup, logs, and user dictionary data were intentionally left untracked.

## 2026-07-11 - Kimi - Fix Kindle connector flicker and bridge `sync_id` crash

### Goal

Fix two regressions reported after the Codex redesign:

1. The Kindle connector button lost its glow and the disconnected notice flashed
   during every background probe, even when the Kindle was still connected.
2. Offline processing failed with `UnboundLocalError: cannot access local variable 'sync_id'`.

### Changes

- `kindle_vocab_app/tauri_bridge.py`: removed duplicated `process_lexemes`,
  `export`, and `load_demo` branches left over from the redesign merge. The
  remaining `process_lexemes`/`optimize` handler is the correct one and no
  longer references the undefined `sync_id` or `source.label` variables.
- `src/features/library/use-library-controller.ts`: stopped setting the Kindle
  connector state to `checking` during `probeConnectors`; the previous connected
  state is now preserved until the probe returns a new factual state.
- `src/features/library/library-workspace.tsx`:
  - `ConnectorNotice` now renders only when the Kindle state is `disconnected`,
    so it no longer appears during checks or errors.
  - `ConnectorButton` no longer uses the `checking` state for a spinner, since
    probing no longer transitions to that state.

### Verification

- `python -m compileall kindle_vocab_app`: passed.
- `python -m unittest discover -s tests -v`: 8 tests passed.
- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `cargo check`: passed.
- `git diff --check`: passed.

### Remaining Risk

- Visual QA was limited to a successful production build and TypeScript checks;
  a live browser/Tauri screenshot was not captured because no browser automation
  tooling was installed in the current environment.

## 2026-07-11 - Kimi - Fix `process_lexemes` tuple handling and add bridge smoke test

### Goal

Fix the follow-up regression `'tuple' object has no attribute 'get'` during offline
processing and add a focused smoke test for the bridge `process_lexemes` path.

### Changes

- `kindle_vocab_app/tauri_bridge.py`: in the `process_lexemes`/`optimize`
  handler, unpacked the tuple returned by `_analysis_by_lemma` into
  `(analyses, analyses_by_id)` and restored the lookup by representative entry id.
- `tests/test_tauri_bridge_smoke.py`: added a new test module covering:
  - `_analysis_by_lemma` returning a `(by_lemma, by_id)` tuple;
  - `dispatch("process_lexemes", ...)` running end-to-end without crashing on
    the tuple return value.
- `.kimi-code/AGENTS.md`: added a "Mandatory verification after every code change"
  section requiring runtime checks, not just static checks, before reporting
  completion.

### Verification

- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 10 tests
  passed (including 2 new bridge smoke tests).
- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed.
- `cargo check`: passed.
- `git diff --check`: passed.

### Remaining Risk

- The new smoke test exercises the happy path; it does not cover all failure
  modes of the optimizer or cancellation edge cases.

## 2026-07-11 - Codex - Recover skipped offline analyses and verify Obsidian state

### Goal

Resolve the remaining bridge error `Не найден audit-файл offline-обработки` and
verify that catalog synchronization marks agree with the configured Obsidian
cards without writing to the vault.

### Changes

- Corrected `process_lexemes` to look up optimizer results by the optimizer's
  normalized candidate key, not only by the display form stored in the catalog.
  This recovers previously processed forms such as an inflected word whose
  audit/snapshot belongs to its base form.
- Treated entries for which the English offline optimizer cannot form a
  candidate as an explicit `rejected` result with the
  `unsupported_language` reason. They no longer report a missing audit file.
- Normalized Obsidian queue reasons from the independent processing state:
  `ready` entries are ready to sync, while rejected and failed entries retain a
  factual blocking reason.
- Added bridge regression coverage for both normalized snapshot recovery and
  unsupported-language rejection.

### Verification

- Re-ran the actual pending-failure batch after the fix: no lexemes remain in
  the `failed` processing state; the unsupported entry is correctly rejected.
- Read-only reconciliation check found 809 catalog entries marked as synced and
  809 matching normalized lemmas in the configured Obsidian cards; there were
  zero catalog entries falsely marked as synced.
- The remaining Obsidian queue consists of ready entries awaiting sync and
  rejected entries with explicit blocking reasons. No vault files were written
  during this verification.

## 2026-07-12 - Kimi - Step 1: async python_bridge with spawn_blocking

### Goal

Make the Tauri `python_bridge` command asynchronous and offload the blocking
Python child-process wait to `tauri::async_runtime::spawn_blocking`, preventing
the Tauri main/UI thread from blocking during backend calls.

### Changes

- `src-tauri/src/main.rs`:
  - Converted `python_bridge` to `async fn` while preserving its
    `Result<Value, String>` frontend contract.
  - Wrapped the managed `OperationState` in `Arc<OperationState>` so it can be
    cloned into the async task and its Drop guard.
  - Added `CancellationTokenGuard` to guarantee removal of the cancellation
    token from `OperationState` even if `spawn_blocking` panics or returns an
    error.
  - Changed `run_python_bridge` to accept `Arc<AtomicBool>` instead of
    `&AtomicBool` for `'static` use inside `spawn_blocking`.
  - Kept `cancel_python_bridge` synchronous and kept the JSON contract and
    progress event emission logic unchanged.

### Verification

- `cargo check` inside `src-tauri`: passed.
- `npm run build`: passed (1,996 modules transformed).

### Remaining Risk

- The change compiles and builds, but the actual WebView→Rust→Python latency
  improvement was not measured with a running Tauri app in this step.
- Concurrent cancellation during a blocking backend call is logically preserved,
  but not exercised by an automated end-to-end test yet.

## 2026-07-12 - Kimi - Step 2: avoid heavy reconciliation on read-only library loads

### Goal

Stop re-reconciling Kindle and Obsidian data on every `load_library`/`load_cached`
call. Heavy reconciliation should only happen during explicit actions that mutate
the catalog.

### Changes

- `kindle_vocab_app/tauri_bridge.py`:
  - Added `reconcile_obsidian: bool = True` to `_load_catalog_with_sources` while
    keeping the existing `reconcile_kindle: bool = True` default.
  - Changed `load_library`/`load_cached` to call with both reconciliation flags
    set to `False`.
  - Changed `sync_kindle`/`scan`, `process_lexemes`/`optimize`, `export`,
    `load_obsidian`, and `sync_obsidian` to call with both flags set to `False`;
    these handlers apply their own targeted Kindle/Obsidian updates afterwards.
  - No response shapes or other logic were changed.

### Verification

- `python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 11 tests
  passed.
- The base-env run failed only because the `wordfreq` dependency is not installed
  outside the `kindle_app` conda environment; this is environmental, not a code
  regression.

### Remaining Risk

- `load_obsidian` now goes through `_load_catalog_with_sources` (which saves the
  catalog and refreshes destination states) before applying its own Obsidian
  merge. This matches the new contract but adds a small amount of redundant I/O
  compared to the previous direct `vocab_cache.load` call.

## 2026-07-12 - Kimi - Frontend performance fix Steps 3–6

### Goal

Reduce React re-renders, debounce search input, remove forced layout in the
operation rail, reduce connector probing frequency, and virtualize the lexeme
table.

### Changes

- `src/features/library/use-library-controller.ts`:
  - Replaced `React.useDeferredValue(query)` with an explicit `debouncedQuery`
    state updated via `setTimeout(..., 180)` and cleared on unmount/query
    change. The controlled `<Input>` still uses `query`; filtering uses
    `debouncedQuery`.
  - Increased the `connector_status` probe interval from 5 s to 30 s.
  - Added a `lastProbedAt` ref that skips interval/focus probes occurring
    sooner than 30 s after the previous probe. Explicit probes (e.g. after a
    Kindle sync) still run immediately via a new `force` argument.
  - Wrapped the returned controller object in `React.useMemo` with all
    primitives, derived values, and callbacks as dependencies, giving
    `LibraryWorkspace`'s `React.memo` a stable reference.

- `src/features/library/library-workspace.tsx`:
  - Removed the `layout` prop from `motion.section` in `OperationRail`; the
    `AnimatePresence` height animation remains.
  - Virtualized `LexemeTable`: tracks `scrollTop`/`clientHeight` of the scroll
    container, renders an overscan slice (±5 rows) with spacer rows before and
    after, and scrolls the selected row into view when it leaves the visible
    window. `LexemeRow` and its `React.memo` are unchanged.

### Verification

- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `git diff --check`: passed (only expected Windows line-ending warnings).

### Remaining Risk

- The virtualized list assumes a fixed 48 px row height. Rows with unusually
    long lemmata or contexts could grow slightly, causing minor scroll drift;
    visual QA on a large real library is recommended.
- Connector probes are now spaced 30 s apart; users connecting/disconnecting a
    Kindle between probes will see the state update only on the next scheduled
    probe or an explicit sync action.

## 2026-07-12 - Kimi - Integrated performance fixes

### Goal

Integrate the async Tauri bridge, Python reconciliation flags, and frontend
performance improvements, then verify the combined change.

### Integration

- Reviewed the three parallel coder outputs (Rust async bridge, Python reconcile
  flags, frontend memoization/virtualization).
- Confirmed no overlapping file edits and no JSON contract changes.
- Verified that `CancellationTokenGuard` removes the token even if the blocking
  task panics.
- Confirmed `_load_catalog_with_sources` defaults remain backward-compatible.
- Checked that the virtualized table preserves grid columns and scrolls selected
  rows into view.

### Verification

- `cargo check` inside `src-tauri`: passed.
- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 11 tests
  passed.
- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `git diff --check`: passed (only expected Windows line-ending warnings).

### Remaining Risk

- Real-world Tauri UI smoothness (window move/resize during heavy operations)
  was not measured in this environment because no live WebView profiling tool
  is available here.
- Visual QA of the virtualized table with a very large library is recommended.
