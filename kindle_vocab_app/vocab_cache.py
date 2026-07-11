from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from kindle_vocab_app.logging_config import get_logger


logger = get_logger(__name__)

CACHE_VERSION = 2
CACHE_FILENAME = "vocab_cache.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def cache_path(workspace: Path) -> Path:
    return workspace / ".app-data" / CACHE_FILENAME


def empty_catalog() -> dict[str, Any]:
    return {
        "version": CACHE_VERSION,
        "cached_at": utc_now(),
        "last_kindle_sync_id": "",
        "lexemes": [],
    }


def load(workspace: Path) -> dict[str, Any] | None:
    path = cache_path(workspace)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to read vocabulary catalog path=%s", path)
        return None

    version = int(data.get("version") or 1)
    if version == CACHE_VERSION:
        data["lexemes"] = [_normalize_lexeme(item) for item in data.get("lexemes") or []]
        return data
    if version == 1:
        migrated = migrate_v1(data)
        backup = path.with_suffix(path.suffix + ".v1.bak")
        if not backup.exists():
            shutil.copy2(path, backup)
        save(workspace, migrated)
        logger.info(
            "Migrated vocabulary catalog path=%s backup=%s entries=%d lexemes=%d",
            path,
            backup,
            len(data.get("entries") or []),
            len(migrated["lexemes"]),
        )
        return migrated

    logger.warning("Unsupported vocabulary catalog version path=%s version=%s", path, version)
    return None


def save(workspace: Path, catalog: dict[str, Any]) -> None:
    path = cache_path(workspace)
    payload = {
        "version": CACHE_VERSION,
        "cached_at": utc_now(),
        "last_kindle_sync_id": str(catalog.get("last_kindle_sync_id") or ""),
        "lexemes": [_normalize_lexeme(item) for item in catalog.get("lexemes") or []],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
    logger.info("Saved vocabulary catalog path=%s lexemes=%d", path, len(payload["lexemes"]))


def migrate_v1(data: dict[str, Any]) -> dict[str, Any]:
    catalog = empty_catalog()
    for entry in data.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        _merge_entry(catalog, entry, source="legacy", kindle_sync_id="", mark_new=False)
    return catalog


def merge_kindle(
    catalog: dict[str, Any],
    entries: Iterable[dict[str, Any]],
    *,
    sync_id: str,
    mark_new: bool = True,
) -> dict[str, Any]:
    catalog = _copy_catalog(catalog)
    existing_ids = {str(item.get("id") or "") for item in catalog["lexemes"]}
    if mark_new:
        for lexeme in catalog["lexemes"]:
            if lexeme.get("freshness") == "new":
                lexeme["freshness"] = "known"

    for entry in entries:
        key = lexical_key(entry)
        candidate_id = lexeme_id(str(entry.get("language") or "en"), key)
        is_new_lexeme = candidate_id not in existing_ids
        _merge_entry(
            catalog,
            entry,
            source="kindle",
            kindle_sync_id=sync_id,
            mark_new=mark_new and is_new_lexeme,
        )
        existing_ids.add(candidate_id)

    if mark_new:
        catalog["last_kindle_sync_id"] = sync_id
    return catalog


def merge_obsidian(catalog: dict[str, Any], entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    catalog = _copy_catalog(catalog)
    for entry in entries:
        _merge_entry(catalog, entry, source="obsidian", kindle_sync_id="", mark_new=False)
    return catalog


def lexical_key(entry: dict[str, Any]) -> str:
    analysis = entry.get("analysis") or {}
    value = analysis.get("base_form") or entry.get("lemma") or entry.get("stem") or entry.get("word") or entry.get("id")
    return normalize_lemma(str(value or ""))


def normalize_lemma(value: str) -> str:
    text = value.strip().replace("’", "'").replace("`", "'").casefold()
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,:;!?\"'()[]{}")


def lexeme_id(language: str, key: str) -> str:
    raw = f"{language.casefold()}|{key.casefold()}"
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()


def occurrence_id(entry: dict[str, Any], source: str) -> str:
    raw = "|".join(
        [
            source,
            str(entry.get("word") or ""),
            str(entry.get("context") or ""),
            str(entry.get("book_key") or ""),
            str(entry.get("book_title") or ""),
            str(entry.get("looked_up_at") or ""),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()


def books_from_lexemes(lexemes: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for lexeme in lexemes:
        seen_for_lexeme: set[str] = set()
        for occurrence in lexeme.get("occurrences") or []:
            key = str(occurrence.get("book_key") or occurrence.get("book_title") or "")
            if not key or key in seen_for_lexeme:
                continue
            seen_for_lexeme.add(key)
            counts[key] = counts.get(key, 0) + 1
            title = str(occurrence.get("book_title") or key)
            authors = str(occurrence.get("authors") or "")
            labels[key] = f"{title} · {authors}" if authors else title
    books = [{"label": "Все книги", "key": ""}]
    for key in sorted(counts, key=lambda item: labels[item].casefold()):
        books.append({"label": f"{labels[key]} · {counts[key]}", "key": key})
    return books


def frontend_state(catalog: dict[str, Any], *, source_name: str = "Local library", source_status: str = "") -> dict[str, Any]:
    lexemes = [_normalize_lexeme(item) for item in catalog.get("lexemes") or []]
    return {
        "sourceName": source_name,
        "sourceStatus": source_status,
        "books": books_from_lexemes(lexemes),
        "entries": lexemes,
        "last_kindle_sync_id": str(catalog.get("last_kindle_sync_id") or ""),
    }


def _merge_entry(
    catalog: dict[str, Any],
    entry: dict[str, Any],
    *,
    source: str,
    kindle_sync_id: str,
    mark_new: bool,
) -> None:
    key = lexical_key(entry)
    if not key:
        return
    language = str(entry.get("language") or "en")
    item_id = lexeme_id(language, key)
    by_id = {str(item.get("id") or ""): item for item in catalog["lexemes"]}
    lexeme = by_id.get(item_id)
    if lexeme is None:
        lexeme = next(
            (
                item
                for item in catalog["lexemes"]
                if normalize_lemma(str(item.get("lemma") or "")) == key
                or key in {normalize_lemma(str(form)) for form in item.get("forms") or []}
            ),
            None,
        )
    existing_lexeme = lexeme
    now = utc_now()
    if lexeme is None:
        lexeme = _new_lexeme(entry, item_id, key, source, kindle_sync_id, mark_new, now)
        catalog["lexemes"].append(lexeme)
    else:
        lexeme = _normalize_lexeme(lexeme)
        index = catalog["lexemes"].index(existing_lexeme)
        catalog["lexemes"][index] = lexeme
        lexeme["last_seen_at"] = now
        lexeme["sources"][source] = True
        if source == "kindle" and kindle_sync_id:
            lexeme["last_kindle_sync_id"] = kindle_sync_id

    word = str(entry.get("word") or entry.get("display_form") or key).strip()
    if word and word not in lexeme["forms"]:
        lexeme["forms"].append(word)
    occurrence = _occurrence_from_entry(entry, source)
    if occurrence["id"] not in {item["id"] for item in lexeme["occurrences"]}:
        lexeme["occurrences"].append(occurrence)

    if source == "obsidian":
        lexeme["freshness"] = "known"
        lexeme["sources"]["obsidian"] = True
        lexeme["destinations"]["obsidian"] = {
            "state": "synced",
            "reason": "",
            "last_synced_at": now,
        }
        analysis = entry.get("analysis") or {}
        lexeme["processing"] = {
            "state": "ready",
            "analysis": analysis,
            "updated_at": str(analysis.get("processed_at") or now),
            "error": "",
        }
        lemma = normalize_lemma(str(analysis.get("base_form") or entry.get("stem") or word))
        if lemma:
            lexeme["lemma"] = lemma
    elif source == "legacy":
        _apply_legacy_state(lexeme, entry, now)


def _new_lexeme(
    entry: dict[str, Any],
    item_id: str,
    key: str,
    source: str,
    kindle_sync_id: str,
    mark_new: bool,
    now: str,
) -> dict[str, Any]:
    word = str(entry.get("word") or key).strip()
    return {
        "id": item_id,
        "lemma": key,
        "display_form": word or key,
        "language": str(entry.get("language") or "en"),
        "forms": [word] if word else [],
        "occurrences": [],
        "freshness": "new" if mark_new else "known",
        "processing": {"state": "pending", "analysis": None, "updated_at": "", "error": ""},
        "sources": {"kindle": source == "kindle", "obsidian": source == "obsidian", "legacy": source == "legacy"},
        "destinations": {
            "obsidian": {"state": "not_synced", "reason": "", "last_synced_at": ""},
            "anki": {"state": "not_exported", "last_exported_at": ""},
            "quizlet": {"state": "not_exported", "last_exported_at": ""},
        },
        "first_seen_at": now,
        "last_seen_at": now,
        "last_kindle_sync_id": kindle_sync_id,
    }


def _apply_legacy_state(lexeme: dict[str, Any], entry: dict[str, Any], now: str) -> None:
    status = str(entry.get("processing_status") or "raw")
    state = {
        "raw": "pending",
        "processing": "pending",
        "processed": "ready",
        "rejected": "rejected",
        "failed": "failed",
        "skipped": "ready" if entry.get("analysis") else "pending",
    }.get(status, "pending")
    analysis = entry.get("analysis") if state in {"ready", "rejected"} else None
    current = lexeme.get("processing") or {}
    if current.get("state") not in {"ready", "rejected"} or state in {"ready", "rejected"}:
        lexeme["processing"] = {"state": state, "analysis": analysis, "updated_at": now, "error": ""}


def _occurrence_from_entry(entry: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "id": occurrence_id(entry, source),
        "source": source,
        "word": str(entry.get("word") or entry.get("display_form") or ""),
        "context": str(entry.get("context") or ""),
        "book_key": str(entry.get("book_key") or ""),
        "book_title": str(entry.get("book_title") or ""),
        "authors": str(entry.get("authors") or ""),
        "looked_up_at": str(entry.get("looked_up_at") or ""),
    }


def _normalize_lexeme(item: dict[str, Any]) -> dict[str, Any]:
    item = dict(item)
    item.setdefault("forms", [])
    item.setdefault("occurrences", [])
    item.setdefault("freshness", "known")
    item.setdefault("processing", {"state": "pending", "analysis": None, "updated_at": "", "error": ""})
    item.setdefault("sources", {"kindle": False, "obsidian": False, "legacy": True})
    item.setdefault("destinations", {})
    item["destinations"].setdefault("obsidian", {"state": "not_synced", "reason": "", "last_synced_at": ""})
    item["destinations"].setdefault("anki", {"state": "not_exported", "last_exported_at": ""})
    item["destinations"].setdefault("quizlet", {"state": "not_exported", "last_exported_at": ""})
    item.setdefault("first_seen_at", utc_now())
    item.setdefault("last_seen_at", item["first_seen_at"])
    item.setdefault("last_kindle_sync_id", "")
    return item


def _copy_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(catalog, ensure_ascii=False))


# Compatibility alias used by the bridge while callers migrate to catalog v2.
_build_books = books_from_lexemes
