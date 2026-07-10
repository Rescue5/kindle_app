from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import sys
from pathlib import Path
from typing import Any

from kindle_vocab_app import obsidian_sync, settings, vocab_cache
from kindle_vocab_app.kindle_db import fetch_entries, list_books, validate_vocab_db
from kindle_vocab_app.kindle_device import find_kindle_source
from kindle_vocab_app.logging_config import configure_logging, get_logger
from kindle_vocab_app.tsv_schema import OPTIMIZED_TSV_HEADER
from kindle_vocab_app.vocab_cache import _build_books
from kindle_vocab_app.vocab_optimizer import optimize_entries


logger = get_logger(__name__)


def main() -> int:
    _configure_stdio()
    workspace = _workspace_root()
    configure_logging(workspace / ".app-data" / "tauri-logs", console=True)
    try:
        request_body = (sys.stdin.read() or "{}").lstrip("\ufeff")
        request = json.loads(request_body)
        action = str(request.get("action") or "")
        payload = dict(request.get("payload") or {})
        logger.info("Tauri bridge request action=%s payload_keys=%s", action, sorted(payload))
        result = dispatch(action, payload, workspace)
        _write_response({"ok": True, "result": result})
        return 0
    except Exception as exc:
        logger.exception("Tauri bridge request failed")
        _write_response({"ok": False, "error": str(exc)})
        return 1


def dispatch(action: str, payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    if action in {"scan", "load_demo"}:
        if action == "load_demo":
            return demo_state()
        source = find_kindle_source()
        if source is None:
            cached = vocab_cache.load(workspace)
            if cached is not None:
                return cached
            return missing_kindle_state()
        cache_dir = workspace / ".app-data" / "cache"
        db_path = source.copy_to_cache(cache_dir)
        validate_vocab_db(db_path)
        fresh_state = load_database_state(db_path, source.label)
        cached = vocab_cache.load(workspace)
        if cached is not None:
            merged_state = vocab_cache.merge(cached, fresh_state)
        else:
            merged_state = fresh_state
        vocab_cache.save(workspace, merged_state)
        return merged_state

    if action == "load_cached":
        cached = vocab_cache.load(workspace)
        if cached is not None:
            return cached
        return demo_state()

    if action == "export":
        entries = list(payload.get("entries") or [])
        export_format = str(payload.get("format") or "anki")
        output = workspace / ".app-data" / f"kindle-{export_format}.tsv"
        exported = export_frontend_entries(entries, output, export_format, workspace)
        return {"path": str(output), "exported": exported}

    if action == "optimize":
        entries = list(payload.get("entries") or [])
        output_dir = workspace / ".app-data" / "optimized"
        result = optimize_entries(entries, output_dir, output_dir / "processed_snapshot.json")
        return {
            "processed_new": result.processed_new,
            "accepted_new": result.accepted_new,
            "skipped_existing": result.skipped_existing,
            "rejected_new": result.rejected_new,
            "tsv_path": str(result.tsv_path),
            "entry_updates": _entry_updates_from_analysis(result.analysis_dir, entries, str(result.tsv_path)),
            "events": [
                {
                    "phase": "answered",
                    "title": "Offline optimizer",
                    "message": f"Processed {result.processed_new}; accepted {result.accepted_new}; rejected {result.rejected_new}; skipped {result.skipped_existing}.",
                    "meta": "Python",
                }
            ],
        }

    if action == "load_settings":
        app_settings = settings.load(workspace)
        return settings.to_dict(app_settings)

    if action == "save_cache":
        vocab_cache.save(workspace, dict(payload.get("state") or {}))
        return {"saved": True}

    if action == "save_settings":
        app_settings = settings.from_dict(payload.get("settings") or {})
        settings.save(workspace, app_settings)
        return {"saved": True}

    if action == "load_obsidian":
        vault_path = str(payload.get("vault_path") or "")
        cards_path = str(payload.get("cards_path") or "")
        if not vault_path or not cards_path:
            raise ValueError("vault_path and cards_path are required")
        cards_dir = Path(vault_path) / cards_path
        entries = obsidian_sync.read_cards(cards_dir)
        return {
            "sourceName": "Obsidian",
            "sourceStatus": f"Загружено {len(entries)} карточек",
            "books": _build_books(entries),
            "entries": entries,
        }

    if action == "sync_obsidian":
        vault_path = str(payload.get("vault_path") or "")
        cards_path = str(payload.get("cards_path") or "")
        entries = list(payload.get("entries") or [])
        backup_enabled = bool(payload.get("backup_enabled", True))
        if not vault_path or not cards_path:
            raise ValueError("vault_path and cards_path are required")
        cards_dir = Path(vault_path) / cards_path
        backups_dir = workspace / ".app-data" / "obsidian-backups"
        return obsidian_sync.append_cards(
            cards_dir, entries, backups_dir, backup_enabled=backup_enabled
        )

    raise ValueError(f"Unsupported bridge action: {action}")


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _write_response(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    sys.stdout.write(text)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _workspace_root() -> Path:
    env_root = os.environ.get("KINDLE_CARDS_WORKSPACE")
    if env_root:
        return Path(env_root).resolve()
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "package.json").exists():
            return candidate
    return current


def missing_kindle_state() -> dict[str, Any]:
    return demo_state(
        source_name="Kindle не найден",
        source_status="Подключите Kindle по USB. Пока показаны демонстрационные слова.",
    )


def load_database_state(db_path: Path, source_label: str) -> dict[str, Any]:
    books = [{"label": "Все книги", "key": ""}]
    for book in list_books(db_path):
        label = book.title
        if book.authors:
            label += f" · {book.authors}"
        label += f" · {book.lookup_count}"
        books.append({"label": label, "key": book.key})
    entries = [_entry_for_frontend(entry) for entry in fetch_entries(db_path)]
    return {
        "sourceName": source_label,
        "sourceStatus": "Vocabulary Builder загружен",
        "books": books,
        "entries": entries,
    }


def _entry_for_frontend(entry: dict[str, object]) -> dict[str, str]:
    payload = {
        "word": str(entry.get("word") or ""),
        "stem": str(entry.get("stem") or ""),
        "context": str(entry.get("context") or ""),
        "book_key": str(entry.get("book_key") or ""),
        "book_title": str(entry.get("book_title") or ""),
        "authors": str(entry.get("authors") or ""),
        "language": str(entry.get("language") or ""),
        "looked_up_at": str(entry.get("looked_up_at") or "").split("T", maxsplit=1)[0],
        "processing_status": "raw",
        "export_status": "none",
    }
    payload["id"] = _entry_id(payload)
    return payload


def _entry_id(entry: dict[str, object]) -> str:
    raw = "|".join(
        str(entry.get(key) or "")
        for key in ["word", "stem", "context", "book_key", "book_title", "looked_up_at"]
    )
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()


def export_frontend_entries(
    entries: list[object],
    output_path: Path,
    export_format: str,
    workspace: Path,
) -> int:
    saved_rows = _load_saved_optimized_rows(workspace / ".app-data" / "optimized" / "optimized.tsv")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for item in entries:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        row = _optimized_row_from_frontend(entry)
        if row is None:
            row = _saved_optimized_row_for_entry(entry, saved_rows)
        if row is None or not _is_exportable_optimized_row(row):
            continue
        key = _optimized_export_key(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if export_format == "anki":
        _write_anki_export(rows, output_path)
    elif export_format == "quizlet":
        _write_quizlet_export(rows, output_path)
    else:
        raise ValueError(f"Unsupported export format: {export_format}")

    logger.info("Exported optimized rows path=%s format=%s rows=%d", output_path, export_format, len(rows))
    return len(rows)


def _optimized_row_from_frontend(entry: dict[str, Any]) -> dict[str, str] | None:
    analysis = entry.get("analysis")
    if not isinstance(analysis, dict):
        return None
    if analysis.get("accepted") is False:
        return None
    if _export_score(analysis.get("importance_score")) is None:
        return None

    warnings = analysis.get("warnings") or []
    source_forms = analysis.get("source_word_forms") or [entry.get("word") or ""]
    return {
        "Word": _clean_export(entry.get("word")),
        "Base form": _clean_export(analysis.get("base_form") or entry.get("stem") or entry.get("word")),
        "Part of speech": _clean_export(analysis.get("pos")),
        "Russian meaning(s)": _clean_export(analysis.get("russian_meanings")),
        "Generated context sentence EN": _clean_export(analysis.get("generated_context_en")),
        "Generated context sentence RU": _clean_export(analysis.get("generated_context_ru")),
        "Importance 0-10": _clean_export(analysis.get("importance_score")),
        "Importance note": _clean_export(analysis.get("importance_note")),
        "Lemma Zipf": _clean_export(analysis.get("lemma_zipf")),
        "Form Zipf": _clean_export(analysis.get("form_zipf")),
        "WordNet synset count": _clean_export(analysis.get("wordnet_synset_count")),
        "WordNet POS count": _clean_export(analysis.get("wordnet_pos_count")),
        "Warnings": _clean_export(_join_export_values(warnings)),
        "Tags": _clean_export(analysis.get("tags")),
        "Source word forms": _clean_export(_join_export_values(source_forms)),
        "Source occurrence count": _clean_export(analysis.get("source_occurrence_count")),
        "Original word": _clean_export(entry.get("word")),
        "Original stem": _clean_export(entry.get("stem")),
        "Original context": _clean_export(entry.get("context")),
        "Original book_title": _clean_export(entry.get("book_title")),
        "Original authors": _clean_export(entry.get("authors")),
        "Original language": _clean_export(entry.get("language")),
        "Original looked_up_at": _clean_export(entry.get("looked_up_at")),
    }


def _load_saved_optimized_rows(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        for raw_row in reader:
            row = {header: str((raw_row or {}).get(header) or "") for header in OPTIMIZED_TSV_HEADER}
            rows[_optimized_export_key(row)] = row
    return rows


def _saved_optimized_row_for_entry(
    entry: dict[str, Any],
    saved_rows: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    if not saved_rows:
        return None
    analysis = entry.get("analysis") if isinstance(entry.get("analysis"), dict) else {}
    base_candidates = [
        str(analysis.get("base_form") or ""),
        str(entry.get("stem") or ""),
        str(entry.get("word") or ""),
    ]
    book_title = str(entry.get("book_title") or "")
    authors = str(entry.get("authors") or "")
    for base_form in base_candidates:
        key = _optimized_export_key_from_values(base_form, book_title, authors)
        if key in saved_rows:
            return saved_rows[key]
    return None


def _is_exportable_optimized_row(row: dict[str, str]) -> bool:
    return _export_score(row.get("Importance 0-10")) is not None


def _write_anki_export(rows: list[dict[str, str]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OPTIMIZED_TSV_HEADER, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in OPTIMIZED_TSV_HEADER})


def _write_quizlet_export(rows: list[dict[str, str]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter="\t")
        writer.writerow(["term", "definition"])
        for row in rows:
            source = " - ".join(part for part in [row.get("Original book_title", ""), row.get("Original authors", "")] if part)
            details = [
                f"base: {row.get('Base form', '')}",
                f"score: {row.get('Importance 0-10', '')}/10",
            ]
            if row.get("Part of speech"):
                details.append(f"pos: {row['Part of speech']}")
            if row.get("Lemma Zipf"):
                details.append(f"lemma Zipf: {row['Lemma Zipf']}")
            if row.get("Form Zipf"):
                details.append(f"form Zipf: {row['Form Zipf']}")
            if row.get("Importance note"):
                details.append(f"note: {row['Importance note']}")
            if row.get("Original context"):
                details.append(f"context: {row['Original context']}")
            if source:
                details.append(f"source: {source}")
            writer.writerow([row.get("Word", ""), "; ".join(details)])


def _optimized_export_key(row: dict[str, str]) -> str:
    return _optimized_export_key_from_values(
        row.get("Base form", ""),
        row.get("Original book_title", ""),
        row.get("Original authors", ""),
    )


def _optimized_export_key_from_values(base_form: object, book_title: object, authors: object) -> str:
    return "\t".join(str(value or "").casefold().strip() for value in [base_form, book_title, authors])


def _export_score(value: object) -> int | None:
    try:
        score = int(float(str(value)))
    except (TypeError, ValueError):
        return None
    if score < 0 or score > 10:
        return None
    return score


def _join_export_values(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item))
    return str(value or "")


def _clean_export(value: object) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    return html.escape(text, quote=False)


def _entry_updates_from_analysis(
    analysis_dir: Path,
    submitted_entries: list[object],
    tsv_path: str,
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    submitted_ids = {
        str(entry.get("id") or _entry_id(entry))
        for entry in submitted_entries
        if isinstance(entry, dict)
    }
    for path in sorted(analysis_dir.glob("*.json")):
        try:
            analysis = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read analysis JSON path=%s", path)
            continue

        entry = dict(analysis.get("representative_entry") or {})
        entry_id = str(entry.get("id") or _entry_id(entry))
        if entry_id not in submitted_ids:
            continue
        importance = dict(analysis.get("importance") or {})
        frequencies = dict(analysis.get("frequencies") or {})
        wordnet = dict(analysis.get("wordnet") or {})
        warnings = dict(analysis.get("warnings") or {})
        tsv_row = dict(analysis.get("tsv_row") or {})
        accepted = bool(analysis.get("accepted"))
        updates.append(
            {
                "id": entry_id,
                "processing_status": "processed" if accepted else "rejected",
                "analysis": {
                    "base_form": str(analysis.get("base_form") or entry.get("stem") or entry.get("word") or ""),
                    "pos": str(analysis.get("pos") or ""),
                    "accepted": accepted,
                    "importance_score": importance.get("score"),
                    "importance_note": str(importance.get("note") or ""),
                    "frequency_note": _frequency_note(frequencies),
                    "lemma_zipf": frequencies.get("lemma_zipf"),
                    "form_zipf": frequencies.get("form_zipf"),
                    "wordnet_synset_count": wordnet.get("synset_count"),
                    "wordnet_pos_count": wordnet.get("pos_count"),
                    "warnings": sorted(warnings),
                    "tags": str(tsv_row.get("Tags") or ""),
                    "source_word_forms": analysis.get("source_word_forms") or [],
                    "source_occurrence_count": analysis.get("source_occurrence_count"),
                    "processed_at": str(analysis.get("processed_at") or ""),
                    "translation_status": "offline_only",
                    "tsv_path": tsv_path,
                },
            }
        )

    if updates:
        return updates

    return [
        {
            "id": str(entry.get("id") or _entry_id(entry)),
            "processing_status": "skipped",
            "analysis": {
                "base_form": str(entry.get("stem") or entry.get("word") or ""),
                "accepted": True,
                "importance_note": "уже есть в processed snapshot",
                "translation_status": "offline_only",
                "tsv_path": tsv_path,
            },
        }
        for entry in submitted_entries
        if isinstance(entry, dict)
    ]


def _frequency_note(frequencies: dict[str, Any]) -> str:
    lemma = frequencies.get("lemma_zipf")
    form = frequencies.get("form_zipf")
    parts = []
    if lemma is not None:
        parts.append(f"lemma Zipf {lemma}")
    if form is not None:
        parts.append(f"form Zipf {form}")
    return ", ".join(parts)


def demo_state(source_name: str = "Demo Kindle", source_status: str = "Загружены демонстрационные данные") -> dict[str, Any]:
    entries = [
        {
            "word": "afraid",
            "stem": "afraid",
            "context": "She was afraid to open the old door.",
            "book_key": "The Night Reader",
            "book_title": "The Night Reader",
            "authors": "Demo Library",
            "language": "en",
            "looked_up_at": "2026-06-19",
        },
        {
            "word": "glimpse",
            "stem": "glimpse",
            "context": "For a moment he caught a glimpse of the city below.",
            "book_key": "The Night Reader",
            "book_title": "The Night Reader",
            "authors": "Demo Library",
            "language": "en",
            "looked_up_at": "2026-06-18",
        },
        {
            "word": "dread",
            "stem": "dread",
            "context": "A quiet dread settled over the room.",
            "book_key": "Shadows and Signals",
            "book_title": "Shadows and Signals",
            "authors": "Demo Library",
            "language": "en",
            "looked_up_at": "2026-06-17",
        },
    ]
    return {
        "sourceName": source_name,
        "sourceStatus": source_status,
        "books": [
            {"label": "Все книги", "key": ""},
            {"label": "The Night Reader · Demo Library · 2", "key": "The Night Reader"},
            {"label": "Shadows and Signals · Demo Library · 1", "key": "Shadows and Signals"},
        ],
        "entries": [_entry_for_frontend(entry) for entry in entries],
    }


if __name__ == "__main__":
    raise SystemExit(main())
