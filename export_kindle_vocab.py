#!/usr/bin/env python3
"""Export Kindle Vocabulary Builder entries from vocab.db.

Kindle keeps Vocabulary Builder data in an SQLite database, usually at
Kindle/system/vocabulary/vocab.db when the device is connected over USB.
"""

from __future__ import annotations

import argparse
import csv
import html
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ANKI_FIELDS = [
    "word",
    "stem",
    "context",
    "book_title",
    "authors",
    "language",
    "looked_up_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Kindle Vocabulary Builder vocab.db to Anki or Quizlet."
    )
    parser.add_argument("database", type=Path, help="Path to Kindle vocab.db")
    parser.add_argument("output", type=Path, help="Output .tsv or .csv file")
    parser.add_argument(
        "--format",
        choices=("anki", "quizlet"),
        default="anki",
        help="Export format. Anki gets rich fields; Quizlet gets term/definition.",
    )
    parser.add_argument(
        "--delimiter",
        choices=("tab", "comma"),
        default="tab",
        help="Field delimiter for the output file.",
    )
    parser.add_argument(
        "--include-header",
        action="store_true",
        help="Write a header row. Leave off for the smoothest Anki/Quizlet import.",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="HTML-escape fields so Anki can import them with 'Allow HTML in fields'.",
    )
    return parser.parse_args()


def normalize_timestamp(value: int | None) -> str:
    if not value:
        return ""

    # Kindle timestamps found in vocab.db are commonly milliseconds since epoch.
    seconds = value / 1000 if value > 10_000_000_000 else value
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return str(value)


def clean(value: object, *, html_mode: bool) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    return html.escape(text, quote=False) if html_mode else text


def fetch_entries(db_path: Path) -> list[dict[str, object]]:
    query = """
        SELECT
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
        ORDER BY l.timestamp DESC, lower(w.word)
    """

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query).fetchall()

    return [dict(row) for row in rows]


def write_anki(rows: list[dict[str, object]], output: Path, delimiter: str, include_header: bool, html_mode: bool) -> None:
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter=delimiter)
        if include_header:
            writer.writerow(ANKI_FIELDS)
        for row in rows:
            writer.writerow(
                [
                    clean(row["word"], html_mode=html_mode),
                    clean(row["stem"], html_mode=html_mode),
                    clean(row["context"], html_mode=html_mode),
                    clean(row["book_title"], html_mode=html_mode),
                    clean(row["authors"], html_mode=html_mode),
                    clean(row["language"], html_mode=html_mode),
                    normalize_timestamp(row["lookup_timestamp"]),
                ]
            )


def write_quizlet(rows: list[dict[str, object]], output: Path, delimiter: str, include_header: bool, html_mode: bool) -> None:
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter=delimiter)
        if include_header:
            writer.writerow(["term", "definition"])
        for row in rows:
            source = " - ".join(
                part
                for part in [
                    clean(row["book_title"], html_mode=html_mode),
                    clean(row["authors"], html_mode=html_mode),
                ]
                if part
            )
            context = clean(row["context"], html_mode=html_mode)
            definition = f"{context} ({source})" if source else context
            writer.writerow([clean(row["word"], html_mode=html_mode), definition])


def main() -> int:
    args = parse_args()
    delimiter = "\t" if args.delimiter == "tab" else ","

    if not args.database.exists():
        raise SystemExit(f"Database not found: {args.database}")

    rows = fetch_entries(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.format == "anki":
        write_anki(rows, args.output, delimiter, args.include_header, args.html)
    else:
        write_quizlet(rows, args.output, delimiter, args.include_header, args.html)

    print(f"Exported {len(rows)} lookup entries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
