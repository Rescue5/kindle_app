from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Protocol

from kindle_vocab_app import vocab_cache
from kindle_vocab_app.logging_config import get_logger


logger = get_logger(__name__)

DATABASE_FILENAME = "kindle_cards.sqlite3"
SCHEMA_VERSION = 1


class VocabularyRepository(Protocol):
    def load_catalog(self) -> dict[str, Any]: ...

    def save_catalog(self, catalog: dict[str, Any]) -> None: ...

    def queue_status(self) -> dict[str, int]: ...


class SQLiteVocabularyRepository:
    """Authoritative local vocabulary store used by the desktop application."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.path = workspace / ".app-data" / DATABASE_FILENAME
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def load_catalog(self) -> dict[str, Any]:
        with self.connect() as connection:
            meta = {
                row["key"]: row["value"]
                for row in connection.execute("SELECT key, value FROM metadata")
            }
            lexemes: list[dict[str, Any]] = []
            for row in connection.execute(
                """
                SELECT id, language, canonical_key, display_form, freshness,
                       first_seen_at, last_seen_at, last_kindle_sync_id,
                       source_kindle, source_legacy
                FROM lexemes
                ORDER BY first_seen_at, canonical_key
                """
            ):
                lexeme_id = str(row["id"])
                forms = [
                    str(item["form"])
                    for item in connection.execute(
                        "SELECT form FROM forms WHERE lexeme_id = ? ORDER BY rowid",
                        (lexeme_id,),
                    )
                ]
                occurrences = [
                    {
                        "id": str(item["id"]),
                        "source": str(item["source"]),
                        "word": str(item["word"]),
                        "context": str(item["context"]),
                        "book_key": str(item["book_key"]),
                        "book_title": str(item["book_title"]),
                        "authors": str(item["authors"]),
                        "looked_up_at": str(item["looked_up_at"]),
                    }
                    for item in connection.execute(
                        """
                        SELECT id, source, word, context, book_key, book_title,
                               authors, looked_up_at
                        FROM occurrences WHERE lexeme_id = ?
                        ORDER BY looked_up_at, id
                        """,
                        (lexeme_id,),
                    )
                ]
                analysis_row = connection.execute(
                    """
                    SELECT state, payload_json, updated_at, error
                    FROM analyses WHERE lexeme_id = ?
                    """,
                    (lexeme_id,),
                ).fetchone()
                processing = {
                    "state": str(analysis_row["state"]) if analysis_row else "pending",
                    "analysis": json.loads(str(analysis_row["payload_json"]))
                    if analysis_row and analysis_row["payload_json"]
                    else None,
                    "updated_at": str(analysis_row["updated_at"]) if analysis_row else "",
                    "error": str(analysis_row["error"]) if analysis_row else "",
                }
                destinations = {
                    "obsidian": _default_obsidian_destination(),
                    "anki": {"state": "not_exported", "last_exported_at": ""},
                    "quizlet": {"state": "not_exported", "last_exported_at": ""},
                }
                for destination in connection.execute(
                    """
                    SELECT destination, state, eligible, reason, external_key,
                           last_checked_at, last_synced_at, last_exported_at
                    FROM destinations WHERE lexeme_id = ?
                    """,
                    (lexeme_id,),
                ):
                    name = str(destination["destination"])
                    if name == "obsidian":
                        destinations[name] = {
                            "state": str(destination["state"]),
                            "eligible": bool(destination["eligible"]),
                            "reason": str(destination["reason"]),
                            "external_key": str(destination["external_key"]),
                            "last_checked_at": str(destination["last_checked_at"]),
                            "last_synced_at": str(destination["last_synced_at"]),
                        }
                    elif name in {"anki", "quizlet"}:
                        destinations[name] = {
                            "state": str(destination["state"]),
                            "last_exported_at": str(destination["last_exported_at"]),
                        }
                lexemes.append(
                    {
                        "id": lexeme_id,
                        "lemma": str(row["canonical_key"]),
                        "display_form": str(row["display_form"]),
                        "language": str(row["language"]),
                        "forms": forms,
                        "occurrences": occurrences,
                        "freshness": str(row["freshness"]),
                        "processing": processing,
                        "sources": {
                            "kindle": bool(row["source_kindle"]),
                            "legacy": bool(row["source_legacy"]),
                        },
                        "destinations": destinations,
                        "first_seen_at": str(row["first_seen_at"]),
                        "last_seen_at": str(row["last_seen_at"]),
                        "last_kindle_sync_id": str(row["last_kindle_sync_id"]),
                    }
                )
        return {
            "version": 3,
            "cached_at": meta.get("updated_at", vocab_cache.utc_now()),
            "last_kindle_sync_id": meta.get("last_kindle_sync_id", ""),
            "lexemes": lexemes,
        }

    def save_catalog(self, catalog: dict[str, Any]) -> None:
        canonical = _canonicalize_catalog(catalog)
        with self.connect() as connection:
            self._replace_catalog(connection, canonical)

    def queue_status(self) -> dict[str, int]:
        result = {"pending": 0, "processing": 0, "failed": 0}
        with self.connect() as connection:
            for row in connection.execute(
                "SELECT status, COUNT(*) AS count FROM processing_queue GROUP BY status"
            ):
                result[str(row["status"])] = int(row["count"])
        result["total"] = sum(result.values())
        return result

    def queued_ids(self, requested_ids: set[str] | None = None) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT lexeme_id FROM processing_queue
                WHERE status IN ('pending', 'failed')
                ORDER BY created_at, lexeme_id
                """
            ).fetchall()
        ids = [str(row["lexeme_id"]) for row in rows]
        return [item for item in ids if requested_ids is None or item in requested_ids]

    def save_processed_lexeme(self, catalog: dict[str, Any], lexeme_id: str) -> bool:
        """Persist one processing result; return True when a canonical merge occurred."""
        lexeme = next(
            (item for item in catalog.get("lexemes") or [] if str(item.get("id") or "") == lexeme_id),
            None,
        )
        if lexeme is None:
            return False
        analysis = (lexeme.get("processing") or {}).get("analysis") or {}
        canonical_key = vocab_cache.normalize_lemma(
            str(analysis.get("base_form") or lexeme.get("lemma") or "")
        )
        language = str(lexeme.get("language") or "en")
        with self.connect() as connection:
            conflict = connection.execute(
                """
                SELECT id FROM lexemes
                WHERE language = ? AND canonical_key = ? AND id <> ?
                """,
                (language, canonical_key, lexeme_id),
            ).fetchone()
        if conflict is not None:
            self.save_catalog(catalog)
            return True

        processing = dict(lexeme.get("processing") or {})
        destination = _normalize_obsidian_destination(
            lexeme, ((lexeme.get("destinations") or {}).get("obsidian") or {})
        )
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE lexemes
                SET canonical_key = ?, display_form = ?, freshness = ?,
                    last_seen_at = ?, last_kindle_sync_id = ?
                WHERE id = ?
                """,
                (
                    canonical_key,
                    str(lexeme.get("display_form") or canonical_key),
                    str(lexeme.get("freshness") or "known"),
                    str(lexeme.get("last_seen_at") or vocab_cache.utc_now()),
                    str(lexeme.get("last_kindle_sync_id") or ""),
                    lexeme_id,
                ),
            )
            for form in [canonical_key, *(lexeme.get("forms") or [])]:
                normalized = vocab_cache.normalize_lemma(str(form or ""))
                if normalized:
                    connection.execute(
                        "INSERT OR IGNORE INTO forms(lexeme_id, form, normalized_form) VALUES (?, ?, ?)",
                        (lexeme_id, str(form), normalized),
                    )
            connection.execute(
                """
                INSERT OR REPLACE INTO analyses(
                    lexeme_id, state, payload_json, updated_at, error, origin
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    lexeme_id,
                    processing.get("state") or "pending",
                    json.dumps(processing.get("analysis"), ensure_ascii=False, sort_keys=True)
                    if processing.get("analysis")
                    else None,
                    processing.get("updated_at") or "",
                    processing.get("error") or "",
                    processing.get("origin") or "sqlite_optimizer",
                ),
            )
            state = str(processing.get("state") or "pending")
            if state in {"ready", "rejected"}:
                connection.execute("DELETE FROM processing_queue WHERE lexeme_id = ?", (lexeme_id,))
            else:
                queue_state = "pending" if state == "processing" else state
                connection.execute(
                    """
                    INSERT OR REPLACE INTO processing_queue(
                        lexeme_id, status, created_at, updated_at, error
                    ) VALUES (?, ?, COALESCE(
                        (SELECT created_at FROM processing_queue WHERE lexeme_id = ?), ?
                    ), ?, ?)
                    """,
                    (
                        lexeme_id,
                        queue_state,
                        lexeme_id,
                        str(lexeme.get("first_seen_at") or vocab_cache.utc_now()),
                        processing.get("updated_at") or vocab_cache.utc_now(),
                        processing.get("error") or "",
                    ),
                )
            connection.execute(
                """
                INSERT OR REPLACE INTO destinations(
                    lexeme_id, destination, state, eligible, reason, external_key,
                    last_checked_at, last_synced_at, last_exported_at
                ) VALUES (?, 'obsidian', ?, ?, ?, ?, ?, ?, '')
                """,
                (
                    lexeme_id,
                    destination["state"],
                    int(destination["eligible"]),
                    destination["reason"],
                    destination["external_key"],
                    destination["last_checked_at"],
                    destination["last_synced_at"],
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES ('updated_at', ?)",
                (vocab_cache.utc_now(),),
            )
        return False

    def record_sync_run(
        self,
        connector: str,
        status: str,
        *,
        added: int = 0,
        skipped: int = 0,
        error: str = "",
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sync_runs(connector, status, added, skipped, error, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (connector, status, added, skipped, error, vocab_cache.utc_now()),
            )

    def _initialize(self) -> None:
        migration_completed = False
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            self._create_schema(connection)
            version = connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
            ).fetchone()
            if version is None:
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, vocab_cache.utc_now()),
                )
            migration_completed = connection.execute(
                "SELECT value FROM metadata WHERE key = 'legacy_migration_completed'"
            ).fetchone() is not None
        if not migration_completed:
            self._migrate_legacy_files()

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations(
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metadata(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lexemes(
                id TEXT PRIMARY KEY,
                language TEXT NOT NULL,
                canonical_key TEXT NOT NULL,
                display_form TEXT NOT NULL,
                freshness TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_kindle_sync_id TEXT NOT NULL,
                source_kindle INTEGER NOT NULL DEFAULT 0,
                source_legacy INTEGER NOT NULL DEFAULT 0,
                UNIQUE(language, canonical_key)
            );
            CREATE TABLE IF NOT EXISTS forms(
                lexeme_id TEXT NOT NULL REFERENCES lexemes(id) ON DELETE CASCADE,
                form TEXT NOT NULL,
                normalized_form TEXT NOT NULL,
                PRIMARY KEY(lexeme_id, normalized_form)
            );
            CREATE INDEX IF NOT EXISTS idx_forms_normalized ON forms(normalized_form);
            CREATE TABLE IF NOT EXISTS occurrences(
                id TEXT PRIMARY KEY,
                lexeme_id TEXT NOT NULL REFERENCES lexemes(id) ON DELETE CASCADE,
                source TEXT NOT NULL,
                word TEXT NOT NULL,
                context TEXT NOT NULL,
                book_key TEXT NOT NULL,
                book_title TEXT NOT NULL,
                authors TEXT NOT NULL,
                looked_up_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_occurrences_lexeme ON occurrences(lexeme_id);
            CREATE TABLE IF NOT EXISTS analyses(
                lexeme_id TEXT PRIMARY KEY REFERENCES lexemes(id) ON DELETE CASCADE,
                state TEXT NOT NULL,
                payload_json TEXT,
                updated_at TEXT NOT NULL,
                error TEXT NOT NULL,
                origin TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS processing_queue(
                lexeme_id TEXT PRIMARY KEY REFERENCES lexemes(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS destinations(
                lexeme_id TEXT NOT NULL REFERENCES lexemes(id) ON DELETE CASCADE,
                destination TEXT NOT NULL,
                state TEXT NOT NULL,
                eligible INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL,
                external_key TEXT NOT NULL,
                last_checked_at TEXT NOT NULL,
                last_synced_at TEXT NOT NULL,
                last_exported_at TEXT NOT NULL,
                PRIMARY KEY(lexeme_id, destination)
            );
            CREATE TABLE IF NOT EXISTS sync_runs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connector TEXT NOT NULL,
                status TEXT NOT NULL,
                added INTEGER NOT NULL DEFAULT 0,
                skipped INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL,
                completed_at TEXT NOT NULL
            );
            """
        )

    def _migrate_legacy_files(self) -> None:
        catalog_path = self.workspace / ".app-data" / vocab_cache.CACHE_FILENAME
        snapshot_path = self.workspace / ".app-data" / "optimized" / "processed_snapshot.json"
        for path in (catalog_path, snapshot_path):
            if path.exists():
                backup = path.with_suffix(path.suffix + ".sqlite-migration.bak")
                if not backup.exists():
                    shutil.copy2(path, backup)

        catalog = vocab_cache.load(self.workspace) or vocab_cache.empty_catalog()
        snapshot: dict[str, Any] = {}
        if snapshot_path.exists():
            try:
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except Exception:
                logger.exception("Failed to read legacy processed snapshot path=%s", snapshot_path)
        migrated = _canonicalize_catalog(catalog, snapshot.get("processed") or {})
        with self.connect() as connection:
            self._replace_catalog(connection, migrated)
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES ('legacy_migration_completed', ?)",
                (vocab_cache.utc_now(),),
            )
        logger.info(
            "Migrated legacy vocabulary state to SQLite path=%s lexemes=%d",
            self.path,
            len(migrated["lexemes"]),
        )

    def _replace_catalog(self, connection: sqlite3.Connection, catalog: dict[str, Any]) -> None:
        connection.execute("DELETE FROM lexemes")
        now = vocab_cache.utc_now()
        for lexeme in catalog.get("lexemes") or []:
            processing = dict(lexeme.get("processing") or {})
            state = str(processing.get("state") or "pending")
            connection.execute(
                """
                INSERT INTO lexemes(
                    id, language, canonical_key, display_form, freshness,
                    first_seen_at, last_seen_at, last_kindle_sync_id,
                    source_kindle, source_legacy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lexeme["id"],
                    lexeme["language"],
                    lexeme["lemma"],
                    lexeme["display_form"],
                    lexeme["freshness"],
                    lexeme["first_seen_at"],
                    lexeme["last_seen_at"],
                    lexeme["last_kindle_sync_id"],
                    int(bool((lexeme.get("sources") or {}).get("kindle"))),
                    int(bool((lexeme.get("sources") or {}).get("legacy"))),
                ),
            )
            for form in lexeme.get("forms") or []:
                normalized = vocab_cache.normalize_lemma(str(form))
                if normalized:
                    connection.execute(
                        "INSERT OR IGNORE INTO forms(lexeme_id, form, normalized_form) VALUES (?, ?, ?)",
                        (lexeme["id"], str(form), normalized),
                    )
            for occurrence in lexeme.get("occurrences") or []:
                if occurrence.get("source") == "obsidian":
                    continue
                connection.execute(
                    """
                    INSERT OR IGNORE INTO occurrences(
                        id, lexeme_id, source, word, context, book_key,
                        book_title, authors, looked_up_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        occurrence["id"],
                        lexeme["id"],
                        occurrence.get("source") or "kindle",
                        occurrence.get("word") or "",
                        occurrence.get("context") or "",
                        occurrence.get("book_key") or "",
                        occurrence.get("book_title") or "",
                        occurrence.get("authors") or "",
                        occurrence.get("looked_up_at") or "",
                    ),
                )
            analysis = processing.get("analysis")
            connection.execute(
                """
                INSERT INTO analyses(lexeme_id, state, payload_json, updated_at, error, origin)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    lexeme["id"],
                    state,
                    json.dumps(analysis, ensure_ascii=False, sort_keys=True) if analysis else None,
                    processing.get("updated_at") or "",
                    processing.get("error") or "",
                    processing.get("origin") or "catalog",
                ),
            )
            if state in {"pending", "processing", "failed"}:
                queue_state = "pending" if state == "processing" else state
                connection.execute(
                    """
                    INSERT INTO processing_queue(lexeme_id, status, created_at, updated_at, error)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        lexeme["id"],
                        queue_state,
                        lexeme.get("first_seen_at") or now,
                        processing.get("updated_at") or now,
                        processing.get("error") or "",
                    ),
                )
            destinations = lexeme.get("destinations") or {}
            obsidian = _normalize_obsidian_destination(lexeme, destinations.get("obsidian") or {})
            connection.execute(
                """
                INSERT INTO destinations(
                    lexeme_id, destination, state, eligible, reason, external_key,
                    last_checked_at, last_synced_at, last_exported_at
                ) VALUES (?, 'obsidian', ?, ?, ?, ?, ?, ?, '')
                """,
                (
                    lexeme["id"],
                    obsidian["state"],
                    int(obsidian["eligible"]),
                    obsidian["reason"],
                    obsidian["external_key"],
                    obsidian["last_checked_at"],
                    obsidian["last_synced_at"],
                ),
            )
            for name in ("anki", "quizlet"):
                destination = destinations.get(name) or {}
                connection.execute(
                    """
                    INSERT INTO destinations(
                        lexeme_id, destination, state, eligible, reason, external_key,
                        last_checked_at, last_synced_at, last_exported_at
                    ) VALUES (?, ?, ?, 0, '', '', '', '', ?)
                    """,
                    (
                        lexeme["id"],
                        name,
                        destination.get("state") or "not_exported",
                        destination.get("last_exported_at") or "",
                    ),
                )
        metadata = {
            "last_kindle_sync_id": str(catalog.get("last_kindle_sync_id") or ""),
            "updated_at": now,
        }
        for key, value in metadata.items():
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                (key, value),
            )


def repository_for(workspace: Path) -> SQLiteVocabularyRepository:
    return SQLiteVocabularyRepository(workspace)


def _canonicalize_catalog(
    catalog: dict[str, Any],
    snapshot: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    snapshot = snapshot or {}
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in catalog.get("lexemes") or []:
        sources = raw.get("sources") or {}
        if sources.get("obsidian") and not sources.get("kindle") and not sources.get("legacy"):
            continue
        processing = raw.get("processing") or {}
        analysis = processing.get("analysis") or {}
        key = vocab_cache.normalize_lemma(
            str(analysis.get("base_form") or raw.get("lemma") or raw.get("display_form") or "")
        )
        if not key:
            continue
        language = str(raw.get("language") or "en")
        group_key = (language.casefold(), key)
        target = grouped.get(group_key)
        if target is None:
            target = {
                **raw,
                "id": vocab_cache.lexeme_id(language, key),
                "lemma": key,
                "language": language,
                "forms": [],
                "occurrences": [],
                "sources": {"kindle": False, "obsidian": False, "legacy": False},
                "_all_new": True,
            }
            grouped[group_key] = target
        target["first_seen_at"] = min(
            str(target.get("first_seen_at") or vocab_cache.utc_now()),
            str(raw.get("first_seen_at") or vocab_cache.utc_now()),
        )
        target["last_seen_at"] = max(
            str(target.get("last_seen_at") or ""), str(raw.get("last_seen_at") or "")
        )
        if raw.get("freshness") != "new":
            target["_all_new"] = False
        for name in ("kindle", "legacy"):
            target["sources"][name] = bool(target["sources"].get(name) or sources.get(name))
        for form in [raw.get("display_form"), raw.get("lemma"), *(raw.get("forms") or [])]:
            normalized = vocab_cache.normalize_lemma(str(form or ""))
            if normalized and normalized not in {
                vocab_cache.normalize_lemma(str(item)) for item in target["forms"]
            }:
                target["forms"].append(str(form))
        existing_occurrences = {str(item.get("id") or "") for item in target["occurrences"]}
        for occurrence in raw.get("occurrences") or []:
            if occurrence.get("source") == "obsidian":
                continue
            if str(occurrence.get("id") or "") not in existing_occurrences:
                target["occurrences"].append(dict(occurrence))
                existing_occurrences.add(str(occurrence.get("id") or ""))
        target["processing"] = _preferred_processing(target.get("processing"), processing)
        target["destinations"] = _preferred_destinations(
            target.get("destinations"), raw.get("destinations")
        )

    for target in grouped.values():
        target["freshness"] = "new" if target.pop("_all_new", False) else "known"
        candidates = {
            target["lemma"],
            *(vocab_cache.normalize_lemma(str(form)) for form in target.get("forms") or []),
        }
        snapshot_key = next((key for key in candidates if key in snapshot), "")
        if snapshot_key:
            payload = snapshot[snapshot_key]
            accepted = bool(payload.get("accepted", True))
            existing_analysis = (target.get("processing") or {}).get("analysis") or {}
            target["processing"] = {
                "state": "ready" if accepted else "rejected",
                "analysis": {
                    **existing_analysis,
                    "base_form": str(payload.get("base_form") or target["lemma"]),
                    "accepted": accepted,
                    "importance_score": payload.get("importance"),
                    "source_occurrence_count": payload.get("source_occurrence_count"),
                    "translation_status": existing_analysis.get("translation_status") or "offline_only",
                },
                "updated_at": str(payload.get("last_seen_at") or vocab_cache.utc_now()),
                "error": "",
                "origin": "processed_snapshot",
            }
        elif (target.get("processing") or {}).get("state") in {"ready", "rejected"}:
            target["processing"]["origin"] = "legacy_catalog"
        target.setdefault("display_form", target["lemma"])
        target.setdefault("freshness", "known")
        target.setdefault("first_seen_at", vocab_cache.utc_now())
        target.setdefault("last_seen_at", target["first_seen_at"])
        target.setdefault("last_kindle_sync_id", "")

    return {
        "version": 3,
        "cached_at": vocab_cache.utc_now(),
        "last_kindle_sync_id": str(catalog.get("last_kindle_sync_id") or ""),
        "lexemes": list(grouped.values()),
    }


def _preferred_processing(left: Any, right: Any) -> dict[str, Any]:
    left = dict(left or {"state": "pending", "analysis": None, "updated_at": "", "error": ""})
    right = dict(right or {})
    rank = {"pending": 0, "processing": 1, "failed": 2, "rejected": 3, "ready": 4}
    if rank.get(str(right.get("state")), 0) > rank.get(str(left.get("state")), 0):
        return right
    return left


def _preferred_destinations(left: Any, right: Any) -> dict[str, Any]:
    result = dict(left or {})
    for name, destination in dict(right or {}).items():
        current = result.get(name) or {}
        if destination.get("state") in {"synced", "exported"} or not current:
            result[name] = dict(destination)
    return result


def _default_obsidian_destination() -> dict[str, Any]:
    return {
        "state": "not_applicable",
        "eligible": False,
        "reason": "waiting_processing",
        "external_key": "",
        "last_checked_at": "",
        "last_synced_at": "",
    }


def _normalize_obsidian_destination(
    lexeme: dict[str, Any], destination: dict[str, Any]
) -> dict[str, Any]:
    processing = lexeme.get("processing") or {}
    analysis = processing.get("analysis") or {}
    score = analysis.get("importance_score")
    eligible = (
        processing.get("state") == "ready"
        and analysis.get("accepted") is not False
        and isinstance(score, (int, float))
        and 3 <= score <= 10
    )
    old_state = str(destination.get("state") or "")
    if old_state == "synced" and eligible:
        state = "synced"
        reason = ""
    elif old_state == "failed" and eligible:
        state = "failed"
        reason = str(destination.get("reason") or "sync_failed")
    elif eligible:
        state = "missing"
        reason = ""
    else:
        state = "not_applicable"
        if processing.get("state") == "rejected":
            reason = str(destination.get("reason") or "rejected")
        elif processing.get("state") == "failed":
            reason = "processing_failed"
        elif processing.get("state") == "ready":
            reason = "unsupported_priority"
        else:
            reason = "waiting_processing"
    return {
        "state": state,
        "eligible": eligible,
        "reason": reason,
        "external_key": vocab_cache.normalize_lemma(str(lexeme.get("lemma") or "")),
        "last_checked_at": str(destination.get("last_checked_at") or ""),
        "last_synced_at": str(destination.get("last_synced_at") or ""),
    }
