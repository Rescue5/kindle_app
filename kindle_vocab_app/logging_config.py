from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOGGER_NAME = "kindle_vocab_app"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_BACKUP_COUNT = 5


def configure_logging(
    log_dir: Path,
    *,
    console: bool = False,
    level: str | None = None,
) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "kindle_vocab_app.log"
    resolved_level = _resolve_level(level or os.environ.get("KINDLE_VOCAB_LOG_LEVEL"))

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(resolved_level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _replace_handlers(logger)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=DEFAULT_MAX_BYTES,
        backupCount=DEFAULT_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(resolved_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    logger.info(
        "Logging configured path=%s level=%s console=%s",
        log_path,
        logging.getLevelName(resolved_level),
        console,
    )
    return log_path


def get_logger(name: str) -> logging.Logger:
    if name == LOGGER_NAME or name.startswith(f"{LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def _replace_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def _resolve_level(value: str | None) -> int:
    name = (value or DEFAULT_LOG_LEVEL).strip().upper()
    return getattr(logging, name, logging.INFO)
