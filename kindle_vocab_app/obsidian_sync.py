from __future__ import annotations

import hashlib
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kindle_vocab_app.logging_config import get_logger


logger = get_logger(__name__)

_PRIORITY_FILES: dict[int, str] = {
    10: "01 - Priority 10.md",
    9: "02 - Priority 9.md",
    8: "03 - Priority 8.md",
    7: "04 - Priority 7.md",
    6: "05 - Priority 6.md",
    5: "06 - Priority 5.md",
    4: "07 - Priority 4.md",
    3: "08 - Priority 3.md",
}

_FILE_BY_PRIORITY = {score: name for score, name in _PRIORITY_FILES.items()}

_CARD_SEPARATOR = "\n---\n"

_SOURCE_RE = re.compile(r"\*(.*?)\*\s*[\u2014\u2013-]\s*(.*)")


def read_cards(cards_dir: Path) -> list[dict[str, Any]]:
    """Parse Obsidian SR cards into frontend-shaped vocabulary entries."""
    entries: list[dict[str, Any]] = []
    if not cards_dir.exists():
        logger.info("Obsidian cards directory does not exist path=%s", cards_dir)
        return entries

    for path in sorted(cards_dir.glob("* - Priority *.md")):
        priority = _priority_from_filename(path.name)
        if priority is None:
            continue
        text = path.read_text(encoding="utf-8")
        body = _strip_frontmatter(text)
        for card in body.split("---"):
            parsed = _parse_card(card)
            if parsed is None:
                continue
            entry = _entry_from_parsed(parsed, priority)
            entries.append(entry)

    logger.info("Read obsidian cards path=%s entries=%d", cards_dir, len(entries))
    return entries


def append_cards(
    cards_dir: Path,
    entries: list[dict[str, Any]],
    backups_dir: Path,
    backup_enabled: bool = True,
) -> dict[str, Any]:
    """Append processed entries to Obsidian SR priority files."""
    backup_path = backup_cards(cards_dir, backups_dir) if backup_enabled else None

    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped = 0

    for entry in entries:
        status = entry.get("processing_status")
        analysis = entry.get("analysis") or {}
        if status != "processed" or analysis.get("accepted") is False:
            skipped += 1
            continue
        score = analysis.get("importance_score")
        if score not in _FILE_BY_PRIORITY:
            skipped += 1
            continue
        by_file[_FILE_BY_PRIORITY[score]].append(entry)

    added = 0
    files_touched: set[str] = set()

    for filename in sorted(by_file.keys()):
        file_path = cards_dir / filename
        is_new = not file_path.exists()
        existing_keys = _existing_card_keys(file_path)
        new_cards: list[str] = []

        for entry in by_file[filename]:
            word = str(entry.get("word") or "").strip()
            context = str(entry.get("context") or "").strip()
            key = f"{word}|{context}".casefold()
            if key in existing_keys:
                skipped += 1
                continue
            existing_keys.add(key)
            new_cards.append(_render_card(entry))
            added += 1

        if not new_cards:
            continue

        _ensure_file(file_path, filename)
        rendered = _CARD_SEPARATOR.join(new_cards)
        with file_path.open("a", encoding="utf-8", newline="\n") as file:
            if not is_new:
                file.write(_CARD_SEPARATOR)
            file.write(rendered)
            file.write("\n")
        files_touched.add(filename)

    result = {
        "added": added,
        "skipped": skipped,
        "files": sorted(files_touched),
        "backup_path": str(backup_path) if backup_path else "",
    }
    logger.info("Appended obsidian cards result=%s", result)
    return result


def backup_cards(cards_dir: Path, backups_dir: Path) -> Path:
    """Copy the entire cards directory into a timestamped backup folder."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = backups_dir / timestamp / cards_dir.name
    if cards_dir.exists():
        shutil.copytree(cards_dir, backup_path)
    else:
        backup_path.mkdir(parents=True, exist_ok=True)
    logger.info("Backed up obsidian cards src=%s backup=%s", cards_dir, backup_path)
    return backup_path


def _normalize_base(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _priority_from_filename(name: str) -> int | None:
    match = re.match(r"\d{2}\s+-\s+Priority\s+(\d+)\.md$", name, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text
    return parts[2].lstrip("\n")


def _extract_quote_translation(text: str) -> str:
    """Return the contents of the > [!quote]- Перевод контекста block."""
    in_block = False
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("> [!quote]- Перевод контекста"):
            in_block = True
            continue
        if not in_block:
            continue
        if stripped.startswith("> [!"):
            break
        if stripped.startswith("> "):
            lines.append(stripped[2:])
        elif stripped.startswith(">"):
            lines.append(stripped[1:].strip())
        else:
            break
    return "\n".join(lines).strip()


def _extract_meanings_and_examples(text: str) -> tuple[str, str, str]:
    """Parse the > [!example]- Примеры значений block.

    Returns (russian_meanings, generated_context_en, generated_context_ru).
    """
    in_block = False
    block_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("> [!example]- Примеры значений"):
            in_block = True
            continue
        if not in_block:
            continue
        if stripped.startswith("> [!"):
            break
        if stripped.startswith("> "):
            block_lines.append(stripped[2:])
        elif stripped.startswith(">"):
            block_lines.append(stripped[1:].strip())
        else:
            break

    meanings: list[str] = []
    generated_context_en = ""
    generated_context_ru = ""
    for line in block_lines:
        stripped = line.strip()
        if not stripped:
            continue
        meaning_match = re.match(r"\*\*\d+\.\*\*\s+(.*)", stripped)
        if not meaning_match:
            meaning_match = re.match(r"\*\*\d+\.\s*(.*?)\*\*$", stripped)
        if meaning_match:
            meanings.append(meaning_match.group(1).strip().strip("*"))
            continue
        if not generated_context_en and not stripped.startswith("*"):
            generated_context_en = stripped
            continue
        if generated_context_en and stripped.startswith("*") and not generated_context_ru:
            generated_context_ru = stripped.strip("*").strip()
            continue

    return "\n".join(meanings), generated_context_en, generated_context_ru


def _parse_card(card_text: str) -> dict[str, Any] | None:
    card_text = card_text.strip()
    if not card_text:
        return None

    if "\n?\n" not in card_text:
        return None

    question, answer = card_text.split("\n?\n", 1)
    question = question.strip()
    answer = answer.strip()

    word = _extract_bold_word(question)
    context = _extract_context(question)
    book_title, authors = _extract_source(answer)
    base_form = _extract_base_form(answer, word)

    generated_context_ru_quote = _extract_quote_translation(answer)
    russian_meanings, generated_context_en, generated_context_ru_example = (
        _extract_meanings_and_examples(answer)
    )
    generated_context_ru = generated_context_ru_quote or generated_context_ru_example

    is_pending = "<!-- NN_PENDING -->" in answer
    if not is_pending and russian_meanings:
        translation_status = "llm_enriched"
    else:
        translation_status = "offline_only"

    return {
        "word": word,
        "base_form": base_form,
        "context": context,
        "book_title": book_title,
        "authors": authors,
        "translation_status": translation_status,
        "russian_meanings": russian_meanings,
        "generated_context_en": generated_context_en,
        "generated_context_ru": generated_context_ru,
    }


def _extract_bold_word(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("**") and line.endswith("**"):
            return line[2:-2].strip()
    return ""


def _extract_base_form(answer: str, word: str) -> str:
    """Try to extract the English lemma from the first bold answer segment."""
    match = re.search(r"\*\*(.*?)\*\*", answer.strip())
    if not match:
        return word
    content = match.group(1).strip()
    if "<!-- NN_PENDING -->" in content:
        return word
    for separator in ("\u2014", "\u2013", "-"):
        if separator in content:
            candidate = content.split(separator, 1)[0].strip()
            if candidate and re.fullmatch(r"[A-Za-z][A-Za-z\s\-'\.]*", candidate):
                return candidate
    if re.fullmatch(r"[A-Za-z][A-Za-z\s\-'\.]*", content):
        return content
    return word


def _extract_context(text: str) -> str:
    lines: list[str] = []
    in_context = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("> [!example]- Контекст"):
            in_context = True
            continue
        if not in_context:
            continue
        if stripped.startswith("> "):
            lines.append(stripped[2:])
        elif stripped.startswith(">"):
            lines.append(stripped[1:].strip())
        else:
            break
    return " ".join(lines).strip()


def _extract_source(text: str) -> tuple[str, str]:
    in_source = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("> [!info]- Источник"):
            in_source = True
            continue
        if not in_source:
            continue
        content = stripped[2:].strip() if stripped.startswith("> ") else stripped
        match = _SOURCE_RE.search(content)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        if stripped.startswith("> "):
            continue
        break
    return "", ""


def _entry_from_parsed(parsed: dict[str, Any], priority: int) -> dict[str, Any]:
    word = str(parsed.get("word") or "")
    context = str(parsed.get("context") or "")
    book_title = str(parsed.get("book_title") or "")
    authors = str(parsed.get("authors") or "")
    looked_up_at = ""

    base_form = str(parsed.get("base_form") or word)

    base_payload = {
        "word": word,
        "stem": base_form,
        "context": context,
        "book_key": book_title,
        "book_title": book_title,
        "authors": authors,
        "language": "en",
        "looked_up_at": looked_up_at,
    }
    entry_id = hashlib.sha1(
        "|".join(
            str(base_payload.get(key) or "")
            for key in [
                "word",
                "stem",
                "context",
                "book_key",
                "book_title",
                "looked_up_at",
            ]
        ).encode("utf-8", errors="replace")
    ).hexdigest()

    return {
        "id": entry_id,
        **base_payload,
        "processing_status": "processed",
        "export_status": "none",
        "analysis": {
            "base_form": _normalize_base(base_form),
            "accepted": True,
            "importance_score": priority,
            "importance_note": f"Obsidian priority {priority}",
            "translation_status": parsed.get("translation_status") or "offline_only",
            "russian_meanings": parsed.get("russian_meanings") or "",
            "generated_context_en": parsed.get("generated_context_en") or "",
            "generated_context_ru": parsed.get("generated_context_ru") or "",
        },
    }


def _existing_card_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.exists():
        return keys
    text = path.read_text(encoding="utf-8")
    body = _strip_frontmatter(text)
    for card in body.split("---"):
        parsed = _parse_card(card)
        if parsed is None:
            continue
        word = str(parsed.get("word") or "").strip()
        context = str(parsed.get("context") or "").strip()
        keys.add(f"{word}|{context}".casefold())
    return keys


def _ensure_file(path: Path, filename: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    priority = _priority_from_filename(filename) or 10
    prefix = filename.split(" - ")[0]
    tag_number = f"{prefix}-priority-{priority}"
    frontmatter = f"""---
tags:
  - flashcards/book-vocab
  - flashcards/book-vocab/{tag_number}
  - vocab/priority/{priority}
view-count: 1
---
"""
    path.write_text(frontmatter, encoding="utf-8")


def _render_card(entry: dict[str, Any]) -> str:
    word = str(entry.get("word") or "").strip()
    context = str(entry.get("context") or "").strip()
    book_title = str(entry.get("book_title") or "").strip()
    authors = str(entry.get("authors") or "").strip()
    analysis = entry.get("analysis") or {}

    translation_status = analysis.get("translation_status") or "offline_only"
    russian_meanings = str(analysis.get("russian_meanings") or "").strip()
    generated_context_en = str(analysis.get("generated_context_en") or "").strip()
    generated_context_ru = str(analysis.get("generated_context_ru") or "").strip()

    is_enriched = (
        translation_status == "llm_enriched"
        and russian_meanings
        and generated_context_en
        and generated_context_ru
    )

    indented_context = _indent_block(context)

    if is_enriched:
        answer_heading = russian_meanings.splitlines()[0].strip()
        examples = _indent_block(
            _format_examples(
                russian_meanings, generated_context_en, generated_context_ru
            )
        )
        indented_context_ru = _indent_block(generated_context_ru)
        card = f"""**{word}**
> [!example]- Контекст
> {indented_context}
?
**{answer_heading}**
> [!quote]- Перевод контекста
> {indented_context_ru}
>
> [!example]- Примеры значений
> {examples}
> [!info]- Источник
> *{book_title}* — {authors}"""
    else:
        card = f"""**{word}**
> [!example]- Контекст
> {indented_context}
?
**<!-- NN_PENDING -->**
> [!quote]- Перевод контекста
>
>
> [!example]- Примеры значений
>
>
> [!info]- Источник
> *{book_title}* — {authors}"""

    return card


def _indent_block(text: str) -> str:
    if not text:
        return ""
    return "\n> ".join(text.splitlines())


def _format_examples(
    russian_meanings: str,
    generated_context_en: str,
    generated_context_ru: str,
) -> str:
    meaning_lines = [line.strip() for line in russian_meanings.splitlines() if line.strip()]
    parts: list[str] = []
    for index, meaning in enumerate(meaning_lines, 1):
        parts.append(f"**{index}.** {meaning}")
    if generated_context_en:
        parts.append(generated_context_en)
    if generated_context_ru:
        parts.append(f"*{generated_context_ru}*")
    if parts:
        return "\n\n".join(parts) + "\n"
    return "\n\n"
