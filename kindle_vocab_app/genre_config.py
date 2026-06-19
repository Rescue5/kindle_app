from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "processing.toml"


@dataclass(frozen=True)
class ProcessingConfig:
    preferred_categories: tuple[str, ...]
    book_genres: dict[str, tuple[str, ...]]


def load_processing_config(user_path: Path | None = None) -> ProcessingConfig:
    data: dict = {}
    for path in [DEFAULT_CONFIG_PATH, user_path]:
        if path is None or not path.exists():
            continue
        loaded = tomllib.loads(path.read_text(encoding="utf-8"))
        data = _merge_dicts(data, loaded)

    preferred = tuple(str(item) for item in data.get("preferred_categories", []))
    books = {
        str(title): tuple(str(item) for item in genres)
        for title, genres in data.get("book_genres", {}).items()
    }
    return ProcessingConfig(preferred_categories=preferred, book_genres=books)


def _merge_dicts(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result
