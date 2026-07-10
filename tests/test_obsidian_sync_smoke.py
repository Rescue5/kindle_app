"""Smoke test for Obsidian card parsing."""

from pathlib import Path
import sys

# Allow running the test directly from the repository root.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kindle_vocab_app.obsidian_sync import _parse_card


def test_card_with_question_mark_in_context() -> None:
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
    assert parsed is not None
    assert parsed["word"] == "perplexed"
    assert parsed["context"] == "Are you sure? she asked, perplexed."
    assert parsed["book_title"] == "The Test Book"
    assert parsed["authors"] == "Demo Author"
    assert parsed["translation_status"] == "offline_only"


def test_enriched_card_preserves_fields() -> None:
    card = """**perplexed**
> [!example]- Контекст
> Are you sure? she asked, perplexed.
?
**смущённый; озадаченный**
> [!quote]- Перевод контекста
> Вы уверены? — спросила она, озадаченная.
>
> [!example]- Примеры значений
> **1.** смущённый
> **2.** озадаченный
> She looked perplexed by the unexpected question.
*Она выглядела озадаченной неожиданным вопросом.*
> [!info]- Источник
> *The Test Book* — Demo Author"""

    parsed = _parse_card(card)
    assert parsed is not None
    assert parsed["word"] == "perplexed"
    assert parsed["context"] == "Are you sure? she asked, perplexed."
    assert parsed["translation_status"] == "llm_enriched"
    assert parsed["russian_meanings"] == "смущённый\nозадаченный"
    assert parsed["generated_context_en"] == "She looked perplexed by the unexpected question."
    assert parsed["generated_context_ru"] == "Вы уверены? — спросила она, озадаченная."


def test_vault_meaning_format() -> None:
    """Cards in the vault use `**1. meaning**` (meaning inside bold)."""
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
> **3. позволять**
> The guard stopped admitting visitors after midnight.
> *Охрана перестала впускать посетителей после полуночи.*
>
> [!info]- Источник
> *The Test Book* — Demo Author"""

    parsed = _parse_card(card)
    assert parsed is not None
    assert parsed["translation_status"] == "llm_enriched"
    assert parsed["russian_meanings"] == "признавать\nдопускать\nпозволять"
    assert parsed["generated_context_en"] == "He avoided admitting that he was wrong."
    assert parsed["generated_context_ru"] == "Она знала ответ, но не решалась признать это."


if __name__ == "__main__":
    test_card_with_question_mark_in_context()
    test_enriched_card_preserves_fields()
    test_vault_meaning_format()
    print("Obsidian parser smoke tests passed.")
