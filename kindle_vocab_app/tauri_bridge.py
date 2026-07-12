from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from kindle_vocab_app import obsidian_sync, settings, vocab_cache
from kindle_vocab_app.kindle_db import fetch_entries, list_books, validate_vocab_db
from kindle_vocab_app.kindle_device import find_kindle_source
from kindle_vocab_app.logging_config import configure_logging, get_logger
from kindle_vocab_app.processing_state import ProcessedSnapshot
from kindle_vocab_app.tsv_schema import OPTIMIZED_TSV_HEADER
from kindle_vocab_app.vocab_optimizer import optimize_entries, _candidate_from_entry


logger = get_logger(__name__)
PROGRESS_PREFIX = "KINDLE_PROGRESS "


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
    job_id = str(payload.get("job_id") or "")

    if action in {"load_library", "load_cached"}:
        catalog = _load_catalog_with_sources(workspace, reconcile_kindle=False, reconcile_obsidian=False)
        return _catalog_response(catalog, connector_status=_connector_status(workspace, probe_kindle=False))

    if action == "connector_status":
        return _connector_status(workspace, probe_kindle=True)

    if action in {"sync_kindle", "scan"}:
        _emit_progress(job_id, "detecting", "Ищем подключённый Kindle", 0, 4)
        source = find_kindle_source()
        catalog = _load_catalog_with_sources(workspace, reconcile_kindle=False, reconcile_obsidian=False)
        if source is None:
            logger.info("Kindle synchronization skipped job_id=%s reason=disconnected", job_id)
            disconnected = _connector_status(workspace, probe_kindle=False)
            disconnected["kindle"] = {"state": "disconnected", "label": "Kindle", "checked_at": vocab_cache.utc_now()}
            return _catalog_response(catalog, connector_status=disconnected)
        _emit_progress(job_id, "copying", "Копируем vocab.db в локальный кэш", 1, 4)
        db_path = source.copy_to_cache(workspace / ".app-data" / "cache")
        validate_vocab_db(db_path)
        _emit_progress(job_id, "parsing", "Читаем слова и контексты", 2, 4)
        entries = [_entry_for_frontend(entry) for entry in fetch_entries(db_path)]
        sync_id = uuid.uuid4().hex
        _emit_progress(job_id, "merging", "Объединяем формы и известные леммы", 3, 4)
        catalog = vocab_cache.merge_kindle(catalog, entries, sync_id=sync_id, mark_new=True)
        _refresh_obsidian_destination_states(catalog)
        vocab_cache.save(workspace, catalog)
        _emit_progress(job_id, "completed", "Синхронизация Kindle завершена", 4, 4)
        logger.info(
            "Kindle synchronization completed job_id=%s sync_id=%s entries=%d lexemes=%d",
            job_id,
            sync_id,
            len(entries),
            len(catalog["lexemes"]),
        )
        return _catalog_response(
            catalog,
            source_name=source.label,
            source_status="Vocabulary Builder синхронизирован",
            connector_status={
                **_connector_status(workspace, probe_kindle=False),
                "kindle": {"state": "connected", "label": source.label, "checked_at": vocab_cache.utc_now()},
            },
        )

    if action == "load_demo":
        raw = demo_state()["entries"]
        catalog = vocab_cache.merge_kindle(vocab_cache.empty_catalog(), raw, sync_id="demo", mark_new=True)
        return _catalog_response(catalog, source_name="Demo Kindle", source_status="Демонстрационные данные")

    if action == "export":
        entries = [_lexeme_as_entry(item) for item in payload.get("entries") or []]
        export_format = str(payload.get("format") or "anki")
        output = workspace / ".app-data" / f"kindle-{export_format}.tsv"
        exported = export_frontend_entries(entries, output, export_format, workspace)
        catalog = _load_catalog_with_sources(workspace, reconcile_kindle=False, reconcile_obsidian=False)
        exported_ids = {str(item.get("id") or "") for item in payload.get("entries") or []}
        now = vocab_cache.utc_now()
        for lexeme in catalog["lexemes"]:
            if lexeme.get("id") in exported_ids:
                lexeme["destinations"][export_format] = {"state": "exported", "last_exported_at": now}
        vocab_cache.save(workspace, catalog)
        return {"path": str(output), "exported": exported}

    if action in {"process_lexemes", "optimize"}:
        catalog = _load_catalog_with_sources(workspace, reconcile_kindle=False, reconcile_obsidian=False)
        requested_ids = {str(value) for value in payload.get("ids") or []}
        if not requested_ids and payload.get("entries"):
            requested_ids = {str(item.get("id") or "") for item in payload.get("entries") or []}
        selected = [
            item
            for item in catalog["lexemes"]
            if item.get("id") in requested_ids and (item.get("processing") or {}).get("state") in {"pending", "failed"}
        ]
        entries = [_lexeme_as_entry(item) for item in selected]
        candidate_keys_by_id: dict[str, str] = {}
        for entry in entries:
            candidate = _candidate_from_entry(entry)
            if candidate is None:
                continue
            candidate_keys_by_id[str(entry.get("id") or "")] = vocab_cache.normalize_lemma(
                str(candidate["lexical_key"])
            )
        _emit_progress(job_id, "preparing", f"Подготовлено лемм: {len(entries)}", 0, max(len(entries), 1))
        output_dir = workspace / ".app-data" / "optimized"
        result = optimize_entries(
            entries,
            output_dir,
            output_dir / "processed_snapshot.json",
            progress_callback=lambda current, total, lemma: _emit_progress(
                job_id,
                "processing",
                f"Анализируем {lemma}",
                current,
                max(total, 1),
            ),
        )
        analyses, analyses_by_id = _analysis_by_lemma(result.analysis_dir)
        snapshot = ProcessedSnapshot.load(result.snapshot_path)
        rejected_without_candidate = 0
        for index, lexeme in enumerate(selected, 1):
            lemma_key = vocab_cache.normalize_lemma(str(lexeme.get("lemma") or ""))
            forms = {vocab_cache.normalize_lemma(str(form)) for form in lexeme.get("forms") or []}
            display_key = vocab_cache.normalize_lemma(str(lexeme.get("display_form") or ""))
            lexeme_id = str(lexeme.get("id") or "")
            candidate_key = candidate_keys_by_id.get(lexeme_id, "")
            if not candidate_key:
                rejected_without_candidate += 1
                lexeme["processing"] = {
                    "state": "rejected",
                    "analysis": _analysis_for_unsupported_entry(lexeme),
                    "updated_at": vocab_cache.utc_now(),
                    "error": "",
                }
                lexeme["destinations"]["obsidian"].update(
                    {"state": "not_synced", "reason": "unsupported_language"}
                )
                logger.info(
                    "Rejected unsupported offline-processing entry job_id=%s lexeme_id=%s language=%s",
                    job_id,
                    lexeme_id,
                    lexeme.get("language"),
                )
                continue
            analysis = analyses.get(candidate_key) or analyses.get(lemma_key) or analyses_by_id.get(lexeme_id)
            if analysis is None:
                previous = (lexeme.get("processing") or {}).get("analysis")
                if previous:
                    analysis = previous
            if analysis is None:
                for key, candidate in analyses.items():
                    if key in forms or key == display_key:
                        analysis = candidate
                        break
            if analysis is None:
                for key in {candidate_key, lemma_key, display_key, *forms}:
                    if not key:
                        continue
                    if snapshot.has_processed(key):
                        analysis = _analysis_from_snapshot(snapshot.processed[key])
                        break
            if analysis is None:
                lexeme["processing"] = {
                    "state": "failed",
                    "analysis": None,
                    "updated_at": vocab_cache.utc_now(),
                    "error": "Не найден audit-файл offline-обработки",
                }
            else:
                accepted = analysis.get("accepted") is not False
                lexeme["processing"] = {
                    "state": "ready" if accepted else "rejected",
                    "analysis": analysis,
                    "updated_at": str(analysis.get("processed_at") or vocab_cache.utc_now()),
                    "error": "",
                }
                lexeme["lemma"] = vocab_cache.normalize_lemma(str(analysis.get("base_form") or lexeme["lemma"]))
                if not accepted:
                    lexeme["destinations"]["obsidian"].update(
                        {"state": "not_synced", "reason": "rejected"}
                    )
            logger.debug(
                "Applied processing result job_id=%s lexeme_id=%s index=%d total=%d state=%s",
                job_id,
                lexeme.get("id"),
                index,
                len(selected),
                lexeme["processing"]["state"],
            )
        _refresh_obsidian_destination_states(catalog)
        vocab_cache.save(workspace, catalog)
        _emit_progress(job_id, "completed", "Offline-обработка завершена", len(selected), max(len(selected), 1))
        return {
            "processed_new": result.processed_new,
            "accepted_new": result.accepted_new,
            "skipped_existing": result.skipped_existing,
            "rejected_new": result.rejected_new + rejected_without_candidate,
            "tsv_path": str(result.tsv_path),
            "entries": catalog["lexemes"],
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
        catalog = _load_catalog_with_sources(workspace, reconcile_kindle=False, reconcile_obsidian=False)
        entries = obsidian_sync.read_cards(cards_dir)
        catalog = vocab_cache.merge_obsidian(catalog, entries)
        vocab_cache.save(workspace, catalog)
        return _catalog_response(catalog, source_name="Obsidian", source_status=f"Сверено карточек: {len(entries)}")

    if action == "sync_obsidian":
        app_settings = settings.load(workspace)
        vault_path = str(payload.get("vault_path") or app_settings.obsidian_vault_path)
        cards_path = str(payload.get("cards_path") or app_settings.obsidian_cards_path)
        backup_enabled = bool(payload.get("backup_enabled", app_settings.obsidian_backup_enabled))
        if not vault_path or not cards_path:
            raise ValueError("vault_path and cards_path are required")
        catalog = _load_catalog_with_sources(workspace, reconcile_kindle=False, reconcile_obsidian=False)
        entries = [_lexeme_as_entry(item) for item in catalog["lexemes"] if (item.get("destinations") or {}).get("obsidian", {}).get("state") != "synced"]
        cards_dir = Path(vault_path) / cards_path
        backups_dir = workspace / ".app-data" / "obsidian-backups"
        _emit_progress(job_id, "reconciling", f"Проверяем очередь: {len(entries)}", 0, max(len(entries), 1))
        result = obsidian_sync.append_cards(
            cards_dir, entries, backups_dir, backup_enabled=backup_enabled
        )
        result_by_id = {str(item.get("id") or ""): item for item in result.get("items") or []}
        for index, lexeme in enumerate(catalog["lexemes"], 1):
            item = result_by_id.get(str(lexeme.get("id") or ""))
            if item is None:
                continue
            outcome = item.get("outcome")
            destination = lexeme["destinations"]["obsidian"]
            if outcome in {"added", "already_present"}:
                destination.update({"state": "synced", "reason": "", "last_synced_at": vocab_cache.utc_now()})
                lexeme["sources"]["obsidian"] = True
            elif outcome == "failed":
                destination.update({"state": "failed", "reason": item.get("reason") or "sync_failed"})
            else:
                destination.update({"state": "not_synced", "reason": item.get("reason") or "waiting_processing"})
            _emit_progress(job_id, "syncing", f"Проверено {index} из {len(catalog['lexemes'])}", index, len(catalog["lexemes"]), lexeme_id=str(lexeme.get("id") or ""))
        vocab_cache.save(workspace, catalog)
        result["entries"] = catalog["lexemes"]
        _emit_progress(job_id, "completed", "Синхронизация Obsidian завершена", len(entries), max(len(entries), 1))
        return result

    raise ValueError(f"Unsupported bridge action: {action}")


def _emit_progress(
    job_id: str,
    stage: str,
    message: str,
    current: int,
    total: int,
    *,
    lexeme_id: str = "",
) -> None:
    if not job_id:
        return
    payload = {
        "job_id": job_id,
        "stage": stage,
        "message": message,
        "current": current,
        "total": total,
        "lexeme_id": lexeme_id,
        "timestamp": vocab_cache.utc_now(),
    }
    sys.stderr.write(PROGRESS_PREFIX + json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n")
    sys.stderr.flush()


def _load_catalog_with_sources(workspace: Path, *, reconcile_kindle: bool = True, reconcile_obsidian: bool = True) -> dict[str, Any]:
    catalog = vocab_cache.load(workspace) or vocab_cache.empty_catalog()
    if reconcile_kindle:
        cached_db = workspace / ".app-data" / "cache" / "vocab.db"
        if cached_db.exists():
            try:
                validate_vocab_db(cached_db)
                entries = [_entry_for_frontend(entry) for entry in fetch_entries(cached_db)]
                catalog = vocab_cache.merge_kindle(
                    catalog,
                    entries,
                    sync_id=str(catalog.get("last_kindle_sync_id") or "cached"),
                    mark_new=False,
                )
            except Exception:
                logger.exception("Failed to reconcile cached Kindle database")

    app_settings = settings.load(workspace)
    if reconcile_obsidian and app_settings.obsidian_sync_enabled and app_settings.obsidian_vault_path and app_settings.obsidian_cards_path:
        cards_dir = Path(app_settings.obsidian_vault_path) / app_settings.obsidian_cards_path
        try:
            catalog = vocab_cache.merge_obsidian(catalog, obsidian_sync.read_cards(cards_dir))
        except Exception:
            logger.exception("Failed to reconcile Obsidian cards")
    _refresh_obsidian_destination_states(catalog)
    vocab_cache.save(workspace, catalog)
    return catalog


def _connector_status(workspace: Path, *, probe_kindle: bool) -> dict[str, Any]:
    app_settings = settings.load(workspace)
    source = find_kindle_source() if probe_kindle else None
    kindle = {
        "state": "connected" if source is not None else ("disconnected" if probe_kindle else "unknown"),
        "label": source.label if source is not None else "Kindle",
        "checked_at": vocab_cache.utc_now(),
    }
    cards_dir = Path(app_settings.obsidian_vault_path) / app_settings.obsidian_cards_path if app_settings.obsidian_vault_path else None
    configured = bool(app_settings.obsidian_sync_enabled and cards_dir)
    obsidian_state = "disabled"
    if configured:
        obsidian_state = "connected" if cards_dir and cards_dir.exists() else "error"
    return {
        "kindle": kindle,
        "obsidian": {
            "state": obsidian_state,
            "label": "Obsidian",
            "checked_at": vocab_cache.utc_now(),
        },
    }


def _catalog_response(
    catalog: dict[str, Any],
    *,
    source_name: str = "Локальная библиотека",
    source_status: str = "Сохранённые слова доступны без устройства",
    connector_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = vocab_cache.frontend_state(catalog, source_name=source_name, source_status=source_status)
    result["connectors"] = connector_status or _connector_status(_workspace_root(), probe_kindle=False)
    return result


def _lexeme_as_entry(lexeme: dict[str, Any]) -> dict[str, Any]:
    occurrences = list(lexeme.get("occurrences") or [])
    occurrence = max(
        occurrences,
        key=lambda item: (bool(item.get("context")), len(str(item.get("context") or "")), str(item.get("looked_up_at") or "")),
        default={},
    )
    processing = lexeme.get("processing") or {}
    return {
        "id": str(lexeme.get("id") or ""),
        "word": str(lexeme.get("display_form") or lexeme.get("lemma") or ""),
        "stem": str(lexeme.get("lemma") or ""),
        "context": str(occurrence.get("context") or ""),
        "book_key": str(occurrence.get("book_key") or ""),
        "book_title": str(occurrence.get("book_title") or ""),
        "authors": str(occurrence.get("authors") or ""),
        "language": str(lexeme.get("language") or "en"),
        "looked_up_at": str(occurrence.get("looked_up_at") or ""),
        "processing_status": "processed" if processing.get("state") == "ready" else processing.get("state"),
        "analysis": processing.get("analysis"),
    }


def _refresh_obsidian_destination_states(catalog: dict[str, Any]) -> None:
    """Keep the Obsidian queue reason aligned with the independent processing state."""
    for lexeme in catalog.get("lexemes") or []:
        destination = (lexeme.get("destinations") or {}).get("obsidian")
        if not isinstance(destination, dict) or destination.get("state") == "synced":
            continue
        processing_state = str((lexeme.get("processing") or {}).get("state") or "pending")
        if processing_state == "ready":
            destination.update({"state": "not_synced", "reason": ""})
        elif processing_state == "rejected":
            reason = str(destination.get("reason") or "")
            warnings = (lexeme.get("processing") or {}).get("analysis") or {}
            unsupported = "unsupported_language" in (warnings.get("warnings") or [])
            destination.update(
                {
                    "state": "not_synced",
                    "reason": "unsupported_language" if unsupported or reason == "unsupported_language" else "rejected",
                }
            )
        elif processing_state == "failed":
            destination.update({"state": "not_synced", "reason": "processing_failed"})
        else:
            destination.update({"state": "not_synced", "reason": "waiting_processing"})


def _analysis_for_unsupported_entry(lexeme: dict[str, Any]) -> dict[str, Any]:
    """Build an honest terminal result when the offline English optimizer cannot parse an entry."""
    occurrences = list(lexeme.get("occurrences") or [])
    return {
        "base_form": str(lexeme.get("lemma") or lexeme.get("display_form") or ""),
        "accepted": False,
        "importance_score": 0,
        "importance_note": "Offline-обработчик поддерживает только английские слова.",
        "frequency_note": "",
        "warnings": ["unsupported_language"],
        "source_occurrence_count": len(occurrences),
        "translation_status": "offline_only",
    }


def _analysis_by_lemma(analysis_dir: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return (analysis by normalized lexical_key, analysis by representative entry id)."""
    by_lemma: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    if not analysis_dir.exists():
        return by_lemma, by_id
    for path in analysis_dir.glob("*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read analysis audit file path=%s", path)
            continue
        importance = raw.get("importance") or {}
        frequencies = raw.get("frequencies") or {}
        wordnet = raw.get("wordnet") or {}
        analysis = {
            "base_form": str(raw.get("base_form") or raw.get("lexical_key") or ""),
            "pos": str(raw.get("pos") or ""),
            "accepted": bool(raw.get("accepted", True)),
            "importance_score": importance.get("score"),
            "importance_note": str(importance.get("explanation") or importance.get("note") or ""),
            "frequency_note": _frequency_note(frequencies),
            "lemma_zipf": frequencies.get("lemma_zipf"),
            "form_zipf": frequencies.get("form_zipf"),
            "wordnet_synset_count": wordnet.get("synset_count"),
            "wordnet_pos_count": wordnet.get("pos_count"),
            "warnings": sorted((raw.get("warnings") or {}).keys()) if isinstance(raw.get("warnings"), dict) else list(raw.get("warnings") or []),
            "tags": str(raw.get("tags") or ""),
            "source_word_forms": list(raw.get("source_word_forms") or []),
            "source_occurrence_count": raw.get("source_occurrence_count"),
            "processed_at": str(raw.get("processed_at") or ""),
            "translation_status": "offline_only",
        }
        key = vocab_cache.normalize_lemma(str(raw.get("lexical_key") or analysis["base_form"]))
        if key:
            by_lemma[key] = analysis
        entry = dict(raw.get("representative_entry") or {})
        entry_id = str(entry.get("id") or "")
        if entry_id:
            by_id[entry_id] = analysis
    return by_lemma, by_id


def _analysis_from_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal analysis dict from a processed-snapshot entry."""
    return {
        "base_form": str(payload.get("base_form") or ""),
        "pos": "",
        "accepted": bool(payload.get("accepted", True)),
        "importance_score": payload.get("importance"),
        "importance_note": "уже обработано ранее",
        "frequency_note": "",
        "lemma_zipf": None,
        "form_zipf": None,
        "wordnet_synset_count": None,
        "wordnet_pos_count": None,
        "warnings": [],
        "tags": "",
        "source_word_forms": list(payload.get("source_word_forms") or []),
        "source_occurrence_count": payload.get("source_occurrence_count"),
        "processed_at": str(payload.get("last_seen_at") or ""),
        "translation_status": "offline_only",
    }


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
