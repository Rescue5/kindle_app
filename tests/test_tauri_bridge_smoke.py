from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kindle_vocab_app import vocab_cache
from kindle_vocab_app.kindle_device import KindlePresence
from kindle_vocab_app.library_repository import repository_for
from kindle_vocab_app.obsidian_sync import append_cards, read_cards
from kindle_vocab_app.processing_state import ProcessedSnapshot
from kindle_vocab_app.tauri_bridge import _analysis_by_lemma, _load_catalog_with_sources, dispatch


class BridgeSmokeTests(unittest.TestCase):
    def test_connector_status_uses_passive_presence_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            presence = KindlePresence(
                label="Kindle · Paperwhite",
                signature=("windows-device", "kindle-paperwhite"),
            )
            with (
                patch("kindle_vocab_app.tauri_bridge.find_kindle_presence", return_value=presence),
                patch("kindle_vocab_app.tauri_bridge.find_kindle_source") as source_probe,
            ):
                result = dispatch("connector_status", {}, workspace)

            source_probe.assert_not_called()
            self.assertEqual(result["kindle"]["state"], "connected")
            self.assertEqual(result["kindle"]["signature"], list(presence.signature))

    def test_analysis_by_lemma_returns_tuple(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            analysis_dir = Path(temporary)
            analysis_dir.joinpath("test.json").write_text(
                '{"lexical_key": "admit", "base_form": "admit", "accepted": true, '
                '"importance": {"score": 8}, "representative_entry": {"id": "occ-1"}}',
                encoding="utf-8",
            )
            by_lemma, by_id = _analysis_by_lemma(analysis_dir)
            self.assertIn("admit", by_lemma)
            self.assertIn("occ-1", by_id)

    def test_load_obsidian_reconciles_without_importing_or_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            catalog = vocab_cache.merge_kindle(
                vocab_cache.empty_catalog(),
                [
                    {
                        "word": "admitting",
                        "stem": "admit",
                        "context": "She admitted it.",
                        "book_key": "book",
                        "book_title": "Book",
                        "authors": "Author",
                        "language": "en",
                        "looked_up_at": "2026-07-10",
                    }
                ],
                sync_id="sync",
            )
            catalog["lexemes"][0]["processing"] = {
                "state": "ready",
                "analysis": {"base_form": "admit", "accepted": True, "importance_score": 7},
                "updated_at": "now",
                "error": "",
            }
            repository = repository_for(workspace)
            repository.save_catalog(catalog)

            vault = workspace / "vault"
            cards = vault / "cards"
            append_cards(
                cards,
                [
                    {
                        "id": "matching",
                        "word": "admit",
                        "stem": "admit",
                        "context": "Different Obsidian context.",
                        "book_title": "Other",
                        "authors": "Other",
                        "processing_status": "processed",
                        "analysis": {"base_form": "admit", "accepted": True, "importance_score": 10},
                    },
                    {
                        "id": "unknown",
                        "word": "unknown",
                        "stem": "unknown",
                        "context": "Only in Obsidian.",
                        "book_title": "Other",
                        "authors": "Other",
                        "processing_status": "processed",
                        "analysis": {"base_form": "unknown", "accepted": True, "importance_score": 9},
                    },
                ],
                workspace / "backups",
                backup_enabled=False,
            )

            result = dispatch(
                "load_obsidian",
                {"vault_path": str(vault), "cards_path": "cards"},
                workspace,
            )

            self.assertEqual(len(result["entries"]), 1)
            stored = result["entries"][0]
            self.assertEqual(stored["processing"]["analysis"]["importance_score"], 7)
            self.assertEqual(len(stored["occurrences"]), 1)
            self.assertEqual(stored["destinations"]["obsidian"]["state"], "synced")

    def test_sync_obsidian_repairs_stale_state_and_excludes_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            catalog = vocab_cache.merge_kindle(
                vocab_cache.empty_catalog(),
                [
                    {
                        "word": "glimpse",
                        "stem": "glimpse",
                        "context": "He caught a glimpse.",
                        "book_key": "book",
                        "book_title": "Book",
                        "authors": "Author",
                        "language": "en",
                        "looked_up_at": "2026-07-10",
                    },
                    {
                        "word": "the",
                        "stem": "the",
                        "context": "The room was empty.",
                        "book_key": "book",
                        "book_title": "Book",
                        "authors": "Author",
                        "language": "en",
                        "looked_up_at": "2026-07-10",
                    },
                ],
                sync_id="sync",
            )
            accepted = next(item for item in catalog["lexemes"] if item["lemma"] == "glimpse")
            accepted["processing"] = {
                "state": "ready",
                "analysis": {"base_form": "glimpse", "accepted": True, "importance_score": 7},
                "updated_at": "now",
                "error": "",
            }
            accepted["destinations"]["obsidian"]["state"] = "synced"
            rejected = next(item for item in catalog["lexemes"] if item["lemma"] == "the")
            rejected["processing"] = {
                "state": "rejected",
                "analysis": {"base_form": "the", "accepted": False, "importance_score": 1},
                "updated_at": "now",
                "error": "",
            }
            repository_for(workspace).save_catalog(catalog)
            vault = workspace / "vault"

            result = dispatch(
                "sync_obsidian",
                {
                    "vault_path": str(vault),
                    "cards_path": "cards",
                    "backup_enabled": False,
                },
                workspace,
            )

            self.assertEqual(result["added"], 1)
            self.assertEqual(len(read_cards(vault / "cards")), 1)
            by_lemma = {item["lemma"]: item for item in result["entries"]}
            self.assertEqual(by_lemma["glimpse"]["destinations"]["obsidian"]["state"], "synced")
            self.assertEqual(
                by_lemma["the"]["destinations"]["obsidian"]["state"],
                "not_applicable",
            )

    def test_sqlite_migration_imports_ready_state_from_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            catalog = vocab_cache.empty_catalog()
            lexeme = {
                "id": "test-admit",
                "lemma": "admit",
                "display_form": "admitting",
                "language": "en",
                "forms": ["admitting", "admit"],
                "occurrences": [
                    {
                        "id": "occ",
                        "source": "kindle",
                        "word": "admitting",
                        "context": "She admitted it.",
                        "book_key": "book",
                        "book_title": "Book",
                        "authors": "Author",
                        "looked_up_at": "2026-07-10",
                    }
                ],
                "freshness": "new",
                "processing": {"state": "pending", "analysis": None, "updated_at": "", "error": ""},
                "sources": {"kindle": True, "obsidian": False, "legacy": False},
                "destinations": {
                    "obsidian": {"state": "not_synced", "reason": "", "last_synced_at": ""},
                    "anki": {"state": "not_exported", "last_exported_at": ""},
                    "quizlet": {"state": "not_exported", "last_exported_at": ""},
                },
                "first_seen_at": "2026-07-10",
                "last_seen_at": "2026-07-10",
                "last_kindle_sync_id": "",
            }
            catalog["lexemes"].append(lexeme)
            vocab_cache.save(workspace, catalog)

            snapshot_path = workspace / ".app-data" / "optimized" / "processed_snapshot.json"
            snapshot = ProcessedSnapshot.load(snapshot_path)
            snapshot.remember_processed(
                "admit",
                {
                    "accepted": True,
                    "importance": 8,
                    "base_form": "admit",
                    "word": "admit",
                    "source_occurrence_count": 1,
                },
            )
            snapshot.save()

            catalog = _load_catalog_with_sources(workspace)
            restored = next(item for item in catalog["lexemes"] if item["lemma"] == "admit")
            self.assertEqual(restored["processing"]["state"], "ready")
            self.assertEqual(restored["processing"]["analysis"]["base_form"], "admit")

            result = dispatch("process_lexemes", {"ids": [restored["id"]]}, workspace)
            processed = next(item for item in result["entries"] if item["lemma"] == "admit")
            self.assertEqual(processed["processing"]["state"], "ready")
            self.assertEqual(result["processed_new"], 0)
            self.assertEqual(result["skipped_existing"], 0)

    def test_sqlite_migration_imports_rejected_state_from_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            catalog = vocab_cache.empty_catalog()
            lexeme = {
                "id": "test-reject",
                "lemma": "reject",
                "display_form": "rejected",
                "language": "en",
                "forms": ["rejected", "reject"],
                "occurrences": [
                    {
                        "id": "occ",
                        "source": "kindle",
                        "word": "rejected",
                        "context": "It was rejected.",
                        "book_key": "book",
                        "book_title": "Book",
                        "authors": "Author",
                        "looked_up_at": "2026-07-10",
                    }
                ],
                "freshness": "new",
                "processing": {"state": "pending", "analysis": None, "updated_at": "", "error": ""},
                "sources": {"kindle": True, "obsidian": False, "legacy": False},
                "destinations": {
                    "obsidian": {"state": "not_synced", "reason": "", "last_synced_at": ""},
                    "anki": {"state": "not_exported", "last_exported_at": ""},
                    "quizlet": {"state": "not_exported", "last_exported_at": ""},
                },
                "first_seen_at": "2026-07-10",
                "last_seen_at": "2026-07-10",
                "last_kindle_sync_id": "",
            }
            catalog["lexemes"].append(lexeme)
            vocab_cache.save(workspace, catalog)

            snapshot_path = workspace / ".app-data" / "optimized" / "processed_snapshot.json"
            snapshot = ProcessedSnapshot.load(snapshot_path)
            snapshot.remember_processed(
                "reject",
                {
                    "accepted": False,
                    "importance": 0,
                    "base_form": "reject",
                    "word": "reject",
                    "source_occurrence_count": 1,
                },
            )
            snapshot.save()

            catalog = _load_catalog_with_sources(workspace)
            restored = next(item for item in catalog["lexemes"] if item["lemma"] == "reject")
            self.assertEqual(restored["processing"]["state"], "rejected")
            self.assertEqual(restored["processing"]["analysis"]["accepted"], False)

    def test_process_lexemes_message_includes_skipped_existing_in_russian(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            catalog = vocab_cache.empty_catalog()
            catalog["lexemes"].append(
                {
                    "id": "test-ready",
                    "lemma": "ready",
                    "display_form": "ready",
                    "language": "en",
                    "forms": ["ready"],
                    "occurrences": [
                        {
                            "id": "occ",
                            "source": "kindle",
                            "word": "ready",
                            "context": "It is ready.",
                            "book_key": "book",
                            "book_title": "Book",
                            "authors": "Author",
                            "looked_up_at": "2026-07-10",
                        }
                    ],
                    "freshness": "known",
                    "processing": {"state": "ready", "analysis": None, "updated_at": "", "error": ""},
                    "sources": {"kindle": True, "obsidian": False, "legacy": False},
                    "destinations": {
                        "obsidian": {"state": "not_synced", "reason": "", "last_synced_at": ""},
                        "anki": {"state": "not_exported", "last_exported_at": ""},
                        "quizlet": {"state": "not_exported", "last_exported_at": ""},
                    },
                    "first_seen_at": "2026-07-10",
                    "last_seen_at": "2026-07-10",
                    "last_kindle_sync_id": "",
                }
            )
            vocab_cache.save(workspace, catalog)

            snapshot_path = workspace / ".app-data" / "optimized" / "processed_snapshot.json"
            snapshot = ProcessedSnapshot.load(snapshot_path)
            snapshot.remember_processed(
                "ready",
                {
                    "accepted": True,
                    "importance": 5,
                    "base_form": "ready",
                    "word": "ready",
                    "source_occurrence_count": 1,
                },
            )
            snapshot.save()

            result = dispatch("process_lexemes", {"ids": ["test-ready"]}, workspace)
            event = result["events"][0]
            self.assertIn("пропущено ранее", event["message"])
            self.assertIn("Обработано:", event["message"])
            self.assertIn("принято:", event["message"])
            self.assertIn("отклонено:", event["message"])

    def test_process_lexemes_rejects_unsupported_language_without_audit_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            catalog = vocab_cache.empty_catalog()
            catalog["lexemes"].append(
                {
                    "id": "test-russian",
                    "lemma": "большой",
                    "display_form": "Большой",
                    "language": "ru",
                    "forms": ["Большой"],
                    "occurrences": [
                        {
                            "id": "occ",
                            "source": "kindle",
                            "word": "Большой",
                            "context": "Большой бюст или огромный бюст?",
                            "book_key": "book",
                            "book_title": "Book",
                            "authors": "Author",
                            "looked_up_at": "2026-07-10",
                        }
                    ],
                    "freshness": "new",
                    "processing": {"state": "pending", "analysis": None, "updated_at": "", "error": ""},
                    "sources": {"kindle": True, "obsidian": False, "legacy": False},
                    "destinations": {
                        "obsidian": {"state": "not_synced", "reason": "", "last_synced_at": ""},
                        "anki": {"state": "not_exported", "last_exported_at": ""},
                        "quizlet": {"state": "not_exported", "last_exported_at": ""},
                    },
                    "first_seen_at": "2026-07-10",
                    "last_seen_at": "2026-07-10",
                    "last_kindle_sync_id": "",
                }
            )
            vocab_cache.save(workspace, catalog)

            migrated = _load_catalog_with_sources(
                workspace, reconcile_kindle=False, reconcile_obsidian=False
            )
            migrated_id = next(
                item["id"] for item in migrated["lexemes"] if item["language"] == "ru"
            )
            result = dispatch("process_lexemes", {"ids": [migrated_id]}, workspace)
            processed = next(item for item in result["entries"] if item["language"] == "ru")

            self.assertEqual(processed["processing"]["state"], "rejected")
            self.assertEqual(processed["processing"]["error"], "")
            self.assertIn("unsupported_language", processed["processing"]["analysis"]["warnings"])
            self.assertEqual(processed["destinations"]["obsidian"]["reason"], "unsupported_language")
            self.assertEqual(result["rejected_new"], 1)

    def test_process_queue_commits_each_completed_lexeme_before_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            catalog = vocab_cache.merge_kindle(
                vocab_cache.empty_catalog(),
                [
                    {
                        "word": "большой",
                        "stem": "большой",
                        "context": "Большой бюст.",
                        "book_key": "book",
                        "book_title": "Book",
                        "authors": "Author",
                        "language": "ru",
                        "looked_up_at": "2026-07-10",
                    },
                    {
                        "word": "glimpse",
                        "stem": "glimpse",
                        "context": "He caught a glimpse.",
                        "book_key": "book",
                        "book_title": "Book",
                        "authors": "Author",
                        "language": "en",
                        "looked_up_at": "2026-07-10",
                    },
                ],
                sync_id="sync",
            )
            for item in catalog["lexemes"]:
                item["first_seen_at"] = "2026-01-01" if item["language"] == "ru" else "2026-01-02"
            repository = repository_for(workspace)
            repository.save_catalog(catalog)

            with patch(
                "kindle_vocab_app.tauri_bridge.analyze_entries_once",
                side_effect=RuntimeError("test failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "test failure"):
                    dispatch("process_queue", {}, workspace)

            persisted = repository.load_catalog()
            by_language = {item["language"]: item for item in persisted["lexemes"]}
            self.assertEqual(by_language["ru"]["processing"]["state"], "rejected")
            self.assertEqual(by_language["en"]["processing"]["state"], "failed")
            self.assertEqual(repository.queue_status()["failed"], 1)


if __name__ == "__main__":
    unittest.main()
