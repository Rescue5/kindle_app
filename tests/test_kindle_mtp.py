from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kindle_vocab_app import kindle_device, kindle_mtp


def _vocab_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        for table in ("WORDS", "LOOKUPS", "BOOK_INFO"):
            connection.execute(f"CREATE TABLE {table} (id TEXT)")


class FakeSession:
    def __init__(self, source: Path, *, kindled: bool = True, partial: bool = False):
        self.source = source
        self.kindled = kindled
        self.partial = partial
        self.calls: list[str] = []

    def call(self, action: str):
        self.calls.append(action)
        if action == "Initialize":
            return {
                "usbDeviceInfo": {
                    "IdVendor": kindle_mtp.AMAZON_VENDOR_ID if self.kindled else 0x05AC,
                    "Product": "Kindle" if self.kindled else "Phone",
                }
            }
        if action == "FetchStorages":
            return [{"Sid": 7}]
        if action == "Dispose":
            return None
        raise AssertionError(action)

    def walk(self, storage_id: int, path: str):
        assert storage_id == 7
        if path == "/system/vocabulary":
            return [{"path": "/system/vocabulary/vocab.db", "size": self.source.stat().st_size,
                     "isFolder": False}]
        if path == "/system/thumbnails":
            return []
        if path == "/":
            return []
        raise AssertionError(path)

    def download(self, storage_id: int, sources: list[str], destination: Path):
        assert storage_id == 7
        assert sources == ["/system/vocabulary/vocab.db"]
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.source, destination / "vocab.db")
        if self.partial:
            with (destination / "vocab.db").open("r+b") as output:
                output.truncate(1)


class MacKindleMtpTests(unittest.TestCase):
    def test_usb_identity_filters_amazon_kindle_without_storage_access(self) -> None:
        tree = [
            {"idVendor": 0x05AC, "USB Product Name": "Phone", "IORegistryEntryChildren": []},
            {"idVendor": kindle_mtp.AMAZON_VENDOR_ID,
             "USB Product Name": "Kindle Paperwhite", "idProduct": 39297,
             "IORegistryEntryID": 123, "IORegistryEntryChildren": []},
        ]
        self.assertEqual(kindle_mtp.kindle_usb_identity(tree), ("mac-mtp", "39297", "123"))
        self.assertIsNone(kindle_mtp.kindle_usb_identity([
            {"idVendor": kindle_mtp.AMAZON_VENDOR_ID, "USB Product Name": "Fire Tablet"},
            {"idVendor": 0x05AC, "USB Product Name": "Kindle lookalike"},
        ]))
        with (
            patch.object(kindle_device.sys, "platform", "darwin"),
            patch.object(kindle_device, "mounted_volume_roots", return_value=[]),
            patch.object(kindle_mtp, "mac_kindle_identity", return_value=("mac-mtp", "39297", "123")),
            patch.object(kindle_mtp, "KalamSession", side_effect=AssertionError("storage opened")),
        ):
            presence = kindle_device.find_kindle_presence()
        self.assertIsNotNone(presence)
        assert presence is not None
        self.assertEqual(presence.signature, ("mac-mtp", "39297", "123"))

    def test_sync_rejects_other_device_before_walking_storage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.db"
            _vocab_database(source)
            session = FakeSession(source, kindled=False)
            with self.assertRaisesRegex(RuntimeError, "другое устройство"):
                kindle_mtp.sync_session(session, root / "cache")
            self.assertEqual(session.calls, ["Initialize", "Dispose"])
            self.assertFalse((root / "cache" / "vocab.db").exists())

    def test_incomplete_download_keeps_previous_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.db"
            _vocab_database(source)
            cache = root / "cache"
            cache.mkdir()
            target = cache / "vocab.db"
            target.write_bytes(b"previous-good-cache")
            session = FakeSession(source, partial=True)
            with self.assertRaisesRegex(RuntimeError, "не полностью"):
                kindle_mtp.sync_session(session, cache)
            self.assertEqual(target.read_bytes(), b"previous-good-cache")
            self.assertEqual(session.calls[-1], "Dispose")

    def test_valid_download_replaces_cache_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.db"
            _vocab_database(source)
            cache = root / "cache"
            cache.mkdir()
            (cache / "vocab.db").write_bytes(b"old")
            summary = kindle_mtp.sync_session(FakeSession(source), cache)
            self.assertEqual(summary["vocab_bytes"], source.stat().st_size)
            self.assertEqual((cache / "vocab.db").read_bytes(), source.read_bytes())

    def test_worker_timeout_and_invalid_json_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            with (
                patch.object(kindle_mtp, "kalam_library_path", return_value=Path("/fake/kalam.dylib")),
                patch.object(kindle_mtp.subprocess, "run",
                             side_effect=subprocess.TimeoutExpired(["python"], 120)),
            ):
                with self.assertRaises(TimeoutError):
                    kindle_mtp.copy_mac_vocab(cache)
            with (
                patch.object(kindle_mtp, "kalam_library_path", return_value=Path("/fake/kalam.dylib")),
                patch.object(kindle_mtp.subprocess, "run",
                             return_value=subprocess.CompletedProcess(["python"], 1, stdout="diagnostic", stderr="")),
            ):
                with self.assertRaisesRegex(RuntimeError, "MTP"):
                    kindle_mtp.copy_mac_vocab(cache)
            with (
                patch.object(kindle_mtp, "kalam_library_path", return_value=Path("/fake/kalam.dylib")),
                patch.object(kindle_mtp.subprocess, "run",
                             return_value=subprocess.CompletedProcess(["python"], 1,
                                 stdout=json.dumps({"ok": False, "error": "USB busy"}), stderr="")),
            ):
                with self.assertRaisesRegex(RuntimeError, "USB busy"):
                    kindle_mtp.copy_mac_vocab(cache)

    def test_thumbnail_paths_stay_inside_cache(self) -> None:
        good = {"name": "thumbnail_12.jpg", "path": "/system/thumbnails/thumbnail_12.jpg",
                "size": 100, "isFolder": False}
        self.assertTrue(kindle_mtp.safe_thumbnail(good))
        for bad in (
            {**good, "name": "../thumbnail_12.jpg"},
            {**good, "path": "/system/vocabulary/thumbnail_12.jpg"},
            {**good, "size": kindle_mtp.MAX_THUMBNAIL_BYTES + 1},
            {**good, "isFolder": True},
        ):
            self.assertFalse(kindle_mtp.safe_thumbnail(bad))


if __name__ == "__main__":
    unittest.main()
