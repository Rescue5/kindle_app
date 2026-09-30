from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kindle_vocab_app import vocab_cache
from kindle_vocab_app.library_repository import DATABASE_FILENAME, repository_for
from kindle_vocab_app.tauri_bridge import dispatch


def _catalog() -> dict:
    catalog = vocab_cache.merge_kindle(
        vocab_cache.empty_catalog(),
        [
            {
                "word": lemma,
                "stem": lemma,
                "context": f"A real source sentence for {lemma}.",
                "book_key": "book",
                "book_title": "Book",
                "authors": "Author",
                "language": "en",
                "looked_up_at": "2026-07-10",
            }
            for lemma in ("glimpse", "forlorn", "the")
        ],
        sync_id="test",
    )
    for lexeme in catalog["lexemes"]:
        accepted = lexeme["lemma"] != "the"
        lexeme["processing"] = {
            "state": "ready" if accepted else "rejected",
            "analysis": {
                "base_form": lexeme["lemma"],
                "accepted": accepted,
                "importance_score": 7 if accepted else 1,
                "russian_meanings": "настоящий перевод" if lexeme["lemma"] == "glimpse" else "",
            },
            "updated_at": "2026-07-10T00:00:00+00:00",
            "error": "",
        }
    return catalog


class ReviewTests(unittest.TestCase):
    def test_only_accepted_words_are_due_without_fabricated_meanings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = repository_for(Path(temporary))
            repository.save_catalog(_catalog())
            queue = repository.load_review(limit=1)

            self.assertEqual(queue["due_count"], 2)
            self.assertEqual(queue["total_count"], 2)
            self.assertEqual(len(queue["cards"]), 1)
            all_cards = repository.load_review()["cards"]
            self.assertEqual({card["lemma"] for card in all_cards}, {"glimpse", "forlorn"})
            forlorn = next(card for card in all_cards if card["lemma"] == "forlorn")
            self.assertEqual(forlorn["analysis"]["russian_meanings"], "")
            self.assertEqual(forlorn["occurrences"][0]["book_title"], "Book")

    def test_ratings_schedule_and_survive_catalog_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            repository = repository_for(workspace)
            repository.save_catalog(_catalog())
            card = repository.load_review()["cards"][0]
            lexeme_id = card["lexeme_id"]
            start = datetime(2026, 9, 29, 10, tzinfo=timezone.utc)

            rated = repository.rate_review(lexeme_id, "again", now=start)
            self.assertEqual(rated["card"]["review"]["last_rating"], "again")
            self.assertEqual(rated["card"]["review"]["repetitions"], 0)
            self.assertEqual(
                datetime.fromisoformat(rated["card"]["review"]["due_at"]),
                start + timedelta(minutes=10),
            )
            self.assertEqual(rated["due_count"], 1)
            with self.assertRaisesRegex(ValueError, "not due"):
                repository.rate_review(lexeme_id, "good", now=start)

            repository.save_catalog(repository.load_catalog())
            reopened = repository_for(workspace)
            self.assertEqual(reopened.load_review(now=start)["due_count"], 1)
            hard = reopened.rate_review(lexeme_id, "hard", now=start + timedelta(minutes=10))
            self.assertEqual(hard["card"]["review"]["interval_days"], 1.0)
            self.assertEqual(hard["card"]["review"]["repetitions"], 1)
            good = reopened.rate_review(lexeme_id, "good", now=start + timedelta(days=1, minutes=10))
            self.assertEqual(good["card"]["review"]["interval_days"], 3.0)
            self.assertEqual(good["card"]["review"]["repetitions"], 2)

    def test_bridge_and_version_one_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            repository = repository_for(workspace)
            repository.save_catalog(_catalog())
            database = workspace / ".app-data" / DATABASE_FILENAME
            with sqlite3.connect(database) as connection:
                connection.execute("DROP TABLE review_cards")
                connection.execute("DELETE FROM schema_migrations")
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (1, 'old')"
                )
            queue = dispatch("load_review", {}, workspace)
            self.assertEqual(queue["due_count"], 2)
            result = dispatch(
                "rate_review",
                {"lexeme_id": queue["cards"][0]["lexeme_id"], "rating": "good"},
                workspace,
            )
            self.assertEqual(result["due_count"], 1)
            with sqlite3.connect(database) as connection:
                self.assertEqual(
                    connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],
                    2,
                )

    def test_invalid_rating_and_rejected_card_do_not_create_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            repository = repository_for(workspace)
            repository.save_catalog(_catalog())
            rejected_id = next(
                item["id"] for item in repository.load_catalog()["lexemes"]
                if item["lemma"] == "the"
            )
            with self.assertRaises(ValueError):
                repository.rate_review(rejected_id, "good")
            with self.assertRaises(ValueError):
                repository.rate_review("missing", "good")
            with self.assertRaises(ValueError):
                repository.rate_review(rejected_id, "invented")
            with repository.connect() as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM review_cards").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
