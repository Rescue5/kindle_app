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

## 2026-07-13 - Kimi - Backend: restore skipped snapshot state and report skip count

### Goal

Fix the backend part of three reported issues:
1. Provide a stable Kindle connection signature for frontend auto-sync detection.
2. Restore `ready` processing state for lexemes already present in the processed snapshot when the catalog loads.
3. Include the `skipped_existing` count in the offline-processing completion message so the UI can explain the numbers.

### Changes

- `kindle_vocab_app/tauri_bridge.py`:
  - `_connector_status` now returns `signature` for a connected Kindle source using `source.signature` from `find_kindle_source()`.
  - `_load_catalog_with_sources` now calls `_restore_ready_from_snapshot` after reconciliation and before saving. Pending lexemes whose normalized `lemma`, `display_form`, or any `form` matches a key in `.app-data/optimized/processed_snapshot.json` are marked `ready` with an analysis built by `_analysis_from_snapshot`.
  - Added helpers `_restore_ready_from_snapshot` and `_lexeme_snapshot_keys`.
  - The `process_lexemes`/`optimize` completion event message is now in Russian and includes the `skipped_existing` count: "Обработано: N; принято: N; отклонено: N; пропущено ранее: M".

- `tests/test_tauri_bridge_smoke.py`:
  - Replaced the old `test_process_lexemes_recovers_snapshot_using_normalized_candidate_key` with `test_load_catalog_restores_ready_state_from_snapshot`, which verifies the new catalog-load restore path.
  - Added `test_process_lexemes_message_includes_skipped_existing_in_russian` to assert the Russian message and skip count.

### Verification

- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 12 tests passed.

### Remaining Risk

- The snapshot restore only matches by normalized lemma/forms; lexemes whose processed snapshot key differs from all stored forms will remain pending until reprocessed.
- The new `signature` field in `_connector_status` is only present when a Kindle source is actually connected; the frontend must handle its absence on disconnected/unknown states.
- Full cross-layer verification (npm test, npm run build, cargo check) is left to the integration pass.

## 2026-07-13 - Kimi - Frontend auto-sync, table virtualization, and integration

### Goal

Complete the frontend and integration parts of the three reported issues:
1. Auto-sync Kindle when the connector probe detects a new connection or device signature.
2. Fix the virtualized lexeme table so it renders all visible rows on first mount.
3. Wire the backend's Russian skip-count message through to the UI and verify the full stack.

### Changes

- `src/types.ts`:
  - Added optional `signature?: string[]` to `ConnectorInfo`.

- `src/lib/backend.ts`:
  - `mockConnectors` now returns a stable `signature` for the connected Kindle preview source.

- `src/features/library/use-library-controller.ts`:
  - Added `prevConnectorsRef`, `lastAutoSyncSignatureRef`, and `syncKindleRef`.
  - `probeConnectors` now compares the current Kindle state/signature with the previous probe and triggers `syncKindle` only on a genuine transition to `connected` or when a new signature appears, skipping duplicates and avoiding loops.
  - `syncKindle` records the synced signature so the next probe does not re-trigger.
  - `processVisible` now uses the backend's `message` if present and falls back to a Russian message that includes `skipped_existing`.

- `src/features/library/library-workspace.tsx`:
  - Replaced the post-mount viewport measurement with a callback ref that reads `clientHeight` synchronously when the scroll container is attached.
  - Added a `ResizeObserver` to keep `viewportHeight` accurate on resize.
  - Removed the mutable `containerRef` in favor of a `container` state variable, avoiding TypeScript readonly-ref issues.

- `kindle_vocab_app/tauri_bridge.py`:
  - Added a top-level `message` field to the `process_lexemes`/`optimize` response containing the same Russian skip-count text already used in the event array.

### Verification

- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 12 tests passed.
- `conda run -n kindle_app cargo check --manifest-path src-tauri/Cargo.toml`: passed.
- `git diff --check`: passed (only expected Windows line-ending warning for `WORKLOG.md`).

### Remaining Risk

- Auto-sync is gated by the 30-second probe interval; a Kindle connected and disconnected within that window may be missed.
- The virtualized table still assumes a fixed 48 px row height; unusually long content could cause minor scroll drift on very large libraries.
- Live browser/Tauri screenshot QA was not performed in this environment.

## 2026-07-13 - Kimi - Integration: auto-sync, table virtualization, and snapshot restore

### Goal

Integrate and verify the three reported fixes across frontend, backend, and contracts:
1. Automatic Kindle sync when the device is connected or its signature changes.
2. Virtualized lexeme table renders all visible rows on first paint.
3. Processed-snapshot lexemes are restored to ready state and the skip count is reported in the UI.

### Changes

- `src/types.ts`: added optional `signature?: string[]` to `ConnectorInfo`.
- `src/lib/backend.ts`: mock backend connector status now returns a stable `signature` for the Kindle preview source.
- `src/features/library/use-library-controller.ts`:
  - Tracks the previous connector status and the last auto-synced Kindle signature in refs.
  - `probeConnectors` triggers `syncKindle` only on a genuine transition to `connected` or when the signature changes, avoiding duplicate syncs and loops.
  - `processVisible` now includes `skipped_existing` in the completion message shown in the operation rail.
- `src/features/library/library-workspace.tsx`: fixed the virtualized table initial render by measuring the scroll container through a callback ref and `ResizeObserver`, so `viewportHeight` is never stuck at 0.
- `kindle_vocab_app/tauri_bridge.py`: already updated by the backend pass; verified that `_connector_status` returns `signature`, `_load_catalog_with_sources` restores snapshot state, and the completion event reports `skipped_existing` in Russian.
- `tests/test_tauri_bridge_smoke.py`: already updated by the backend pass; tests pass.

### Verification

- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 12 tests passed.
- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `conda run -n kindle_app cargo check --manifest-path src-tauri/Cargo.toml`: passed.
- `git diff --check`: passed (only expected Windows line-ending warning for `WORKLOG.md`).

### Remaining Risk

- The snapshot restore currently marks every matched lexeme as `ready`, even if the snapshot entry was originally rejected (`accepted: false`). The analysis object preserves the correct `accepted` value, but the UI state does not reflect rejection. This matches the current instruction to set state to `ready`, but may need refinement if rejected snapshot entries exist in the wild.
- First-render auto-sync may trigger an immediate `sync_kindle` when a Kindle is already connected at app startup; this is intentional but could surprise users who expected the app to stay on the cached library.
- Real-world Tauri end-to-end verification (actual USB Kindle connection, auto-sync timing, and large-library table scrolling) was not performed in this environment.

## 2026-07-13 - Kimi - Refine snapshot restore for rejected entries

### Goal

Ensure that lexemes restored from the processed snapshot reflect their original
acceptance status instead of always appearing as `ready`.

### Changes

- `kindle_vocab_app/tauri_bridge.py`: `_restore_ready_from_snapshot` now sets
  `processing.state` to `rejected` when the snapshot entry has `accepted: false`.
- `tests/test_tauri_bridge_smoke.py`: added
  `test_load_catalog_restores_rejected_state_from_snapshot` to cover the
  rejected-restore path.

### Verification

- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `conda run -n kindle_app python -m unittest discover -s tests -v`: 13 tests
  passed.
- `npm test`: 3 Vitest tests passed.
- `npm run build`: passed; 1,996 modules transformed.
- `conda run -n kindle_app cargo check --manifest-path src-tauri/Cargo.toml`:
  passed.
- `git diff --check`: passed (only expected Windows line-ending warnings).

### Remaining Risk

- Live USB Kindle auto-sync timing and large-library table virtualization were
  not verified in this environment.

## 2026-07-13 - Codex - Passive Kindle presence probing

### Goal

Keep automatic Kindle synchronization while preventing periodic connector
checks from browsing device storage or opening `vocab.db`.

### Changes

- Added a lightweight `KindlePresence` detector that checks only top-level
  devices shown by Windows under "This PC". Mounted-volume fallback checks the
  volume identity but does not search folders.
- `connector_status` now uses the passive detector. Full MTP/path traversal and
  copying remain confined to `sync_kindle`.
- Connector polling is limited to once per minute, overlapping probes are
  suppressed, and failed automatic synchronization retries use a five-minute
  backoff.
- Added Python and Vitest coverage for the passive boundary and retry policy.

### Verification

- `conda run -n kindle_app python -m unittest discover -s tests -v`: 16 passed.
- `conda run -n kindle_app python -m compileall kindle_vocab_app`: passed.
- `npm test`: 6 passed.
- `npm run build`: passed; 1,996 modules transformed.
- `conda run -n kindle_app cargo check --manifest-path src-tauri/Cargo.toml`: passed.
- `git diff --check`: passed with expected Windows line-ending warnings.

### Device Safety

- Background probes do not enumerate Kindle folders or copy files.
- Synchronization copies `vocab.db` from Kindle to a local staging/cache path;
  the application never writes, renames, or deletes files on the device.
- A live passive probe reported the device as disconnected at verification
  time, so the connected-device path remains covered by mocks rather than a
  physical Kindle test.

## 2026-07-14 - Codex - SQLite library and one-way Obsidian sync

### Goal

Replace competing JSON state files with one durable SQLite library, process new
Kindle lexemes through a resumable queue, and make Obsidian a verified one-way
destination rather than a source of vocabulary state.

### Decisions

- `.app-data/kindle_cards.sqlite3` is the authoritative application store.
  Legacy catalog and snapshot JSON files are imported once and backed up, but
  are no longer written by the application bridge.
- Lexemes are unique by language and canonical key; forms and Kindle contexts
  remain separate records, and context fingerprints prevent duplicate imports.
- Queue items are committed one lexeme at a time. Accepted and rejected terminal
  states are both durable and are not reanalysed when another form or context is
  discovered.
- Obsidian is read only for reconciliation. A sync rereads the vault, backs it
  up, appends eligible cards, verifies the result, and only then records a
  destination as synced.
- Rejected lexemes remain visible under `Все`, but are excluded from `Новые`
  and `Не в Obsidian`.

### Changes

- Added the versioned SQLite repository, migration, repository-level queue,
  analysis, destination, and sync-run persistence.
- Moved bridge loading, Kindle sync, processing, export state, and Obsidian
  reconciliation to the repository. Added `process_queue` while preserving the
  explicit `process_lexemes` compatibility action.
- Hardened Obsidian append-only writes with exact prefix verification and
  duplicate-lemma blocking inside a single sync batch.
- Replaced the normal manual processing control with compact automatic queue
  status and retry-on-error behavior. Fixed automatic queue resumption after a
  Kindle operation completed.
- Updated frontend contracts, filters, preview fixtures, project documentation,
  and focused Python/Vitest coverage.

### Local Migration Audit

- Imported 1,039 canonical lexemes and 1,332 non-Obsidian occurrences.
- Preserved 1,023 ready and 16 rejected states; the persistent queue is empty.
- Reconciliation reports 1,022 synced, 16 not applicable, and 1 missing
  Obsidian destination, repairing the previously stale synced state.
- SQLite integrity check passed, foreign-key violations are zero, and both
  legacy JSON backup files exist.
- No Obsidian write was performed during the audit.

### Verification

- `conda run -n kindle_app python -m unittest discover -s tests`: 21 passed.
- `conda run -n kindle_app python -m compileall -q kindle_vocab_app`: passed.
- `npm test -- --run`: 8 passed.
- `npm run build`: passed; 1,996 modules transformed.
- `conda run -n kindle_app cargo check -q --manifest-path src-tauri/Cargo.toml`:
  passed.
- Bridge `load_library` smoke: 1,039 entries, zero pending/failed queue items.
- Chromium QA at 1,440 x 900 confirmed automatic queue completion, accepted-only
  `Новые`, eligible-only `Не в Obsidian`, bounded table scrolling, and zero
  console errors or warnings.
- `git diff --check`: passed with expected Windows line-ending warnings.

### Remaining Risk

- A physical Kindle was not connected during the final end-to-end run, so the
  new SQLite path is covered by repository/bridge tests and the existing mocked
  device boundary rather than a live USB sync.
- The standalone optimizer CLI intentionally retains snapshot compatibility;
  application runtime state is SQLite-only.
