from __future__ import annotations

import json
import tempfile
import time
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from kindle_vocab_app import book_covers


BOOK = {"key": "amzn1:ebook:asin:B012345678", "title": "Dune", "authors": "Frank Herbert", "label": "Dune · Frank Herbert · 3"}
IMAGE = b"\xff\xd8\xff\xe0example jpeg bytes"


class _FakeResponse:
    def __init__(self, url: str, data: bytes, content_type: str = "image/jpeg") -> None:
        self.url = url
        self.data = data
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def geturl(self) -> str:
        return self.url

    def read(self, size: int) -> bytes:
        return self.data[:size]


class BookCoverTests(unittest.TestCase):
    def test_exact_open_library_match_is_cached_and_attached(self) -> None:
        search = {"docs": [
            {"key": "/works/wrong", "title": "Dune Messiah", "author_name": ["Frank Herbert"], "cover_i": 1},
            {"key": "/works/right", "title": "Dune", "author_name": ["Frank Herbert"], "cover_i": 42},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            with patch.object(book_covers, "_request_bytes", side_effect=[json.dumps(search).encode(), IMAGE]) as request:
                result = book_covers.download_covers([BOOK], cache)
            self.assertEqual(result["downloaded"], 1)
            self.assertEqual(request.call_count, 2)
            self.assertIn("title=Dune", request.call_args_list[0].args[0])
            self.assertIn("author=Frank+Herbert", request.call_args_list[0].args[0])
            self.assertIn("/b/id/42-M.jpg?default=false", request.call_args_list[1].args[0])
            with patch.object(book_covers, "_request_bytes", side_effect=AssertionError("network used")):
                attached = book_covers.attach_covers([BOOK], cache)
                cached = book_covers.download_covers([BOOK], cache)
            self.assertTrue(attached[0]["cover_data_url"].startswith("data:image/jpeg;base64,"))
            self.assertEqual(attached[0]["cover_status"], "available")
            self.assertEqual(cached["cached"], 1)

    def test_ambiguous_exact_work_is_negative_cached(self) -> None:
        search = {"docs": [
            {"key": "/works/a", "title": "Dune", "author_name": ["Frank Herbert"], "cover_i": 1},
            {"key": "/works/b", "title": "Dune", "author_name": ["Frank Herbert"], "cover_i": 2},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            with patch.object(book_covers, "_request_bytes", return_value=json.dumps(search).encode()) as request:
                first = book_covers.download_covers([BOOK], cache)
                second = book_covers.download_covers([BOOK], cache)
            self.assertEqual(first["missing"], 1)
            self.assertEqual(second["missing"], 1)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(book_covers.attach_covers([BOOK], cache)[0]["cover_status"], "missing")

    def test_same_title_with_different_author_is_not_accepted(self) -> None:
        search = {"docs": [{"key": "/works/wrong", "title": "Dune", "author_name": ["Another Author"], "cover_i": 42}]}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(book_covers, "_request_bytes", return_value=json.dumps(search).encode()) as request:
                result = book_covers.download_covers([BOOK], Path(directory))
            self.assertEqual(result["missing"], 1)
            self.assertEqual(request.call_count, 2)

    def test_reversed_author_name_can_match_exact_tokens(self) -> None:
        search = {"docs": [{"key": "/works/right", "title": "Dune", "author_name": ["Frank Herbert"], "cover_i": 42}]}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(book_covers, "_request_bytes", side_effect=[json.dumps(search).encode(), IMAGE]) as request:
                result = book_covers.download_covers([dict(BOOK, authors="Herbert, Frank")], Path(directory))
            self.assertEqual(result["downloaded"], 1)
            self.assertIn("author=Frank+Herbert", request.call_args_list[0].args[0])

    def test_kindle_metadata_suffixes_are_removed_for_exact_search(self) -> None:
        book = dict(BOOK, title="Golden Son (Red Rising Book 2)", authors="Brown, Pierce")
        search = {"docs": [{"key": "/works/right", "title": "Golden Son", "author_name": ["Pierce Brown"], "cover_i": 42}]}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(book_covers, "_request_bytes", side_effect=[json.dumps(search).encode(), IMAGE]) as request:
                result = book_covers.download_covers([book], Path(directory))
            self.assertEqual(result["downloaded"], 1)
            self.assertIn("title=Golden+Son", request.call_args_list[0].args[0])
            self.assertIn("author=Pierce+Brown", request.call_args_list[0].args[0])

    def test_provenance_author_byline_copy_and_apostrophe_normalization(self) -> None:
        self.assertEqual(book_covers.clean_book_title("Project Hail Mary - Andy Weir;", "AndyWeir"), "Project Hail Mary")
        self.assertEqual(
            book_covers.clean_book_title("The Mirrors Truth (Michael R. Fletcher) (z-library.sk, 1lib.sk, z-lib.sk)", "MichaelR.Fletcher"),
            "The Mirrors Truth",
        )
        self.assertEqual(book_covers.clean_book_title("Words of Radiance (1)", "Brandon Sanderson"), "Words of Radiance")
        self.assertEqual(book_covers._normalized("The Mirrors Truth"), book_covers._normalized("The Mirror’s Truth"))
        self.assertTrue(book_covers._author_matches("SatoshiYagisawa", "Satoshi Yagisawa"))

    def test_broad_query_recovers_punctuation_variant_but_still_requires_exact_match(self) -> None:
        book = dict(BOOK, title="The Mirrors Truth (Michael R. Fletcher) (z-library.sk)", authors="MichaelR.Fletcher")
        search = {"docs": [
            {"key": "/works/wrong", "title": "The Mirror's Truth: A Novel", "author_name": ["Michael R. Fletcher"], "cover_i": 1},
            {"key": "/works/right", "title": "The Mirror's Truth", "author_name": ["Michael R. Fletcher"], "cover_i": 42},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(book_covers, "_request_bytes", side_effect=[b'{"docs": []}', json.dumps(search).encode(), IMAGE]) as request:
                result = book_covers.download_covers([book], Path(directory))
            self.assertEqual(result["downloaded"], 1)
            self.assertIn("q=The+Mirrors+Truth", request.call_args_list[1].args[0])

    def test_numbered_prefix_uses_exact_author_matched_suffix_only(self) -> None:
        book = dict(BOOK, title="Morisaki Bookshop 1 Days at the Morisaki Bookshop (Satoshi Yagisawa) (z-library.sk)", authors="SatoshiYagisawa")
        search = {"docs": [{"key": "/works/right", "title": "Days at the Morisaki Bookshop", "author_name": ["Satoshi Yagisawa"], "cover_i": 42}]}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(book_covers, "_request_bytes", side_effect=[b'{"docs": []}', b'{"docs": []}', json.dumps(search).encode(), IMAGE]) as request:
                result = book_covers.download_covers([book], Path(directory))
            self.assertEqual(result["downloaded"], 1)
            self.assertIn("title=Morisaki+Bookshop+1+Days", request.call_args_list[0].args[0])
            self.assertIn("title=Days+at+the+Morisaki+Bookshop", request.call_args_list[2].args[0])

    def test_old_negative_cache_is_retried_after_search_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            metadata_path, _ = book_covers._paths(cache, BOOK["key"], BOOK["title"], BOOK["authors"])
            metadata_path.write_text(json.dumps({"status": "missing", "checked_at": time.time()}), encoding="utf-8")
            with patch.object(book_covers, "_request_bytes", return_value=b'{"docs": []}') as request:
                result = book_covers.download_covers([BOOK], cache)
            self.assertEqual(result["attempted"], 1)
            self.assertEqual(request.call_count, 2)

    def test_cover_404_becomes_a_cached_miss(self) -> None:
        search = {"docs": [{"key": "/works/right", "title": "Dune", "author_name": ["Frank Herbert"], "cover_i": 42}]}
        not_found = HTTPError("https://covers.openlibrary.org/b/id/42-M.jpg", 404, "Not Found", {}, None)
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            with patch.object(book_covers, "_request_bytes", side_effect=[json.dumps(search).encode(), not_found]) as request:
                first = book_covers.download_covers([BOOK], cache)
                second = book_covers.download_covers([BOOK], cache)
            self.assertEqual(first["missing"], 1)
            self.assertEqual(second["missing"], 1)
            self.assertEqual(request.call_count, 2)

    def test_network_error_is_local_and_cached_temporarily(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            with patch.object(book_covers, "_request_bytes", side_effect=TimeoutError("offline")) as request:
                result = book_covers.download_covers([BOOK, {"key": "", "label": "All books"}], cache)
                again = book_covers.download_covers([BOOK], cache)
            self.assertEqual(result["errors"], 1)
            self.assertEqual(result["unavailable"], 1)
            self.assertEqual(again["errors"], 1)
            self.assertEqual(request.call_count, 1)

    def test_manual_retry_rechecks_transient_error(self) -> None:
        search = {"docs": [{"key": "/works/right", "title": "Dune", "author_name": ["Frank Herbert"], "cover_i": 42}]}
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            with patch.object(book_covers, "_request_bytes", side_effect=[TimeoutError("offline"), json.dumps(search).encode(), IMAGE]) as request:
                first = book_covers.download_covers([BOOK], cache)
                retry = book_covers.download_covers([BOOK], cache, retry_errors=True)
            self.assertEqual(first["errors"], 1)
            self.assertEqual(retry["downloaded"], 1)
            self.assertEqual(request.call_count, 3)

    def test_cover_redirects_allow_only_trusted_https_archive_hosts(self) -> None:
        handler = book_covers._HTTPSRedirects()
        request = Request("https://covers.openlibrary.org/b/id/42-M.jpg")
        for url in (
            "https://archive.org/download/m_covers_0008/example.zip/cover.jpg",
            "https://ia800703.us.archive.org/view_archive.php?foo=bar",
        ):
            self.assertIsNotNone(handler.redirect_request(request, None, 302, "Found", {}, url))
        for url in (
            "http://archive.org/download/cover.jpg",
            "https://evilarchive.org/cover.jpg",
            "https://ia800703.us.archive.org.evil.test/cover.jpg",
            "https://archive.org.evil.test/cover.jpg",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.redirect_request(request, None, 302, "Found", {}, url)

    def test_cover_response_checks_final_host_and_content(self) -> None:
        url = "https://covers.openlibrary.org/b/id/42-M.jpg"
        trusted = _FakeResponse("https://ia800703.us.archive.org/view_archive.php", IMAGE)
        with patch.object(book_covers._opener, "open", return_value=trusted):
            self.assertEqual(book_covers._request_bytes(url, timeout=1, limit=100, expected_type="image/jpeg"), IMAGE)
        untrusted = _FakeResponse("https://evilarchive.org/cover.jpg", IMAGE)
        with patch.object(book_covers._opener, "open", return_value=untrusted), self.assertRaises(ValueError):
            book_covers._request_bytes(url, timeout=1, limit=100, expected_type="image/jpeg")

    def test_kindle_portrait_wins_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thumbnails = root / "kindle-thumbnails"
            thumbnails.mkdir()
            (thumbnails / "thumbnail_B012345678_large_portrait.jpg").write_bytes(IMAGE)
            (thumbnails / "thumbnail_B099999999_large_portrait.jpg").write_bytes(IMAGE)
            with patch.object(book_covers, "_request_bytes", side_effect=AssertionError("network used")):
                result = book_covers.download_covers([BOOK], root / "covers", local_thumbnail_dir=thumbnails)
            self.assertEqual(result["local_copied"], 1)
            self.assertEqual(result["attempted"], 0)
            attached = book_covers.attach_covers([BOOK], root / "covers")
            self.assertEqual(attached[0]["cover_status"], "available")

    def test_explicit_asin_matches_thumbnail_when_book_key_is_uuid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            thumbnails = root / "kindle-thumbnails"
            thumbnails.mkdir()
            (thumbnails / "thumbnail_B012345678_large_portrait.jpg").write_bytes(IMAGE)
            book = dict(BOOK, key="07c10ea5-6e0b-4d4d-8fcb-79f10eacbc32", asin="B012345678")
            with patch.object(book_covers, "_request_bytes", side_effect=AssertionError("network used")):
                result = book_covers.download_covers([book], root / "covers", local_thumbnail_dir=thumbnails)
            self.assertEqual(result["local_copied"], 1)
            self.assertEqual(result["attempted"], 0)

    def test_request_batch_is_bounded(self) -> None:
        books = [dict(BOOK, key=f"book-{index}", title=f"Title {index}") for index in range(3)]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(book_covers, "MAX_DOWNLOADS_PER_RUN", 1), patch.object(book_covers, "_request_bytes", return_value=b'{"docs": []}'):
                result = book_covers.download_covers(books, Path(directory))
            self.assertEqual(result["attempted"], 1)
            self.assertEqual(result["deferred"], 2)


if __name__ == "__main__":
    unittest.main()
