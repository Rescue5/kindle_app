from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kindle_vocab_app.obsidian_sync import _parse_card, append_cards


class ObsidianParserTests(unittest.TestCase):
    def test_card_with_question_mark_in_context(self) -> None:
        card = """**perplexed**
> [!example]- Контекст
> Are you sure? she asked, perplexed.
?
**<!-- NN_PENDING -->**
> [!quote]- Перевод контекста
>
>
> [!example]- Примеры значений
>
>
> [!info]- Источник
> *The Test Book* — Demo Author"""
        parsed = _parse_card(card)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["word"], "perplexed")
        self.assertEqual(parsed["context"], "Are you sure? she asked, perplexed.")
        self.assertEqual(parsed["translation_status"], "offline_only")

    def test_enriched_card_preserves_fields(self) -> None:
        card = """**admit**
> [!example]- Контекст
> She knew the answer but shied from admitting it.
?
**admit — признавать; допускать; позволять**
> [!quote]- Перевод контекста
> Она знала ответ, но не решалась признать это.
>
> [!example]- Примеры значений
> **1. признавать**
> He avoided admitting that he was wrong.
> *Он избегал признаваться, что был неправ.*
>
> **2. допускать**
> The rule admits several possible interpretations.
> *Правило допускает несколько возможных толкований.*
>
> [!info]- Источник
> *The Test Book* — Demo Author"""
        parsed = _parse_card(card)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["base_form"], "admit")
        self.assertEqual(parsed["translation_status"], "llm_enriched")
        self.assertEqual(parsed["russian_meanings"], "признавать\nдопускать")
        self.assertEqual(parsed["generated_context_ru"], "Она знала ответ, но не решалась признать это.")

    def test_append_returns_per_item_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entries = [
                {
                    "id": "ready",
                    "word": "glimpse",
                    "stem": "glimpse",
                    "context": "He caught a glimpse.",
                    "book_title": "Book",
                    "authors": "Author",
                    "processing_status": "processed",
                    "analysis": {"base_form": "glimpse", "accepted": True, "importance_score": 7},
                },
                {
                    "id": "pending",
                    "word": "dread",
                    "stem": "dread",
                    "context": "A quiet dread settled.",
                    "processing_status": "pending",
                    "analysis": None,
                },
            ]
            result = append_cards(root / "cards", entries, root / "backups", backup_enabled=False)
            outcomes = {item["id"]: item["outcome"] for item in result["items"]}
            self.assertEqual(outcomes, {"ready": "added", "pending": "blocked"})


if __name__ == "__main__":
    unittest.main()
