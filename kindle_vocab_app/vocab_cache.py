from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kindle_vocab_app.logging_config import get_logger


logger = get_logger(__name__)

CACHE_VERSION = 1
CACHE_FILENAME = "vocab_cache.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cache_path(workspace: Path) -> Path:
    return workspace / ".app-data" / CACHE_FILENAME


def load(workspace: Path) -> dict[str, Any] | None:
    """Load the cached vocabulary state if it exists and is valid."""
    path = cache_path(workspace)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to read vocab cache path=%s", path)
        return None
    if data.get("version") != CACHE_VERSION:
        logger.warning(
            "Vocab cache version mismatch path=%s version=%s expected=%s",
            path,
            data.get("version"),
            CACHE_VERSION,
        )
        return None
    return data


def save(workspace: Path, state: dict[str, Any]) -> None:
    """Persist the vocabulary state to disk atomically."""
    path = cache_path(workspace)
    payload = {
        "version": CACHE_VERSION,
        "cached_at": utc_now(),
        "sourceName": state.get("sourceName", ""),
        "sourceStatus": state.get("sourceStatus", ""),
        "books": state.get("books", []),
        "entries": state.get("entries", []),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
    logger.info(
        "Saved vocab cache path=%s entries=%d books=%d",
        path,
        len(payload["entries"]),
        len(payload["books"]),
    )


def _normalize_base(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _base_key(entry: dict[str, Any]) -> str:
    analysis = entry.get("analysis") or {}
    candidate = str(analysis.get("base_form") or "").strip()
    if not candidate:
        candidate = str(entry.get("stem") or "").strip()
    if not candidate:
        candidate = str(entry.get("word") or "").strip()
    if not candidate:
        candidate = str(entry.get("id") or "").strip()
    return _normalize_base(candidate)


def merge(cached: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    """Combine fresh Kindle data with cached state, preserving processing progress."""
    cached_entries = list(cached.get("entries") or [])
    fresh_entries = list(fresh.get("entries") or [])

    entry_by_id: dict[str, dict[str, Any]] = {
        entry["id"]: entry for entry in cached_entries if entry.get("id")
    }
    seen_base = {_base_key(entry) for entry in entry_by_id.values()}

    for entry in fresh_entries:
        entry_id = entry.get("id")
        if not entry_id:
            continue
        if entry_id in entry_by_id:
            old = entry_by_id[entry_id]
            entry["processing_status"] = old.get(
                "processing_status", entry.get("processing_status", "raw")
            )
            entry["analysis"] = old.get("analysis", entry.get("analysis"))
            entry["export_status"] = old.get(
                "export_status", entry.get("export_status", "none")
            )
            entry_by_id[entry_id] = entry
            continue

        base = _base_key(entry)
        if base in seen_base:
            continue

        entry_by_id[entry_id] = entry
        seen_base.add(base)

    merged_entries = list(entry_by_id.values())
    books = _build_books(merged_entries)

    return {
        "sourceName": fresh.get("sourceName", cached.get("sourceName", "")),
        "sourceStatus": fresh.get("sourceStatus", cached.get("sourceStatus", "")),
        "books": books,
        "entries": merged_entries,
    }


def _build_books(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Rebuild the book list from entries with accurate counts."""
    books: list[dict[str, str]] = [{"label": "Все книги", "key": ""}]
    counts: dict[tuple[str, str], int] = {}
    titles: dict[tuple[str, str], str] = {}

    for entry in entries:
        key = str(entry.get("book_key") or "")
        title = str(entry.get("book_title") or "Unknown book")
        authors = str(entry.get("authors") or "")
        book_key = (key, authors)
        counts[book_key] = counts.get(book_key, 0) + 1
        titles[book_key] = title

    def sort_key(item: tuple[tuple[str, str], int]) -> tuple[str, str]:
        (key, authors), _ = item
        title = titles.get((key, authors), "Unknown book")
        return (title.lower(), authors.lower())

    for (key, authors), count in sorted(counts.items(), key=sort_key):
        label = titles.get((key, authors), "Unknown book")
        if authors:
            label += f" · {authors}"
        label += f" · {count}"
        books.append({"label": label, "key": key})

    return books
