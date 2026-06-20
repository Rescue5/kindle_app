from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from kindle_vocab_app.kindle_db import export_entries, fetch_entries, list_books, validate_vocab_db
from kindle_vocab_app.kindle_device import find_kindle_source
from kindle_vocab_app.logging_config import configure_logging, get_logger
from kindle_vocab_app.vocab_optimizer import optimize_entries


logger = get_logger(__name__)


def main() -> int:
    _configure_stdio()
    workspace = _workspace_root()
    configure_logging(workspace / ".app-data" / "tauri-logs", console=True)
    try:
        request = json.loads(sys.stdin.read() or "{}")
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
            return demo_state(
                source_name="Kindle не найден",
                source_status="Подключите Kindle по USB. Пока показаны демонстрационные слова.",
            )
        cache_dir = workspace / ".app-data" / "cache"
        db_path = source.copy_to_cache(cache_dir)
        validate_vocab_db(db_path)
        return load_database_state(db_path, source.label)

    if action == "export":
        entries = list(payload.get("entries") or [])
        export_format = str(payload.get("format") or "anki")
        output = workspace / ".app-data" / f"kindle-{export_format}.tsv"
        export_entries(entries, output, export_format, html_mode=True)
        return {"path": str(output)}

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
        warnings = dict(analysis.get("warnings") or {})
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
                    "warnings": sorted(warnings),
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


def demo_state(source_name: str = "Demo Kindle", source_status: str = "Preview data loaded") -> dict[str, Any]:
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
