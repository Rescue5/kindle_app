from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import string
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wordfreq import zipf_frequency

from kindle_vocab_app.genre_config import ProcessingConfig, load_processing_config
from kindle_vocab_app.processing_state import ProcessedSnapshot, utc_now
from kindle_vocab_app.tsv_schema import OPTIMIZED_TSV_HEADER


A1_AND_FUNCTION_WORDS = {
    "a",
    "about",
    "after",
    "again",
    "all",
    "also",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "but",
    "by",
    "can",
    "come",
    "could",
    "day",
    "do",
    "does",
    "down",
    "for",
    "from",
    "get",
    "go",
    "good",
    "had",
    "has",
    "have",
    "he",
    "her",
    "here",
    "him",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "know",
    "like",
    "look",
    "make",
    "man",
    "me",
    "more",
    "my",
    "new",
    "no",
    "not",
    "now",
    "of",
    "on",
    "one",
    "or",
    "our",
    "out",
    "over",
    "people",
    "said",
    "say",
    "see",
    "she",
    "so",
    "some",
    "take",
    "than",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "thing",
    "this",
    "time",
    "to",
    "too",
    "up",
    "us",
    "very",
    "was",
    "we",
    "well",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "will",
    "with",
    "would",
    "you",
    "your",
}

PHRASAL_EXPRESSIONS = {
    "back up",
    "break down",
    "bring up",
    "carry on",
    "carry out",
    "come across",
    "come up",
    "figure out",
    "find out",
    "get away",
    "get back",
    "get in",
    "get out",
    "give in",
    "give up",
    "go on",
    "hold on",
    "keep up",
    "look after",
    "look up",
    "make up",
    "pick up",
    "put down",
    "put off",
    "put on",
    "run into",
    "set up",
    "take off",
    "take over",
    "turn out",
}

ARCHAIC_MARKERS = {"obsolete", "archaic", "rare", "dated", "dialectal", "nonstandard"}
REGISTER_MARKERS = {"slang", "vulgar"}
SPECIALIZED_LEXNAMES = {
    "noun.artifact",
    "noun.cognition",
    "noun.communication",
    "noun.process",
    "noun.substance",
}


@dataclass(frozen=True)
class OptimizationResult:
    output_dir: Path
    tsv_path: Path
    analysis_dir: Path
    snapshot_path: Path
    processed_new: int
    accepted_new: int
    skipped_existing: int
    rejected_new: int


def optimize_entries(
    entries: list[dict[str, Any]],
    output_dir: Path,
    snapshot_path: Path,
    *,
    config_path: Path | None = None,
) -> OptimizationResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir = output_dir / "word_analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = output_dir / "optimized.tsv"
    snapshot = ProcessedSnapshot.load(snapshot_path)
    config = load_processing_config(config_path)

    analyses: list[dict[str, Any]] = []
    skipped_existing = 0
    rejected_new = 0

    candidates = [_candidate_from_entry(entry) for entry in entries]
    candidates = [candidate for candidate in candidates if candidate is not None]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[str(candidate["lexical_key"])].append(candidate)
        snapshot.remember_occurrence(
            occurrence_fingerprint(candidate["entry"]),
            {
                "word": candidate["normalized_word"],
                "base_form": candidate["base_form"],
                "book_title": candidate["entry"].get("book_title") or "",
            },
        )

    for lexical_key, group in sorted(grouped.items()):
        if snapshot.has_processed(lexical_key):
            skipped_existing += 1
            continue

        analysis = _analyze_group(lexical_key, group, config)
        analyses.append(analysis)
        if not analysis["accepted"]:
            rejected_new += 1
        snapshot.remember_processed(
            lexical_key,
            {
                "accepted": analysis["accepted"],
                "importance": analysis["importance"]["score"],
                "base_form": analysis["base_form"],
                "word": analysis["word"],
                "source_occurrence_count": analysis["source_occurrence_count"],
            },
        )
        _write_analysis_json(analysis_dir, lexical_key, analysis)

    accepted = [analysis for analysis in analyses if analysis["accepted"]]
    if analyses or not tsv_path.exists():
        _write_optimized_tsv(tsv_path, accepted)
    snapshot.save()

    return OptimizationResult(
        output_dir=output_dir,
        tsv_path=tsv_path,
        analysis_dir=analysis_dir,
        snapshot_path=snapshot_path,
        processed_new=len(analyses),
        accepted_new=len(accepted),
        skipped_existing=skipped_existing,
        rejected_new=rejected_new,
    )


def seed_snapshot_from_optimized_tsv(snapshot_path: Path, tsv_path: Path) -> int:
    snapshot = ProcessedSnapshot.load(snapshot_path)
    added = 0
    with tsv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        for row in reader:
            base_form = normalize_word(row.get("Base form") or row.get("Word") or "")
            if not base_form or snapshot.has_processed(base_form):
                continue
            snapshot.remember_processed(
                base_form,
                {
                    "accepted": True,
                    "importance": _safe_int(row.get("Importance 0-10")),
                    "base_form": base_form,
                    "word": normalize_word(row.get("Word") or base_form),
                    "source_occurrence_count": _safe_int(row.get("Source occurrence count")),
                    "seeded_from": str(tsv_path),
                },
            )
            added += 1
    snapshot.save()
    return added


def occurrence_fingerprint(entry: dict[str, Any]) -> str:
    raw = "\n".join(
        str(entry.get(key) or "")
        for key in ["word", "stem", "context", "book_title", "authors", "looked_up_at"]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _candidate_from_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    raw_word = str(entry.get("word") or "").strip()
    context = str(entry.get("context") or "")
    normalized = normalize_word(raw_word)
    if not normalized:
        return None

    phrasal = detect_phrasal_expression(normalized, context)
    pos_tag = detect_pos(normalized, context)
    stem_hint = normalize_word(str(entry.get("stem") or ""))
    base_form = phrasal or choose_base_form(normalized, stem_hint, pos_tag)
    lexical_key = base_form.casefold()
    return {
        "entry": entry,
        "raw_word": raw_word,
        "normalized_word": normalized,
        "base_form": base_form,
        "lexical_key": lexical_key,
        "pos_tag": pos_tag,
        "phrasal_expression": phrasal,
    }


def normalize_word(value: str) -> str:
    text = value.strip().replace("’", "'").replace("`", "'").replace("–", "-").replace("—", "-")
    text = text.strip(string.whitespace + string.punctuation + "“”‘’«»…")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^[^A-Za-z]+|[^A-Za-z]+$", "", text)
    if not text:
        return ""
    text = text.casefold()
    text = re.sub(r"[^a-z'\- ]", "", text)
    text = re.sub(r"'{2,}", "'", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("'- ")


def detect_pos(word: str, context: str) -> str:
    try:
        import nltk

        tokens = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", context)
        if tokens:
            tagged = nltk.pos_tag(tokens)
            for token, tag in tagged:
                if normalize_word(token) == word:
                    return _treebank_to_wordnet_pos(tag)
    except Exception:
        pass

    if word.endswith("ly"):
        return "r"
    if word.endswith(("ous", "ful", "able", "ible", "al", "ive", "less")):
        return "a"
    if word.endswith(("ed", "ing", "en", "ify", "ise", "ize")):
        return "v"
    return "n"


def lemmatize_word(word: str, pos: str) -> str:
    try:
        from nltk.corpus import wordnet as wn

        lemma = wn.morphy(word, pos=pos) or wn.morphy(word)
        if lemma:
            return lemma.replace("_", " ")
    except Exception:
        pass

    if pos == "v":
        return _rule_based_verb_lemma(word)
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def choose_base_form(word: str, stem_hint: str, pos: str) -> str:
    if stem_hint and stem_hint != word and is_plausible_english_lexeme(stem_hint):
        return stem_hint
    return lemmatize_word(word, pos)


def detect_phrasal_expression(word: str, context: str) -> str | None:
    tokens = [normalize_word(token) for token in re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", context)]
    tokens = [token for token in tokens if token]
    matches = [index for index, token in enumerate(tokens) if token == word]
    for index in matches:
        for size in (3, 2):
            for start in range(max(0, index - size + 1), min(index + 1, len(tokens) - size + 1)):
                phrase = " ".join(tokens[start : start + size])
                if phrase in PHRASAL_EXPRESSIONS:
                    return phrase
    return None


def _analyze_group(
    lexical_key: str,
    group: list[dict[str, Any]],
    config: ProcessingConfig,
) -> dict[str, Any]:
    representative = _choose_representative(group)
    entry = representative["entry"]
    word = str(representative["normalized_word"])
    base_form = str(representative["base_form"])
    context = str(entry.get("context") or "")
    pos = str(representative["pos_tag"])
    wordnet = wordnet_features(base_form, pos, context)
    frequencies = {
        "lemma_zipf": zipf_frequency(base_form, "en"),
        "form_zipf": zipf_frequency(word, "en"),
    }
    warnings = detect_warnings(word, base_form, context, wordnet)
    proper_noun = is_probable_proper_noun(str(entry.get("word") or ""), context, wordnet)
    genre = genre_features(entry, wordnet, config)
    score, score_parts = score_importance(
        word=word,
        base_form=base_form,
        frequencies=frequencies,
        wordnet=wordnet,
        warnings=warnings,
        proper_noun=proper_noun,
        genre=genre,
    )
    accepted = score >= 2 and not warnings.get("non_english") and not warnings.get("non_word")
    if word in A1_AND_FUNCTION_WORDS or base_form in A1_AND_FUNCTION_WORDS:
        accepted = False
        warnings["too_basic"] = True

    tags = build_tags(score, entry, representative, warnings, proper_noun, genre)
    occurrence_count = len(group)
    source_forms = sorted({str(item["entry"].get("word") or item["normalized_word"]) for item in group})

    return {
        "schema_version": 1,
        "processed_at": utc_now(),
        "accepted": accepted,
        "lexical_key": lexical_key,
        "word": word,
        "base_form": base_form,
        "pos": pos,
        "phrasal_expression": representative.get("phrasal_expression"),
        "frequencies": frequencies,
        "wordnet": wordnet,
        "wiktionary": wiktionary_features(),
        "genre": genre,
        "proper_noun": proper_noun,
        "warnings": warnings,
        "importance": {
            "score": score,
            "note": importance_note(score, wordnet, warnings, proper_noun),
            "parts": score_parts,
        },
        "source_word_forms": source_forms,
        "source_occurrence_count": occurrence_count,
        "representative_entry": entry,
        "tsv_row": optimized_row(
            word=word,
            base_form=base_form,
            score=score,
            note=importance_note(score, wordnet, warnings, proper_noun),
            tags=tags,
            source_forms=source_forms,
            occurrence_count=occurrence_count,
            entry=entry,
        ),
    }


def wordnet_features(base_form: str, pos: str, context: str) -> dict[str, Any]:
    try:
        from nltk.corpus import wordnet as wn
        from nltk.wsd import lesk

        synsets = wn.synsets(base_form, pos=pos) or wn.synsets(base_form)
        selected = lesk(context.split(), base_form, pos=pos) if context else None
        if selected is None and synsets:
            selected = synsets[0]
        lexnames = sorted({synset.lexname() for synset in synsets})
        pos_set = sorted({synset.pos() for synset in synsets})
        definitions = [synset.definition() for synset in synsets[:5]]
        return {
            "available": True,
            "synset_count": len(synsets),
            "pos_count": len(pos_set),
            "lexnames": lexnames,
            "selected_synset": selected.name() if selected else "",
            "selected_definition": selected.definition() if selected else "",
            "sample_definitions": definitions,
        }
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
            "synset_count": 0,
            "pos_count": 0,
            "lexnames": [],
            "selected_synset": "",
            "selected_definition": "",
            "sample_definitions": [],
        }


def wiktionary_features() -> dict[str, Any]:
    return {
        "available": False,
        "register_labels": [],
        "domain_categories": [],
        "note": "Локальный Wiktionary/Wiktextract индекс не подключен к проекту.",
    }


def detect_warnings(
    word: str,
    base_form: str,
    context: str,
    wordnet: dict[str, Any],
) -> dict[str, Any]:
    warnings: dict[str, Any] = {}
    if not re.fullmatch(r"[a-z]+(?:['\- ][a-z]+)*", word):
        warnings["unusual_characters"] = True
    if re.search(r"([a-z])\1\1", word):
        warnings["repeated_letters"] = True
    if not re.search(r"[a-z]", word) or len(word) <= 1:
        warnings["non_word"] = True
    if re.search(r"[^A-Za-z0-9\\s.,;:!?\"'()\\-—–“”‘’]", context):
        warnings["context_has_unusual_symbols"] = True
    if _looks_non_english(word, base_form):
        warnings["non_english"] = True
    if _looks_glued(word):
        warnings["possibly_glued_words"] = True
    if wordnet.get("available") is False:
        warnings["wordnet_unavailable"] = wordnet.get("error", "")
    if wordnet.get("available") and not wordnet.get("synset_count") and zipf_frequency(base_form, "en") == 0:
        warnings["unknown_to_local_lexicons"] = True
    return warnings


def score_importance(
    *,
    word: str,
    base_form: str,
    frequencies: dict[str, float],
    wordnet: dict[str, Any],
    warnings: dict[str, Any],
    proper_noun: bool,
    genre: dict[str, Any],
) -> tuple[int, dict[str, float]]:
    lemma_zipf = float(frequencies["lemma_zipf"])
    form_zipf = float(frequencies["form_zipf"])
    score = 0.0

    if lemma_zipf >= 5.0:
        score = 9.0
    elif lemma_zipf >= 4.2:
        score = 8.0
    elif lemma_zipf >= 3.5:
        score = 6.5
    elif lemma_zipf >= 2.8:
        score = 4.5
    elif lemma_zipf >= 2.0:
        score = 2.5
    else:
        score = 1.0

    form_gap = max(0.0, lemma_zipf - form_zipf)
    form_bonus = min(1.0, form_gap * 0.25)
    polysemy_bonus = min(1.0, math.log1p(int(wordnet.get("synset_count") or 0)) * 0.25)
    pos_bonus = min(0.8, max(0, int(wordnet.get("pos_count") or 0) - 1) * 0.25)
    phrase_bonus = 0.7 if " " in base_form else 0.0
    genre_bonus = 0.5 if genre.get("preferred_match") else 0.0
    specialized_penalty = -0.7 if genre.get("specialized") and not genre.get("preferred_match") else 0.0
    serious_warnings = {
        "unusual_characters",
        "repeated_letters",
        "non_word",
        "non_english",
        "unknown_to_local_lexicons",
        "possibly_glued_words",
    }
    warning_penalty = -1.5 if serious_warnings & set(warnings) else 0.0

    score += form_bonus + polysemy_bonus + pos_bonus + phrase_bonus + genre_bonus
    score += specialized_penalty + warning_penalty

    if base_form in A1_AND_FUNCTION_WORDS or word in A1_AND_FUNCTION_WORDS:
        score = min(score, 1.0)
    if proper_noun:
        score = min(score, 3.0)
    if warnings.get("unknown_to_local_lexicons") or warnings.get("possibly_glued_words"):
        score = min(score, 1.0)
    if warnings.get("non_english") or warnings.get("non_word"):
        score = 0.0

    parts = {
        "lemma_frequency_base": lemma_zipf,
        "form_frequency": form_zipf,
        "form_gap_bonus": form_bonus,
        "polysemy_bonus": polysemy_bonus,
        "pos_bonus": pos_bonus,
        "phrase_bonus": phrase_bonus,
        "genre_bonus": genre_bonus,
        "specialized_penalty": specialized_penalty,
        "warning_penalty": warning_penalty,
    }
    return max(0, min(10, round(score))), parts


def genre_features(
    entry: dict[str, Any],
    wordnet: dict[str, Any],
    config: ProcessingConfig,
) -> dict[str, Any]:
    title = str(entry.get("book_title") or "")
    configured = set(config.book_genres.get(title, ()))
    lexnames = set(wordnet.get("lexnames") or [])
    specialized = bool(lexnames & SPECIALIZED_LEXNAMES)
    preferred_match = bool(configured & set(config.preferred_categories))
    return {
        "book_genres": sorted(configured),
        "preferred_categories": list(config.preferred_categories),
        "preferred_match": preferred_match,
        "specialized": specialized,
        "specialized_lexnames": sorted(lexnames & SPECIALIZED_LEXNAMES),
    }


def is_probable_proper_noun(raw_word: str, context: str, wordnet: dict[str, Any]) -> bool:
    stripped = raw_word.strip(string.punctuation + "“”‘’")
    if not stripped or not stripped[0].isupper():
        return False
    if context.strip().startswith(stripped):
        return False
    return not bool(wordnet.get("synset_count"))


def build_tags(
    score: int,
    entry: dict[str, Any],
    representative: dict[str, Any],
    warnings: dict[str, Any],
    proper_noun: bool,
    genre: dict[str, Any],
) -> str:
    tags: list[str] = []
    if score >= 8:
        tags.append("priority_high")
    elif score >= 5:
        tags.append("priority_medium")
    elif score >= 2:
        tags.append("priority_low")
    else:
        tags.append("priority_skip")

    source = source_tag(str(entry.get("book_title") or "unknown"))
    tags.append(source)
    tags.append(f"pos_{representative['pos_tag']}")
    if representative.get("phrasal_expression"):
        tags.append("phrasal_expression")
    if proper_noun:
        tags.append("proper_noun")
    if genre.get("specialized"):
        tags.append("specialized")
    for warning in sorted(warnings):
        tags.append(f"warn_{warning}")
    return " ".join(tags)


def optimized_row(
    *,
    word: str,
    base_form: str,
    score: int,
    note: str,
    tags: str,
    source_forms: list[str],
    occurrence_count: int,
    entry: dict[str, Any],
) -> dict[str, str]:
    return {
        "Word": word,
        "Base form": base_form,
        "Russian meaning(s)": "",
        "Generated context sentence EN": "",
        "Generated context sentence RU": "",
        "Importance 0-10": str(score),
        "Importance note": note,
        "Tags": tags,
        "Source word forms": ", ".join(source_forms),
        "Source occurrence count": str(occurrence_count),
        "Original word": str(entry.get("word") or ""),
        "Original stem": str(entry.get("stem") or ""),
        "Original context": str(entry.get("context") or ""),
        "Original book_title": str(entry.get("book_title") or ""),
        "Original authors": str(entry.get("authors") or ""),
        "Original language": str(entry.get("language") or ""),
        "Original looked_up_at": str(entry.get("looked_up_at") or ""),
    }


def importance_note(
    score: int,
    wordnet: dict[str, Any],
    warnings: dict[str, Any],
    proper_noun: bool,
) -> str:
    if warnings.get("too_basic"):
        return "слишком базовое слово"
    if warnings.get("non_english"):
        return "не похоже на английское слово"
    if warnings.get("unknown_to_local_lexicons") or warnings.get("possibly_glued_words"):
        return "подозрительный токен"
    if proper_noun:
        return "вероятное имя собственное"
    parts = []
    if score >= 8:
        parts.append("частое и полезное")
    elif score >= 5:
        parts.append("умеренно полезное")
    elif score >= 2:
        parts.append("редкое, но возможно полезное")
    else:
        parts.append("низкая полезность")
    if int(wordnet.get("synset_count") or 0) >= 4:
        parts.append("многозначное")
    if int(wordnet.get("pos_count") or 0) >= 2:
        parts.append("несколько частей речи")
    return " и ".join(parts)


def source_tag(title: str) -> str:
    normalized = normalize_word(re.sub(r"\(.*?\)", "", title).replace(";", " "))
    tokens = [token for token in normalized.split() if token and token not in A1_AND_FUNCTION_WORDS]
    slug = "_".join(tokens[:4]) or "unknown"
    return f"source_{slug[:48]}"


def _write_optimized_tsv(path: Path, analyses: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=OPTIMIZED_TSV_HEADER, delimiter="\t")
        writer.writeheader()
        for analysis in analyses:
            writer.writerow(analysis["tsv_row"])


def _write_analysis_json(output_dir: Path, lexical_key: str, analysis: dict[str, Any]) -> None:
    safe_name = re.sub(r"[^a-z0-9._-]+", "_", lexical_key.casefold()).strip("_") or "word"
    path = output_dir / f"{safe_name}.json"
    path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _choose_representative(group: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        group,
        key=lambda item: (
            -len(str(item["entry"].get("context") or "")),
            str(item["entry"].get("looked_up_at") or ""),
        ),
    )[0]


def _treebank_to_wordnet_pos(tag: str) -> str:
    if tag.startswith("J"):
        return "a"
    if tag.startswith("V"):
        return "v"
    if tag.startswith("R"):
        return "r"
    return "n"


def _rule_based_verb_lemma(word: str) -> str:
    irregular = {
        "ate": "eat",
        "began": "begin",
        "begun": "begin",
        "bore": "bear",
        "borne": "bear",
        "brought": "bring",
        "came": "come",
        "drawn": "draw",
        "drew": "draw",
        "driven": "drive",
        "fell": "fall",
        "felt": "feel",
        "found": "find",
        "gave": "give",
        "gone": "go",
        "kept": "keep",
        "knew": "know",
        "lain": "lie",
        "leaned": "lean",
        "learnt": "learn",
        "left": "leave",
        "made": "make",
        "met": "meet",
        "ran": "run",
        "said": "say",
        "saw": "see",
        "seen": "see",
        "stood": "stand",
        "taken": "take",
        "told": "tell",
        "went": "go",
    }
    if word in irregular:
        return irregular[word]
    if word.endswith("ing") and len(word) > 5:
        root = word[:-3]
        if len(root) > 2 and root[-1] == root[-2]:
            root = root[:-1]
        return root
    if word.endswith("ed") and len(word) > 4:
        root = word[:-2]
        if root.endswith("i"):
            root = root[:-1] + "y"
        if len(root) > 2 and root[-1] == root[-2]:
            root = root[:-1]
        return root
    return word


def _looks_non_english(word: str, base_form: str) -> bool:
    if not re.fullmatch(r"[a-z]+(?:['\- ][a-z]+)*", word):
        return True
    if len(base_form) <= 1:
        return True
    if zipf_frequency(base_form, "en") > 0:
        return False
    if " " in base_form:
        return all(zipf_frequency(part, "en") > 0 for part in base_form.split())
    return False


def is_plausible_english_lexeme(value: str) -> bool:
    if not re.fullmatch(r"[a-z]+(?:['\- ][a-z]+)*", value):
        return False
    if zipf_frequency(value, "en") > 0:
        return True
    try:
        from nltk.corpus import wordnet as wn

        return bool(wn.synsets(value))
    except Exception:
        return False


def _looks_glued(word: str) -> bool:
    if len(word) < 11 or " " in word or "-" in word:
        return False
    try:
        import wordninja

        parts = wordninja.split(word)
        return len(parts) >= 2 and all(zipf_frequency(part, "en") >= 3.0 for part in parts)
    except Exception:
        return False


def _safe_int(value: object) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0
