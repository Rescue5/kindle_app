from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SNAPSHOT_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProcessedSnapshot:
    path: Path
    processed: dict[str, dict[str, Any]] = field(default_factory=dict)
    seen_occurrences: dict[str, dict[str, Any]] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def load(cls, path: Path) -> "ProcessedSnapshot":
        if not path.exists():
            return cls(path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            path=path,
            processed=dict(data.get("processed", {})),
            seen_occurrences=dict(data.get("seen_occurrences", {})),
            created_at=str(data.get("created_at") or utc_now()),
            updated_at=str(data.get("updated_at") or utc_now()),
        )

    def has_processed(self, lexical_key: str) -> bool:
        return lexical_key in self.processed

    def remember_processed(self, lexical_key: str, payload: dict[str, Any]) -> None:
        self.processed[lexical_key] = {
            "first_seen_at": self.processed.get(lexical_key, {}).get("first_seen_at", utc_now()),
            "last_seen_at": utc_now(),
            **payload,
        }
        self.updated_at = utc_now()

    def remember_occurrence(self, fingerprint: str, payload: dict[str, Any]) -> None:
        self.seen_occurrences[fingerprint] = {
            "first_seen_at": self.seen_occurrences.get(fingerprint, {}).get("first_seen_at", utc_now()),
            "last_seen_at": utc_now(),
            **payload,
        }
        self.updated_at = utc_now()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SNAPSHOT_VERSION,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "processed": self.processed,
            "seen_occurrences": self.seen_occurrences,
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)
