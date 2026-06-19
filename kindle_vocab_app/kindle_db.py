from __future__ import annotations

import csv
import html
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from kindle_vocab_app.logging_config import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class Book:
    key: str
    title: str
    authors: str
    lookup_count: int


def normalize_timestamp(value: int | None) -> str:
    if not value:
        return ""

    seconds = value / 1000 if value > 10_000_000_000 else value
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return str(value)


def _connect(db_path: Path) -> sqlite3.Connection:
    logger.debug("Opening Kindle SQLite database path=%s", db_path)
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def validate_vocab_db(db_path: Path) -> None:
    logger.info("Validating Kindle vocab database path=%s", db_path)
    required_tables = {"WORDS", "LOOKUPS", "BOOK_INFO"}
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    available = {row["name"].upper() for row in rows}
    missing = sorted(required_tables - available)
    if missing:
        logger.warning("Database validation failed path=%s missing_tables=%s", db_path, missing)
        raise ValueError(f"Not a Kindle vocab.db file. Missing tables: {', '.join(missing)}")
    logger.info("Database validation succeeded path=%s tables=%s", db_path, sorted(available))


def list_books(db_path: Path) -> list[Book]:
    logger.info("Listing Kindle books path=%s", db_path)
    query = """
        SELECT
            COALESCE(b.id, b.guid, l.book_key, '') AS key,
            COALESCE(NULLIF(b.title, ''), 'Unknown book') AS title,
            COALESCE(NULLIF(b.authors, ''), '') AS authors,
            COUNT(*) AS lookup_count
        FROM LOOKUPS l
        LEFT JOIN BOOK_INFO b
            ON l.book_key = b.id OR l.book_key = b.guid
        GROUP BY key, title, authors
        ORDER BY lower(title), lower(authors)
    """
    with _connect(db_path) as connection:
        rows = connection.execute(query).fetchall()
    books = [
        Book(
            key=str(row["key"]),
            title=str(row["title"]),
            authors=str(row["authors"] or ""),
            lookup_count=int(row["lookup_count"]),
        )
        for row in rows
    ]
    logger.info("Listed Kindle books path=%s count=%d", db_path, len(books))
    return books


def fetch_entries(db_path: Path, book_key: str | None = None) -> list[dict[str, object]]:
    logger.info("Fetching Kindle lookup entries path=%s book_key=%s", db_path, book_key or "<all>")
    query = """
        SELECT
            l.id AS lookup_id,
            COALESCE(b.id, b.guid, l.book_key, '') AS book_key,
            w.word AS word,
            w.stem AS stem,
            l.usage AS context,
            b.title AS book_title,
            b.authors AS authors,
            w.lang AS language,
            l.timestamp AS lookup_timestamp
        FROM LOOKUPS l
        JOIN WORDS w
            ON l.word_key = w.id
        LEFT JOIN BOOK_INFO b
            ON l.book_key = b.id OR l.book_key = b.guid
        WHERE (:book_key IS NULL OR b.id = :book_key OR b.guid = :book_key OR l.book_key = :book_key)
        ORDER BY l.timestamp DESC, lower(w.word)
    """
    with _connect(db_path) as connection:
        rows = connection.execute(query, {"book_key": book_key}).fetchall()

    entries: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        item["looked_up_at"] = normalize_timestamp(item.pop("lookup_timestamp"))
        entries.append(item)
    logger.info(
        "Fetched Kindle lookup entries path=%s book_key=%s count=%d",
        db_path,
        book_key or "<all>",
        len(entries),
    )
    return entries


def _clean(value: object, html_mode: bool) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    return html.escape(text, quote=False) if html_mode else text


def export_entries(
    entries: list[dict[str, object]],
    output_path: Path,
    export_format: str,
    *,
    html_mode: bool = False,
) -> Path:
    logger.info(
        "Exporting entries path=%s format=%s count=%d html_mode=%s",
        output_path,
        export_format,
        len(entries),
        html_mode,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter="\t")
        if export_format == "anki":
            writer.writerow(
                ["word", "stem", "context", "book_title", "authors", "language", "looked_up_at"]
            )
            for row in entries:
                writer.writerow(
                    [
                        _clean(row.get("word"), html_mode),
                        _clean(row.get("stem"), html_mode),
                        _clean(row.get("context"), html_mode),
                        _clean(row.get("book_title"), html_mode),
                        _clean(row.get("authors"), html_mode),
                        _clean(row.get("language"), html_mode),
                        _clean(row.get("looked_up_at"), html_mode),
                    ]
                )
        elif export_format == "quizlet":
            writer.writerow(["term", "definition"])
            for row in entries:
                source = " - ".join(
                    part
                    for part in [
                        _clean(row.get("book_title"), html_mode),
                        _clean(row.get("authors"), html_mode),
                    ]
                    if part
                )
                context = _clean(row.get("context"), html_mode)
                definition = f"{context} ({source})" if source else context
                writer.writerow([_clean(row.get("word"), html_mode), definition])
        else:
            logger.warning("Unsupported export format requested format=%s path=%s", export_format, output_path)
            raise ValueError(f"Unsupported export format: {export_format}")

    logger.info("Export completed path=%s format=%s count=%d", output_path, export_format, len(entries))
    return output_path
