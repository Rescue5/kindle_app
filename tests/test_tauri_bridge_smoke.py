from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kindle_vocab_app import vocab_cache
from kindle_vocab_app.processing_state import ProcessedSnapshot
from kindle_vocab_app.tauri_bridge import _analysis_by_lemma, dispatch


class BridgeSmokeTests(unittest.TestCase):
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

    def test_process_lexemes_recovers_snapshot_using_normalized_candidate_key(self) -> None:
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

            result = dispatch("process_lexemes", {"ids": ["test-admit"]}, workspace)
            self.assertIn("entries", result)
            processed = next(
                (item for item in result["entries"] if item["id"] == "test-admit"), None
            )
            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed["processing"]["state"], "ready")
            self.assertEqual(processed["processing"]["analysis"]["base_form"], "admit")
            self.assertEqual(result["processed_new"], 0)
            self.assertEqual(result["skipped_existing"], 1)

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

            result = dispatch("process_lexemes", {"ids": ["test-russian"]}, workspace)
            processed = next(item for item in result["entries"] if item["id"] == "test-russian")

            self.assertEqual(processed["processing"]["state"], "rejected")
            self.assertEqual(processed["processing"]["error"], "")
            self.assertIn("unsupported_language", processed["processing"]["analysis"]["warnings"])
            self.assertEqual(processed["destinations"]["obsidian"]["reason"], "unsupported_language")
            self.assertEqual(result["rejected_new"], 1)


if __name__ == "__main__":
    unittest.main()
