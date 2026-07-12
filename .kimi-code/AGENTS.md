# Kimi Code Agent Orchestration Rules

These rules are Kimi-Code-specific. They do not replace the project-wide `AGENTS.md`; they tighten how this model must delegate, integrate, and verify work on the Kindle Vocabulary Builder codebase.

## 1. Mandatory Task Classification

Before editing any file, classify the task as either:

- `direct` — a small, local change in a well-known file.
- `delegated` — a non-trivial task that requires one or more subagents.

A task MUST be `delegated` when any of the following is true:

- It touches more than one stack layer (e.g., Python + React, Python + Rust/Tauri).
- It changes a contract between the frontend, the Python bridge, and/or the Tauri shell.
- It spans more than one subsystem (Kindle device, catalog/cache, optimizer, Obsidian sync, settings, UI).
- It modifies lifecycle, state model, synchronization, or persistence behavior.
- It is an architectural refactor or data migration.
- It requires root-cause analysis of a non-obvious bug.
- It affects more than a few files.
- It allows several independent investigation directions.
- It compares or chooses between multiple implementations.
- It risks losing or corrupting user data.
- It needs implementation, testing, and independent review simultaneously.

A task SHOULD remain `direct` only when it is a trivial change in a single, familiar file with no contract or state implications.

## 2. Subagent Type Selection

Use only the built-in Kimi Code subagent types. Do not invent new ones.

| Type | Use for | Must not |
|------|---------|----------|
| `explore` | Read-only investigation: trace data/control flow, find related files and contracts, locate tests, identify regression risks. | Modify any file. |
| `plan` | Architecture, migrations, contract/state changes, trade-off analysis, producing a concrete implementation plan with files and verification steps. | Implement code or run mutating commands. |
| `coder` | Implement a bounded slice, run commands/tests, edit only assigned files. | Expand scope, edit files outside the assigned area, or make architectural decisions beyond the plan. |

## 3. `Agent` vs `AgentSwarm`

- Use a single `Agent` for a distinct, heterogeneous task or when each agent needs a unique prompt.
- Use `AgentSwarm` only for several independent, identically-shaped tasks expressible as one `prompt_template` plus a list of `items`.
- Do NOT use `AgentSwarm` when agents would edit overlapping files or share a mutable contract.
- Do NOT use `AgentSwarm` for visibility or to satisfy a rule formally.
- For multiple different roles, spawn separate `Agent` calls, not a swarm.
- An `AgentSwarm` call must be the only tool call in its turn.
- Subagents cannot create nested subagents. The parent agent owns all delegation.
- When continuing an earlier subagent task, prefer `resume` over creating a new instance.

## 4. Mandatory Delegation Scenarios for This Project

The following patterns MUST use subagents rather than a single context.

### Complex bug investigation

Spawn parallel `explore` lanes:

- frontend state and user scenario;
- Python bridge and backend lifecycle (`kindle_vocab_app/tauri_bridge.py`, `kindle_vocab_app/vocab_cache.py`);
- Tauri/Rust transport and cancellation (`src-tauri/src/main.rs`);
- existing tests and uncovered edge cases.

The parent agent synthesizes a single root cause before making changes.

### Cross-stack feature

Before implementation:

- `explore` current frontend flow (`src/features/library/`, `src/lib/backend.ts`, `src/types.ts`);
- `explore` backend contracts and data model (`kindle_vocab_app/tauri_bridge.py`, `kindle_vocab_app/vocab_cache.py`, `kindle_vocab_app/settings.py`);
- `plan` for a coordinated contract change.

After the plan, use separate `coder` agents only when file ownership is disjoint, for example:

- Python backend;
- React frontend;
- Rust/Tauri bridge;
- tests.

If changes are tightly coupled or share files, implement them sequentially by the parent agent or a single `coder`.

### Obsidian sync changes

Investigate independently:

- card parsing/rendering (`kindle_vocab_app/obsidian_sync.py`);
- catalog/cache merge and provenance (`kindle_vocab_app/vocab_cache.py`);
- destination state logic (`kindle_vocab_app/tauri_bridge.py`);
- backup and atomic write behavior;
- frontend status representation (`src/features/library/domain.ts`, `src/features/library/library-workspace.tsx`);
- regression tests with existing cards.

### UI work

Before changing UI:

- inspect existing primitives (`src/components/ui/`) and design tokens (`src/design/tokens.ts`);
- verify controller/domain separation (`src/features/library/use-library-controller.ts`, `src/features/library/domain.ts`);
- confirm loading, error, empty, disabled, hover, pressed, and focused states.

After implementation, run a separate review pass for visual regressions, information-architecture violations, business logic leaking into presentational components, and missing async states.

### Optimizer or catalog lifecycle changes

Verify separately:

- reprocessing of already-known lemmas (`kindle_vocab_app/vocab_optimizer.py`, `kindle_vocab_app/processing_state.py`);
- migration of old cache/catalog (`kindle_vocab_app/vocab_cache.py`);
- preservation of forms and contexts;
- deterministic behavior;
- TSV and JSON output compatibility (`kindle_vocab_app/tsv_schema.py`);
- ignored runtime data remaining ignored.

## 5. Subagent Contract

Every subagent prompt MUST be self-contained. Include:

- end goal;
- concrete scope;
- allowed and forbidden actions;
- relevant files or subsystem;
- architectural constraints from this file and the root `AGENTS.md`;
- expected result format;
- required checks;
- a rule that the subagent MUST NOT expand scope without reporting to the parent.

### Required `explore` output

1. Short conclusion.
2. Found data/control flow.
3. Relevant files and symbols.
4. Supporting facts.
5. Risks and unknowns.
6. Recommended next steps.

### Required `coder` output

1. What changed.
2. Files changed.
3. Commands run.
4. Test results.
5. Remaining risks.
6. What the parent agent must verify during integration.

## 6. File Ownership and Parallel Editing

- Two parallel `coder` agents MUST NOT edit the same file.
- Two parallel `coder` agents MUST NOT independently change the same logical contract (e.g., frontend types, bridge action schema, catalog shape).
- Before parallel coding, the parent agent assigns explicit file ownership to each subagent.
- Shared types, API contracts, and state schemas are owned by one subagent and must be integrated before others depend on them.
- After parallel changes, the parent agent re-reads the combined diff and checks cross-layer consistency.
- Never accept a subagent's output blindly.

## 7. Integration and Verification

The parent agent is always responsible for the final result. After any code change—whether made directly or by a subagent—the parent MUST verify that the project still works before reporting completion.

After subagents finish, the parent MUST:

1. Reconcile their findings.
2. Surface contradictions.
3. Verify key claims against source code.
4. Adopt a single implementation plan.
5. Review the final diff.
6. Check frontend/backend/Rust contracts.
7. Run relevant tests and checks.
8. Ensure runtime/user data is unchanged in the repository.
9. Update `WORKLOG.md` according to project rules.

### Mandatory verification after every code change

For every code change, no matter how small, run at least one focused check that exercises the changed path. `compileall` or `tsc` alone is not enough if the change affects runtime behavior.

- Python-only changes: `python -m compileall kindle_vocab_app` AND `python -m unittest discover -s tests -v`.
- React/TypeScript changes: `npm test` AND `npm run build`.
- Rust/Tauri changes: `cargo check`.
- Cross-stack changes: run the full relevant set.
- UI changes: additionally verify visually via browser preview or screenshots when tooling is available.

Do not report a task as complete while tests are failing, the build is broken, or the changed runtime path has not been exercised.

### Verification commands

Choose checks based on touched layers. For cross-stack changes, run the full relevant set:

- `python -m compileall kindle_vocab_app`
- `python -m unittest discover -s tests -v`
- `npm test`
- `npm run build`
- `cargo check`
- `git diff --check`

Run conda commands sequentially; simultaneous `conda run` calls can conflict over temporary files.

## 8. `WORKLOG.md` Handling

Resolve the conflict between the project-wide rule (every delegated agent appends to `WORKLOG.md`) and the read-only nature of `explore`/`plan`:

- `explore` and `plan` agents MUST NOT write to `WORKLOG.md`; they return a structured report to the parent.
- The parent agent writes one consolidated entry after integration, citing the investigation directions used.
- Parallel `coder` agents MUST NOT append to `WORKLOG.md` simultaneously.
- The final entry for a logical batch is written by the parent agent after integration and verification.
- Never allow conflicting parallel appends to a single file.

This is a Kimi-specific clarification of the work-log mechanism, not a change to project requirements.

## 9. User Data Protection

Subagents MUST NOT:

- read or publish `.env`;
- include API keys in reports;
- commit `.app-data`;
- commit `vocab.db`;
- disclose user vocabulary contents;
- delete or mass-overwrite Obsidian cards without explicit instruction;
- treat runtime cache as source code;
- run destructive migrations without backup/rollback analysis.

Investigation should use code, test fixtures, and schemas rather than personal user data whenever possible.

## 10. Antipatterns

MUST NOT:

- spawn multiple agents with the same vague prompt;
- delegate an entire task to one `coder` without a bounded scope;
- use a swarm just to look active;
- edit the same file in parallel;
- re-investigate what another subagent has already established reliably;
- make architectural decisions without synthesizing results;
- continue implementation while subagent conclusions contradict each other;
- hand a subagent a prompt like "figure out the project" without context;
- create an excessive number of agents for a small task;
- replace actual work with endless planning.

## 11. Practical Thresholds

| Situation | Minimum delegation |
|-----------|-------------------|
| Simple local fix in one known file | none (`direct`) |
| Non-obvious bug in one subsystem | at least one `explore` |
| Two independent investigation directions | two parallel `explore` agents or a small swarm |
| Architectural or cross-stack change | `explore` + `plan` before coding |
| Large implementation with disjoint areas | multiple `coder` agents with file ownership |
| After large implementation | independent review and verification by parent |

Use judgment. The real criteria are independence of work, integration complexity, context volume, and regression risk—not rigid bureaucracy.
