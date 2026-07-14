from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from kindle_vocab_app import vocab_cache
from kindle_vocab_app.library_repository import DATABASE_FILENAME, repository_for


def lexeme(
    item_id: str,
    lemma: str,
    *,
    base_form: str | None = None,
    state: str = "pending",
    source_kindle: bool = True,
    source_obsidian: bool = False,
) -> dict[str, object]:
    analysis = None
    if state in {"ready", "rejected"}:
        analysis = {
            "base_form": base_form or lemma,
            "accepted": state == "ready",
            "importance_score": 7 if state == "ready" else 1,
        }
    return {
        "id": item_id,
        "lemma": lemma,
        "display_form": lemma,
        "language": "en",
        "forms": [lemma],
        "occurrences": [
            {
                "id": f"occ-{item_id}",
                "source": "kindle" if source_kindle else "obsidian",
                "word": lemma,
                "context": f"Context for {item_id}",
                "book_key": "book",
                "book_title": "Book",
                "authors": "Author",
                "looked_up_at": "2026-07-10",
            }
        ],
        "freshness": "new",
        "processing": {"state": state, "analysis": analysis, "updated_at": "now", "error": ""},
        "sources": {"kindle": source_kindle, "obsidian": source_obsidian, "legacy": False},
        "destinations": {
            "obsidian": {"state": "not_synced", "reason": "", "last_synced_at": ""},
            "anki": {"state": "not_exported", "last_exported_at": ""},
            "quizlet": {"state": "not_exported", "last_exported_at": ""},
        },
        "first_seen_at": "2026-07-10T00:00:00+00:00",
        "last_seen_at": "2026-07-10T00:00:00+00:00",
        "last_kindle_sync_id": "sync",
    }


class SQLiteVocabularyRepositoryTests(unittest.TestCase):
    def test_migration_backs_up_json_deduplicates_and_excludes_obsidian_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            app_data = workspace / ".app-data"
            optimized = app_data / "optimized"
            optimized.mkdir(parents=True)
            catalog = {
                "version": 2,
                "last_kindle_sync_id": "sync",
                "lexemes": [
                    lexeme("one", "leaned", base_form="lean", state="ready"),
                    lexeme("two", "lean", state="pending"),
                    lexeme(
                        "obsidian-only",
                        "private",
                        state="ready",
                        source_kindle=False,
                        source_obsidian=True,
                    ),
                ],
            }
            catalog_path = app_data / vocab_cache.CACHE_FILENAME
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            snapshot_path = optimized / "processed_snapshot.json"
            snapshot_path.write_text(
                json.dumps(
                    {
                        "processed": {
                            "lean": {
                                "accepted": True,
                                "importance": 8,
                                "base_form": "lean",
                                "source_occurrence_count": 2,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            repository = repository_for(workspace)
            migrated = repository.load_catalog()

            self.assertEqual(len(migrated["lexemes"]), 1)
            self.assertEqual(migrated["lexemes"][0]["lemma"], "lean")
            self.assertEqual(len(migrated["lexemes"][0]["occurrences"]), 2)
            self.assertEqual(migrated["lexemes"][0]["processing"]["state"], "ready")
            self.assertEqual(
                migrated["lexemes"][0]["processing"]["analysis"]["importance_score"], 8
            )
            self.assertTrue(
                catalog_path.with_suffix(catalog_path.suffix + ".sqlite-migration.bak").exists()
            )
            self.assertTrue(
                snapshot_path.with_suffix(snapshot_path.suffix + ".sqlite-migration.bak").exists()
            )
            self.assertEqual(repository.queue_status()["total"], 0)

            database = app_data / DATABASE_FILENAME
            with closing(sqlite3.connect(database)) as connection:
                self.assertEqual(
                    connection.execute("PRAGMA journal_mode").fetchone()[0].casefold(), "wal"
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0], 1
                )

    def test_pending_state_survives_repository_reload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            repository = repository_for(workspace)
            catalog = vocab_cache.empty_catalog()
            catalog["lexemes"] = [lexeme("pending", "perplexed")]
            repository.save_catalog(catalog)

            reopened = repository_for(workspace)
            loaded = reopened.load_catalog()

            self.assertEqual(loaded["lexemes"][0]["processing"]["state"], "pending")
            self.assertEqual(reopened.queued_ids(), [loaded["lexemes"][0]["id"]])
            self.assertEqual(reopened.queue_status()["pending"], 1)


if __name__ == "__main__":
    unittest.main()
