from __future__ import annotations

import csv
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from kindle_vocab_app.logging_config import get_logger
from kindle_vocab_app.tsv_schema import OPTIMIZED_TSV_HEADER


logger = get_logger(__name__)
DEFAULT_DSLAB_BASE_URL = "https://api.dslab.tech/v1"
DEFAULT_DSLAB_MODEL = "deepseek-v4-flash"
LLM_FILLED_FIELDS = [
    "Russian meaning(s)",
    "Generated context sentence EN",
    "Generated context sentence RU",
    "Importance 0-10",
    "Importance note",
]


@dataclass(frozen=True)
class LLMEnrichmentResult:
    tsv_path: Path
    processed: int
    skipped: int
    failed: int


class LLMEnrichmentError(RuntimeError):
    pass


def find_env_file(start: Path | None = None) -> Path | None:
    logger.debug("Searching for .env start=%s cwd=%s", start, Path.cwd())
    candidates = []
    if start is not None:
        candidates.append(start)
    candidates.extend([Path.cwd(), Path(__file__).resolve().parents[1]])

    seen: set[Path] = set()
    for candidate in candidates:
        current = candidate if candidate.is_dir() else candidate.parent
        for directory in [current, *current.parents]:
            if directory in seen:
                continue
            seen.add(directory)
            env_path = directory / ".env"
            if env_path.exists():
                logger.info("Found .env file path=%s", env_path)
                return env_path
    logger.info(".env file not found")
    return None


def load_dslab_environment(env_path: Path | None = None) -> None:
    resolved = env_path or find_env_file()
    if resolved is not None:
        try:
            from dotenv import load_dotenv

            load_dotenv(resolved)
            logger.info("Loaded environment with python-dotenv path=%s", resolved)
        except ImportError:
            _load_env_file_without_dependency(resolved)
            logger.info("Loaded environment with fallback parser path=%s", resolved)


def has_dslab_api_key(env_path: Path | None = None) -> bool:
    load_dslab_environment(env_path)
    has_key = bool(os.environ.get("DSLAB_API_KEY"))
    logger.info("Checked DS Lab API key availability has_key=%s", has_key)
    return has_key


def enrich_optimized_tsv(
    tsv_path: Path,
    *,
    output_path: Path | None = None,
    analysis_dir: Path | None = None,
    env_path: Path | None = None,
    force: bool = False,
    limit: int | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> LLMEnrichmentResult:
    logger.info(
        "Starting LLM enrichment tsv=%s output_path=%s analysis_dir=%s force=%s limit=%s",
        tsv_path,
        output_path,
        analysis_dir,
        force,
        limit,
    )
    load_dslab_environment(env_path)
    api_key = os.environ.get("DSLAB_API_KEY")
    if not api_key:
        logger.warning("Cannot start LLM enrichment because DSLAB_API_KEY is missing")
        raise LLMEnrichmentError("DSLAB_API_KEY is missing. Add it to .env before LLM enrichment.")

    client = DeepSeekVocabularyClient(api_key=api_key)
    rows = _read_tsv(tsv_path)
    output = output_path or tsv_path
    logger.info("Read optimized TSV for LLM enrichment tsv=%s rows=%d", tsv_path, len(rows))

    processed = 0
    skipped = 0
    failed = 0
    for row in rows:
        if limit is not None and processed >= limit:
            skipped += 1
            logger.debug("Skipping row because LLM limit reached word=%s limit=%s", row.get("Word"), limit)
            continue
        if not force and not _needs_enrichment(row):
            skipped += 1
            logger.debug("Skipping row because LLM fields are already filled word=%s", row.get("Word"))
            continue
        try:
            analysis_key = row.get("Base form") or row.get("Word") or ""
            logger.info(
                "Enriching word with LLM word=%s base_form=%s occurrence_count=%s",
                row.get("Word"),
                row.get("Base form"),
                row.get("Source occurrence count"),
            )
            _emit_progress(
                progress_callback,
                {
                    "phase": "thinking",
                    "word": row.get("Word") or row.get("Base form") or "",
                    "base_form": row.get("Base form") or "",
                    "message": "Модель подбирает смысл и пример",
                },
            )
            analysis = _read_analysis(row, analysis_dir)
            enrichment = client.enrich(row, analysis)
            _apply_enrichment(row, enrichment)
            _write_analysis_enrichment(analysis_key, analysis_dir, enrichment)
            _emit_progress(
                progress_callback,
                {
                    "phase": "answered",
                    "word": row.get("Word") or row.get("Base form") or "",
                    "base_form": row.get("Base form") or "",
                    "reasoning": enrichment.get("_reasoning_content", ""),
                    "answer": _compact_answer(enrichment),
                    "score": enrichment.get("importance_0_10", ""),
                },
            )
            processed += 1
            logger.info(
                "LLM enrichment succeeded word=%s base_form=%s score=%s",
                row.get("Word"),
                row.get("Base form"),
                enrichment.get("importance_0_10"),
            )
        except Exception as exc:
            failed += 1
            logger.exception(
                "LLM enrichment failed word=%s base_form=%s",
                row.get("Word"),
                row.get("Base form"),
            )
            row["Tags"] = _append_tag(row.get("Tags", ""), "warn_llm_enrichment_failed")
            note = str(row.get("Importance note") or "").strip()
            suffix = f"LLM enrichment failed: {exc}"
            row["Importance note"] = f"{note}; {suffix}" if note else suffix
            _emit_progress(
                progress_callback,
                {
                    "phase": "failed",
                    "word": row.get("Word") or row.get("Base form") or "",
                    "base_form": row.get("Base form") or "",
                    "message": str(exc),
                },
            )

    _write_tsv_atomic(output, rows)
    result = LLMEnrichmentResult(tsv_path=output, processed=processed, skipped=skipped, failed=failed)
    logger.info(
        "Finished LLM enrichment tsv=%s processed=%d skipped=%d failed=%d",
        result.tsv_path,
        result.processed,
        result.skipped,
        result.failed,
    )
    return result


class DeepSeekVocabularyClient:
    def __init__(self, *, api_key: str) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            logger.exception("OpenAI SDK import failed")
            raise LLMEnrichmentError(
                "The openai package is not installed. Reinstall the project dependencies first."
            ) from exc

        self.model = os.environ.get("DSLAB_MODEL", DEFAULT_DSLAB_MODEL)
        self.reasoning_effort = os.environ.get("DSLAB_REASONING_EFFORT", "high")
        self.base_url = os.environ.get("DSLAB_BASE_URL", DEFAULT_DSLAB_BASE_URL)
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=float(os.environ.get("DSLAB_TIMEOUT_SECONDS", "90")),
        )
        logger.info(
            "Initialized DS Lab OpenAI-compatible client base_url=%s model=%s reasoning_effort=%s",
            self.base_url,
            self.model,
            self.reasoning_effort,
        )

    def enrich(self, row: dict[str, str], analysis: dict[str, Any] | None) -> dict[str, Any]:
        logger.debug(
            "Sending LLM enrichment request model=%s word=%s base_form=%s has_analysis=%s",
            self.model,
            row.get("Word"),
            row.get("Base form"),
            analysis is not None,
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(_prompt_payload(row, analysis), ensure_ascii=False)},
            ],
            reasoning_effort=self.reasoning_effort,
            response_format={"type": "json_object"},
            max_tokens=int(os.environ.get("DSLAB_MAX_TOKENS", "900")),
            extra_body={"thinking": {"type": os.environ.get("DSLAB_THINKING", "enabled")}},
        )
        message = response.choices[0].message
        content = message.content or ""
        reasoning = getattr(message, "reasoning_content", "") or ""
        logger.debug(
            "Received LLM response word=%s content_chars=%d reasoning_chars=%d",
            row.get("Word"),
            len(content),
            len(reasoning),
        )
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.exception("LLM returned invalid JSON word=%s content_excerpt=%s", row.get("Word"), content[:300])
            raise LLMEnrichmentError(f"model returned invalid JSON: {exc}") from exc
        enrichment = _validate_enrichment(parsed)
        enrichment["_reasoning_content"] = reasoning
        enrichment["_raw_content"] = content
        return enrichment


_SYSTEM_PROMPT = """You prepare English vocabulary cards for a Russian-speaking Kindle reader.
Return only a valid JSON object with these keys:
word, base_form, russian_meanings, generated_context_sentence_en,
generated_context_sentence_ru, importance_0_10, importance_note, tags.

Rules:
- Use the original Kindle context and local statistics to infer the intended sense.
- If the original context is noisy, missing, too copyrighted, or too dependent on book lore,
  create a fresh natural English sentence for the word.
- Translate both the word/phrase and the generated English context into Russian.
- Reassess importance for an English learner: 0 means noise/proper-name/not useful,
  10 means broadly useful and worth learning early.
- Keep the generated English context short, natural, and self-contained.
- Keep Russian concise. Multiple meanings should be separated with semicolons.
- Preserve a better corrected base form when the local base form is wrong.
- Tags must be a short array of lowercase snake_case labels.
"""


def _prompt_payload(row: dict[str, str], analysis: dict[str, Any] | None) -> dict[str, Any]:
    wordnet = (analysis or {}).get("wordnet") or {}
    importance = (analysis or {}).get("importance") or {}
    return {
        "tsv_row": {
            "word": row.get("Word", ""),
            "base_form": row.get("Base form", ""),
            "source_word_forms": row.get("Source word forms", ""),
            "source_occurrence_count": row.get("Source occurrence count", ""),
            "original_word": row.get("Original word", ""),
            "original_stem": row.get("Original stem", ""),
            "original_context": _truncate(row.get("Original context", ""), 1200),
            "original_book_title": row.get("Original book_title", ""),
            "original_authors": row.get("Original authors", ""),
            "mechanical_importance": row.get("Importance 0-10", ""),
            "mechanical_note": row.get("Importance note", ""),
            "mechanical_tags": row.get("Tags", ""),
        },
        "local_analysis": {
            "pos": (analysis or {}).get("pos", ""),
            "frequencies": (analysis or {}).get("frequencies", {}),
            "warnings": (analysis or {}).get("warnings", {}),
            "proper_noun": (analysis or {}).get("proper_noun", False),
            "wordnet_selected_definition": wordnet.get("selected_definition", ""),
            "wordnet_sample_definitions": wordnet.get("sample_definitions", []),
            "wordnet_synset_count": wordnet.get("synset_count", 0),
            "wordnet_pos_count": wordnet.get("pos_count", 0),
            "importance_parts": importance.get("parts", {}),
            "genre": (analysis or {}).get("genre", {}),
        },
    }


def _validate_enrichment(data: dict[str, Any]) -> dict[str, Any]:
    logger.debug("Validating LLM enrichment keys=%s", sorted(data))
    required = {
        "word",
        "base_form",
        "russian_meanings",
        "generated_context_sentence_en",
        "generated_context_sentence_ru",
        "importance_0_10",
        "importance_note",
        "tags",
    }
    missing = sorted(required - set(data))
    if missing:
        logger.warning("LLM enrichment JSON missing keys=%s", missing)
        raise LLMEnrichmentError(f"model JSON is missing keys: {', '.join(missing)}")
    score = int(data["importance_0_10"])
    if score < 0 or score > 10:
        logger.warning("LLM enrichment score out of range score=%s", score)
        raise LLMEnrichmentError("importance_0_10 must be between 0 and 10")
    data["importance_0_10"] = score
    if isinstance(data["tags"], str):
        data["tags"] = [data["tags"]]
    if not isinstance(data["tags"], list):
        data["tags"] = []
    return data


def _apply_enrichment(row: dict[str, str], enrichment: dict[str, Any]) -> None:
    row["Word"] = _clean_text(enrichment.get("word")) or row.get("Word", "")
    row["Base form"] = _clean_text(enrichment.get("base_form")) or row.get("Base form", "")
    row["Russian meaning(s)"] = _clean_text(enrichment.get("russian_meanings"))
    row["Generated context sentence EN"] = _clean_text(enrichment.get("generated_context_sentence_en"))
    row["Generated context sentence RU"] = _clean_text(enrichment.get("generated_context_sentence_ru"))
    row["Importance 0-10"] = str(enrichment["importance_0_10"])
    row["Importance note"] = _clean_text(enrichment.get("importance_note"))
    row["Tags"] = _merge_tags(row.get("Tags", ""), enrichment.get("tags", []))


def _needs_enrichment(row: dict[str, str]) -> bool:
    return any(not str(row.get(field) or "").strip() for field in LLM_FILLED_FIELDS)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    logger.info("Reading optimized TSV path=%s", path)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        rows = [dict(row) for row in reader]
    for row in rows:
        for header in OPTIMIZED_TSV_HEADER:
            row.setdefault(header, "")
    logger.info("Read optimized TSV path=%s rows=%d", path, len(rows))
    return rows


def _write_tsv_atomic(path: Path, rows: list[dict[str, str]]) -> None:
    logger.info("Writing enriched TSV atomically path=%s rows=%d", path, len(rows))
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        delete=False,
        dir=path.parent,
        suffix=".tmp",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=OPTIMIZED_TSV_HEADER,
            delimiter="\t",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)
        temporary = Path(file.name)
    temporary.replace(path)
    logger.info("Wrote enriched TSV path=%s rows=%d", path, len(rows))


def _read_analysis(row: dict[str, str], analysis_dir: Path | None) -> dict[str, Any] | None:
    if analysis_dir is None:
        logger.debug("No analysis dir configured for row word=%s", row.get("Word"))
        return None
    key = row.get("Base form") or row.get("Word") or ""
    path = analysis_dir / f"{_safe_analysis_name(key)}.json"
    if not path.exists():
        logger.debug("Analysis JSON not found word=%s path=%s", row.get("Word"), path)
        return None
    logger.debug("Reading analysis JSON word=%s path=%s", row.get("Word"), path)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_analysis_enrichment(key: str, analysis_dir: Path | None, enrichment: dict[str, Any]) -> None:
    if analysis_dir is None:
        logger.debug("No analysis dir configured; skipping LLM enrichment audit key=%s", key)
        return
    path = analysis_dir / f"{_safe_analysis_name(key)}.json"
    if not path.exists():
        logger.debug("Analysis JSON missing; skipping LLM enrichment audit key=%s path=%s", key, path)
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    data["llm_enrichment"] = {
        "model": os.environ.get("DSLAB_MODEL", DEFAULT_DSLAB_MODEL),
        "fields": {key: value for key, value in enrichment.items() if not key.startswith("_")},
        "reasoning_excerpt": _truncate(enrichment.get("_reasoning_content", ""), 1200),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    logger.debug("Wrote LLM enrichment audit key=%s path=%s", key, path)


def _safe_analysis_name(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "_", value.casefold()).strip("_") or "word"


def _merge_tags(existing: str, llm_tags: list[Any]) -> str:
    tags = [tag for tag in existing.split() if tag]
    for tag in llm_tags:
        cleaned = re.sub(r"[^a-z0-9_]+", "_", str(tag).casefold()).strip("_")
        if cleaned:
            tags.append(f"llm_{cleaned}")
    return " ".join(dict.fromkeys(tags))


def _append_tag(existing: str, tag: str) -> str:
    tags = [item for item in existing.split() if item]
    tags.append(tag)
    return " ".join(dict.fromkeys(tags))


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _truncate(value: str | None, limit: int) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _compact_answer(enrichment: dict[str, Any]) -> str:
    meanings = _clean_text(enrichment.get("russian_meanings"))
    context = _clean_text(enrichment.get("generated_context_sentence_en"))
    note = _clean_text(enrichment.get("importance_note"))
    parts = [part for part in [meanings, context, note] if part]
    return " · ".join(parts)


def _emit_progress(
    callback: Callable[[dict[str, Any]], None] | None,
    payload: dict[str, Any],
) -> None:
    if callback is not None:
        callback(payload)


def _load_env_file_without_dependency(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", maxsplit=1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")
