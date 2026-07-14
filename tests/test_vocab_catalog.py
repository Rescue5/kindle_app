from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from kindle_vocab_app import vocab_cache


def kindle_entry(context: str = "She admitted it.") -> dict[str, object]:
    return {
        "id": "occurrence",
        "word": "admitting",
        "stem": "admit",
        "context": context,
        "book_key": "book",
        "book_title": "Book",
        "authors": "Author",
        "language": "en",
        "looked_up_at": "2026-07-10",
    }


class VocabularyCatalogTests(unittest.TestCase):
    def test_new_lemma_becomes_known_on_next_successful_sync(self) -> None:
        catalog = vocab_cache.merge_kindle(vocab_cache.empty_catalog(), [kindle_entry()], sync_id="one")
        self.assertEqual(catalog["lexemes"][0]["freshness"], "new")
        catalog = vocab_cache.merge_kindle(catalog, [kindle_entry()], sync_id="two")
        self.assertEqual(catalog["lexemes"][0]["freshness"], "known")

    def test_repeated_lemma_keeps_processing_and_adds_context(self) -> None:
        catalog = vocab_cache.merge_kindle(vocab_cache.empty_catalog(), [kindle_entry()], sync_id="one")
        lexeme = catalog["lexemes"][0]
        lexeme["processing"] = {
            "state": "ready",
            "analysis": {"base_form": "admit", "accepted": True, "importance_score": 8},
            "updated_at": "now",
            "error": "",
        }
        catalog = vocab_cache.merge_kindle(catalog, [kindle_entry("He avoided admitting defeat.")], sync_id="two")
        self.assertEqual(len(catalog["lexemes"]), 1)
        self.assertEqual(len(catalog["lexemes"][0]["occurrences"]), 2)
        self.assertEqual(catalog["lexemes"][0]["processing"]["state"], "ready")

    def test_relemmatized_record_does_not_duplicate_on_future_sync(self) -> None:
        initial = {**kindle_entry(), "stem": "admitting"}
        catalog = vocab_cache.merge_kindle(vocab_cache.empty_catalog(), [initial], sync_id="one")
        catalog["lexemes"][0]["lemma"] = "admit"
        catalog["lexemes"][0]["forms"].append("admit")
        catalog = vocab_cache.merge_kindle(catalog, [kindle_entry("A later lookup")], sync_id="two")
        self.assertEqual(len(catalog["lexemes"]), 1)
        self.assertEqual(len(catalog["lexemes"][0]["occurrences"]), 2)

    def test_v1_migration_is_grouped_and_backed_up(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            app_data = workspace / ".app-data"
            app_data.mkdir()
            payload = {
                "version": 1,
                "entries": [kindle_entry(), kindle_entry("Another context")],
            }
            path = app_data / vocab_cache.CACHE_FILENAME
            path.write_text(json.dumps(payload), encoding="utf-8")
            catalog = vocab_cache.load(workspace)
            self.assertIsNotNone(catalog)
            assert catalog is not None
            self.assertEqual(catalog["version"], 2)
            self.assertEqual(len(catalog["lexemes"]), 1)
            self.assertEqual(len(catalog["lexemes"][0]["occurrences"]), 2)
            self.assertTrue(path.with_suffix(path.suffix + ".v1.bak").exists())


if __name__ == "__main__":
    unittest.main()
