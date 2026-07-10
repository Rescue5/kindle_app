from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kindle_vocab_app.logging_config import get_logger


logger = get_logger(__name__)

SETTINGS_VERSION = 1
SETTINGS_FILENAME = "settings.json"

_VALID_THEMES = {"system", "light", "dark"}
_VALID_LANGUAGES = {"ru", "en"}
_VALID_EXPORT_FORMATS = {"anki", "quizlet", "obsidian"}


@dataclass
class AppSettings:
    version: int = 1
    theme: str = "system"
    language: str = "ru"
    default_export_format: str = "anki"
    app_data_path: str = ""
    llm_enabled: bool = False
    llm_model: str = "deepseek-v4-flash"
    llm_base_url: str = "https://api.dslab.tech/v1"
    obsidian_sync_enabled: bool = False
    obsidian_vault_path: str = ""
    obsidian_cards_path: str = "cards/Book Vocab"
    obsidian_backup_enabled: bool = True


def settings_path(workspace: Path) -> Path:
    return workspace / ".app-data" / SETTINGS_FILENAME


def load(workspace: Path) -> AppSettings:
    """Load persisted settings or return defaults if missing/corrupt."""
    path = settings_path(workspace)
    if not path.exists():
        logger.info("Settings file does not exist; returning defaults path=%s", path)
        return AppSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to read settings path=%s", path)
        return AppSettings()
    try:
        return from_dict(data)
    except Exception:
        logger.exception("Failed to validate settings path=%s", path)
        return AppSettings()


def save(workspace: Path, settings: AppSettings) -> None:
    """Persist settings atomically as versioned JSON."""
    path = settings_path(workspace)
    payload = to_dict(settings)
    payload["version"] = SETTINGS_VERSION
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
    logger.info("Saved settings path=%s", path)


def to_dict(settings: AppSettings) -> dict[str, Any]:
    return {
        "theme": settings.theme,
        "language": settings.language,
        "default_export_format": settings.default_export_format,
        "app_data_path": settings.app_data_path,
        "llm_enabled": settings.llm_enabled,
        "llm_model": settings.llm_model,
        "llm_base_url": settings.llm_base_url,
        "obsidian_sync_enabled": settings.obsidian_sync_enabled,
        "obsidian_vault_path": settings.obsidian_vault_path,
        "obsidian_cards_path": settings.obsidian_cards_path,
        "obsidian_backup_enabled": settings.obsidian_backup_enabled,
    }


def from_dict(data: dict[str, Any]) -> AppSettings:
    """Construct settings from a dict, validating enum fields."""
    theme = str(data.get("theme", "system"))
    if theme not in _VALID_THEMES:
        raise ValueError(f"Invalid theme: {theme!r}; expected one of {_VALID_THEMES}")

    language = str(data.get("language", "ru"))
    if language not in _VALID_LANGUAGES:
        raise ValueError(
            f"Invalid language: {language!r}; expected one of {_VALID_LANGUAGES}"
        )

    default_export_format = str(data.get("default_export_format", "anki"))
    if default_export_format not in _VALID_EXPORT_FORMATS:
        raise ValueError(
            f"Invalid default_export_format: {default_export_format!r}; "
            f"expected one of {_VALID_EXPORT_FORMATS}"
        )

    return AppSettings(
        version=int(data.get("version", SETTINGS_VERSION)),
        theme=theme,
        language=language,
        default_export_format=default_export_format,
        app_data_path=str(data.get("app_data_path", "")),
        llm_enabled=bool(data.get("llm_enabled", False)),
        llm_model=str(data.get("llm_model", "deepseek-v4-flash")),
        llm_base_url=str(data.get("llm_base_url", "https://api.dslab.tech/v1")),
        obsidian_sync_enabled=bool(data.get("obsidian_sync_enabled", False)),
        obsidian_vault_path=str(data.get("obsidian_vault_path", "")),
        obsidian_cards_path=str(data.get("obsidian_cards_path", "cards/Book Vocab")),
        obsidian_backup_enabled=bool(data.get("obsidian_backup_enabled", True)),
    )
