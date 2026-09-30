"""Conservative Open Library cover lookup for the local book shelf.

Only explicit Kindle title and author metadata is searched. The module never
reads the vocabulary database, and cache reads never make network requests.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


logger = logging.getLogger(__name__)

SEARCH_ENDPOINT = "https://openlibrary.org/search.json"
COVER_HOST = "covers.openlibrary.org"
MAX_SEARCH_BYTES = 256_000
MAX_COVER_BYTES = 600_000
SEARCH_TIMEOUT_SECONDS = 7
COVER_TIMEOUT_SECONDS = 9
MISSING_TTL_SECONDS = 30 * 24 * 60 * 60
ERROR_TTL_SECONDS = 6 * 60 * 60
MAX_DOWNLOADS_PER_RUN = 40
REQUEST_PAUSE_SECONDS = 0.25
_USER_AGENT = "KindleCards/0.1 (personal local cover cache)"
_ALLOWED_HOSTS = {"openlibrary.org", COVER_HOST}
_THUMBNAIL_NAME = re.compile(r"^thumbnail_([A-Za-z0-9]{10})(?:_.+)?_portrait\.jpe?g$", re.IGNORECASE)
_SEARCH_VERSION = 4
_TRAILING_PARENS = re.compile(r"\s*\(([^()]*)\)\s*$")
_SERIES_PREFIX = re.compile(r"^(.+?)\s+([1-9]\d?)\s+(.+)$")
_PROVENANCE = re.compile(r"(?:z-library|z-lib|1lib)(?:\.[a-z]+)?", re.IGNORECASE)


class _HTTPSRedirects(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Request | None:
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or not _trusted_response_host(parsed.hostname):
            raise ValueError("Open Library redirected outside the trusted HTTPS hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = build_opener(_HTTPSRedirects())


def _trusted_response_host(host: str | None) -> bool:
    return host in {*_ALLOWED_HOSTS, "archive.org"} or bool(host and host.endswith(".us.archive.org"))


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _normalized(value: object) -> str:
    folded = unicodedata.normalize("NFKD", _clean(value).casefold())
    without_marks = "".join(char for char in folded if not unicodedata.combining(char))
    # Apostrophes are optional in book metadata: "Mirrors" and "Mirror’s".
    without_apostrophes = re.sub(r"['\u2018\u2019\u02bc]", "", without_marks)
    return " ".join(re.findall(r"[^\W_]+", without_apostrophes, flags=re.UNICODE))


def _author_key(value: object) -> tuple[str, ...]:
    # Kindle may store "Surname, Given" while Open Library stores "Given Surname".
    return tuple(sorted(_normalized(value).split()))


def _author_matches(left: object, right: object) -> bool:
    left_normalized = _normalized(left)
    right_normalized = _normalized(right)
    return bool(left_normalized and right_normalized) and (
        _author_key(left) == _author_key(right)
        or left_normalized.replace(" ", "") == right_normalized.replace(" ", "")
    )


def _search_author(authors: str) -> str:
    value = _clean(authors).rstrip(";")
    if value.count(",") == 1:
        surname, given = (_clean(part) for part in value.split(",", 1))
        if surname and given:
            value = f"{given} {surname}"
    return _clean(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value))


def clean_book_title(title: str, authors: str = "") -> str:
    """Remove known Kindle/file provenance while preserving the original record.

    This is a display/search helper; callers should keep the untouched Kindle
    title in occurrences for audit and context.
    """
    value = _clean(title)
    while value:
        parenthetical = _TRAILING_PARENS.search(value)
        if parenthetical:
            suffix = parenthetical.group(1).strip()
            if (
                _PROVENANCE.search(suffix)
                or re.fullmatch(r"\d{1,2}", suffix)
                or re.search(r"\bbook\s+\d+\b", suffix, re.IGNORECASE)
                or (authors and _author_matches(suffix, authors))
            ):
                value = value[:parenthetical.start()].rstrip()
                continue
        byline = re.search(r"\s+[-–—]\s+(.+?);?\s*$", value)
        if byline and authors and _author_matches(byline.group(1).rstrip(";"), authors):
            value = value[:byline.start()].rstrip()
            continue
        break
    return value or _clean(title)


def _search_titles(title: str, authors: str) -> list[str]:
    cleaned = clean_book_title(title, authors)
    titles = [cleaned]
    prefix = _SERIES_PREFIX.match(cleaned)
    if prefix:
        leading, _, trailing = prefix.groups()
        leading_terms = set(_normalized(leading).split()) - {"the", "a", "an", "of", "and"}
        trailing_terms = set(_normalized(trailing).split())
        if len(trailing_terms) >= 3 and leading_terms & trailing_terms:
            titles.append(trailing)
    return titles


def _identity(book: Mapping[str, object]) -> tuple[str, str, str]:
    return _clean(book.get("key")), _clean(book.get("title")), _clean(book.get("authors"))


def _cache_id(key: str, title: str, authors: str) -> str:
    payload = json.dumps([key, title, authors], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _paths(cache_dir: Path, key: str, title: str, authors: str) -> tuple[Path, Path]:
    stem = _cache_id(key, title, authors)
    return cache_dir / f"{stem}.json", cache_dir / f"{stem}.jpg"


def _read_metadata(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".cover-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_status(path: Path, status: str, *, cover_id: int | None = None, source: str | None = None) -> None:
    payload: dict[str, object] = {"status": status, "checked_at": time.time(), "search_version": _SEARCH_VERSION}
    if cover_id is not None:
        payload["cover_id"] = cover_id
    if source is not None:
        payload["source"] = source
    _write_atomic(path, json.dumps(payload, separators=(",", ":")).encode("utf-8"))


def _cached_image_is_valid(path: Path) -> bool:
    try:
        if path.stat().st_size > MAX_COVER_BYTES:
            return False
        with path.open("rb") as stream:
            return stream.read(3) == b"\xff\xd8\xff"
    except OSError:
        return False


def _request_bytes(url: str, *, timeout: int, limit: int, expected_type: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
        raise ValueError("Only the official Open Library HTTPS hosts are allowed")
    request = Request(url, headers={"User-Agent": _USER_AGENT, "Accept": expected_type})
    with _opener.open(request, timeout=timeout) as response:
        final_url = urlparse(response.geturl())
        if final_url.scheme != "https" or not _trusted_response_host(final_url.hostname):
            raise ValueError("Unexpected response host")
        content_type = response.headers.get_content_type()
        if content_type != expected_type:
            raise ValueError(f"Unexpected Open Library content type: {content_type}")
        declared_size = response.headers.get("Content-Length")
        if declared_size and int(declared_size) > limit:
            raise ValueError("Open Library response is too large")
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Open Library response is too large")
        return data


def _cover_id_for(title: str, authors: str) -> int | None:
    for search_title in _search_titles(title, authors):
        wanted_title = _normalized(search_title)
        search_author = _search_author(authors)
        queries = [{"title": search_title}]
        if search_author:
            queries[0]["author"] = search_author
        # Open Library's fielded title search can miss punctuation variants
        # (for example missing apostrophes). A broad query is safe because the
        # returned title and author still need exact local validation.
        queries.append({"q": f"{search_title} {search_author}".strip()})
        for query in queries:
            url = f"{SEARCH_ENDPOINT}?{urlencode({**query, 'fields': 'key,title,author_name,cover_i', 'limit': '5'})}"
            data = _request_bytes(url, timeout=SEARCH_TIMEOUT_SECONDS, limit=MAX_SEARCH_BYTES, expected_type="application/json")
            payload = json.loads(data)
            if not isinstance(payload, dict) or not isinstance(payload.get("docs"), list):
                raise ValueError("Invalid Open Library search response")
            candidates: dict[str, int] = {}
            for item in payload["docs"]:
                if not isinstance(item, dict) or _normalized(item.get("title")) != wanted_title:
                    continue
                candidate_authors = item.get("author_name")
                if authors and (
                    not isinstance(candidate_authors, list)
                    or not any(_author_matches(authors, candidate) for candidate in candidate_authors)
                ):
                    continue
                cover_id = item.get("cover_i")
                work_key = item.get("key")
                if isinstance(cover_id, int) and cover_id > 0 and isinstance(work_key, str) and work_key:
                    candidates[work_key] = cover_id
            if len(candidates) == 1:
                return next(iter(candidates.values()))
            if len(candidates) > 1:
                # Several exact works share this title/author; a fallback
                # query would only increase the chance of a wrong cover.
                return None
    return None


def attach_covers(books: Iterable[Mapping[str, object]], cache_dir: Path) -> list[dict[str, object]]:
    """Return book dictionaries enriched from cache, without accessing network."""
    cache_dir = Path(cache_dir)
    enriched: list[dict[str, object]] = []
    for book in books:
        result = dict(book)
        key, title, authors = _identity(book)
        result.pop("cover_data_url", None)
        if not key or not title:
            result["cover_status"] = "unavailable"
            enriched.append(result)
            continue
        metadata_path, image_path = _paths(cache_dir, key, title, authors)
        metadata = _read_metadata(metadata_path)
        status = metadata.get("status") if metadata else None
        if status == "available":
            try:
                image = image_path.read_bytes()
                if image.startswith(b"\xff\xd8\xff") and len(image) <= MAX_COVER_BYTES:
                    result["cover_data_url"] = "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")
                    result["cover_status"] = "available"
                else:
                    result["cover_status"] = "pending"
            except OSError:
                result["cover_status"] = "pending"
        elif status in {"missing", "error"}:
            result["cover_status"] = status
        else:
            result["cover_status"] = "pending"
        enriched.append(result)
    return enriched


def prefer_local_covers(
    books: Iterable[Mapping[str, object]], cache_dir: Path, local_thumbnail_dir: Path
) -> dict[str, int]:
    """Cache Kindle portrait thumbnails whose ASIN occurs in the book key."""
    cache_dir = Path(cache_dir)
    local_thumbnail_dir = Path(local_thumbnail_dir)
    summary = {"matched": 0, "copied": 0, "cached": 0, "errors": 0}
    if not local_thumbnail_dir.is_dir():
        return summary
    thumbnails: dict[str, list[Path]] = {}
    try:
        for path in local_thumbnail_dir.iterdir():
            match = _THUMBNAIL_NAME.match(path.name)
            if match and path.is_file():
                thumbnails.setdefault(match.group(1).upper(), []).append(path)
    except OSError:
        summary["errors"] += 1
        return summary
    for book in books:
        key, title, authors = _identity(book)
        if not key or not title:
            continue
        explicit_asin = _clean(book.get("asin")).upper()
        if explicit_asin and re.fullmatch(r"[A-Z0-9]{10}", explicit_asin):
            matching_asins = [explicit_asin] if explicit_asin in thumbnails else []
        else:
            matching_asins = [asin for asin in thumbnails if asin in key.upper()]
        if len(matching_asins) != 1:
            continue
        summary["matched"] += 1
        metadata_path, image_path = _paths(cache_dir, key, title, authors)
        metadata = _read_metadata(metadata_path)
        if metadata and metadata.get("status") == "available" and metadata.get("source") == "kindle" and _cached_image_is_valid(image_path):
            summary["cached"] += 1
            continue
        try:
            candidates = sorted(thumbnails[matching_asins[0]], key=lambda path: path.stat().st_size, reverse=True)
            image = None
            for candidate in candidates:
                if candidate.stat().st_size > MAX_COVER_BYTES:
                    continue
                data = candidate.read_bytes()
                if data.startswith(b"\xff\xd8\xff"):
                    image = data
                    break
            if image is None:
                raise ValueError("No valid local portrait JPEG")
            _write_atomic(image_path, image)
            _write_status(metadata_path, "available", source="kindle")
            summary["copied"] += 1
        except (OSError, ValueError) as error:
            logger.warning("Local cover cache failed for book key hash %s: %s", _cache_id(key, title, authors)[:12], type(error).__name__)
            summary["errors"] += 1
    return summary


def download_covers(
    books: Iterable[Mapping[str, object]], cache_dir: Path, *, local_thumbnail_dir: Path | None = None,
    retry_errors: bool = False,
) -> dict[str, int]:
    """Fetch a bounded batch of matching covers and cache misses/errors safely.

    The caller can run this after a successful Kindle sync. A cover failure is
    local to that book and never raises out of this function.
    """
    cache_dir = Path(cache_dir)
    books = list(books)
    local = prefer_local_covers(books, cache_dir, local_thumbnail_dir) if local_thumbnail_dir is not None else {"copied": 0, "cached": 0, "errors": 0}
    summary = {"attempted": 0, "downloaded": 0, "cached": 0, "missing": 0, "errors": local["errors"], "deferred": 0, "unavailable": 0, "local_copied": local["copied"], "local_cached": local["cached"]}
    seen: set[str] = set()
    for book in books:
        key, title, authors = _identity(book)
        if not key or not title:
            summary["unavailable"] += 1
            continue
        cache_id = _cache_id(key, title, authors)
        if cache_id in seen:
            continue
        seen.add(cache_id)
        metadata_path, image_path = _paths(cache_dir, key, title, authors)
        metadata = _read_metadata(metadata_path)
        status = metadata.get("status") if metadata else None
        checked_at = metadata.get("checked_at") if metadata else None
        age = time.time() - checked_at if isinstance(checked_at, (float, int)) else float("inf")
        if status == "available" and _cached_image_is_valid(image_path):
            summary["cached"] += 1
            continue
        cache_search_version = metadata.get("search_version") if metadata else None
        if status == "missing" and cache_search_version == _SEARCH_VERSION and age < MISSING_TTL_SECONDS:
            summary["missing"] += 1
            continue
        if status == "error" and not retry_errors and cache_search_version == _SEARCH_VERSION and age < ERROR_TTL_SECONDS:
            summary["errors"] += 1
            continue
        if summary["attempted"] >= MAX_DOWNLOADS_PER_RUN:
            summary["deferred"] += 1
            continue
        if summary["attempted"]:
            time.sleep(REQUEST_PAUSE_SECONDS)
        summary["attempted"] += 1
        try:
            cover_id = _cover_id_for(title, authors)
            if cover_id is None:
                _write_status(metadata_path, "missing")
                summary["missing"] += 1
                continue
            url = f"https://{COVER_HOST}/b/id/{cover_id}-M.jpg?default=false"
            image = _request_bytes(url, timeout=COVER_TIMEOUT_SECONDS, limit=MAX_COVER_BYTES, expected_type="image/jpeg")
            if not image.startswith(b"\xff\xd8\xff"):
                raise ValueError("Open Library returned an invalid JPEG")
            _write_atomic(image_path, image)
            _write_status(metadata_path, "available", cover_id=cover_id, source="openlibrary")
            summary["downloaded"] += 1
        except HTTPError as error:
            try:
                if error.code == 404:
                    _write_status(metadata_path, "missing")
                    summary["missing"] += 1
                    continue
                logger.warning("Cover lookup failed for book key hash %s: HTTP %s", cache_id[:12], error.code)
                _write_status(metadata_path, "error")
                summary["errors"] += 1
            except OSError:
                summary["errors"] += 1
        except Exception as error:  # Local metadata, network, and cache failures must not interrupt Kindle sync.
            logger.warning("Cover lookup failed for book key hash %s: %s", cache_id[:12], type(error).__name__)
            try:
                _write_status(metadata_path, "error")
            except OSError:
                pass
            summary["errors"] += 1
    return summary
