from __future__ import annotations

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
            "events": [
                {
                    "phase": "answered",
                    "title": "Local optimizer",
                    "message": f"Accepted {result.accepted_new} new cards from {result.processed_new} processed words.",
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
    return {
        "word": str(entry.get("word") or ""),
        "stem": str(entry.get("stem") or ""),
        "context": str(entry.get("context") or ""),
        "book_key": str(entry.get("book_key") or ""),
        "book_title": str(entry.get("book_title") or ""),
        "authors": str(entry.get("authors") or ""),
        "language": str(entry.get("language") or ""),
        "looked_up_at": str(entry.get("looked_up_at") or "").split("T", maxsplit=1)[0],
    }


def demo_state(source_name: str = "Demo Kindle", source_status: str = "Preview data loaded") -> dict[str, Any]:
    return {
        "sourceName": source_name,
        "sourceStatus": source_status,
        "books": [
            {"label": "Все книги", "key": ""},
            {"label": "The Night Reader · Demo Library · 2", "key": "The Night Reader"},
            {"label": "Shadows and Signals · Demo Library · 1", "key": "Shadows and Signals"},
        ],
        "entries": [
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
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
