"""Read-only macOS MTP access using the signed OpenMTP Kalam runtime.

Native USB work runs in a disposable subprocess: a stalled USB connection or
native failure must not stall the desktop bridge or corrupt its cached database.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

AMAZON_VENDOR_ID = 0x1949
MAX_VOCAB_BYTES = 256 * 1024 * 1024
MAX_THUMBNAIL_BYTES = 1024 * 1024


def kindle_usb_identity(tree: Any) -> tuple[str, ...] | None:
    """Inspect USB identity only; do not open a device session or its storage."""
    if isinstance(tree, list):
        for item in tree:
            identity = kindle_usb_identity(item)
            if identity:
                return identity
    elif isinstance(tree, dict):
        if tree.get("idVendor") == AMAZON_VENDOR_ID and "kindle" in str(tree.get("USB Product Name", "")).casefold():
            return ("mac-mtp", str(tree.get("idProduct", "")), str(tree.get("IORegistryEntryID", "")))
        return kindle_usb_identity(tree.get("IORegistryEntryChildren", []))
    return None


def mac_kindle_identity() -> tuple[str, ...] | None:
    try:
        result = subprocess.run(["/usr/sbin/ioreg", "-p", "IOUSB", "-a", "-l"], capture_output=True, timeout=5, check=True)
        return kindle_usb_identity(plistlib.loads(result.stdout))
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException, ValueError):
        return None


def kalam_library_path() -> Path:
    architecture = "arm64" if platform.machine() == "arm64" else "amd64"
    roots = [Path("/Applications"), Path.home() / "Applications"]
    for root in roots:
        path = root / "OpenMTP.app" / "Contents" / "Resources" / "bin" / architecture / "kalam.dylib"
        if path.is_file():
            return path
    raise RuntimeError("Для Kindle по MTP установите OpenMTP в папку Applications: https://openmtp.ganeshrvel.com")


def copy_mac_vocab(cache_dir: Path) -> Path:
    import fcntl

    library = kalam_library_path()
    cache_dir.mkdir(parents=True, exist_ok=True)
    with (cache_dir / "mtp.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Синхронизация Kindle уже выполняется. Дождитесь её завершения.") from exc
        try:
            result = subprocess.run(
                [sys.executable, "-m", "kindle_vocab_app.kindle_mtp"],
                input=json.dumps({"library": str(library), "cache_dir": str(cache_dir.resolve())}),
                text=True, capture_output=True, timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("Kindle не ответил по USB. Закройте OpenMTP, переподключите Kindle и повторите синхронизацию.") from exc
        try:
            response = json.loads(result.stdout)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Не удалось прочитать Kindle по MTP. Закройте другие программы передачи файлов и переподключите устройство.") from exc
        if result.returncode != 0 or not response.get("ok"):
            raise RuntimeError(str(response.get("error") or "Ошибка чтения Kindle по MTP"))
    return cache_dir / "vocab.db"


class KalamSession:
    """Only bind read operations. Never upload, delete, rename, or make folders."""

    CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_char_p)

    def __init__(self, library: Path):
        self.lib = ctypes.CDLL(str(library))
        self.callbacks: list[Any] = []  # Keep callbacks alive until the worker exits.

    def call(self, name: str, payload: dict[str, Any] | None = None) -> Any:
        if name not in {"Initialize", "FetchStorages", "Walk", "DownloadFiles", "Dispose"}:
            raise ValueError("Unsupported MTP operation")
        responses: list[dict[str, Any]] = []

        def receive(raw: bytes) -> None:
            try:
                responses.append(json.loads(raw))
            except (ValueError, TypeError):
                responses.append({"error": "Некорректный ответ MTP"})

        done = self.CALLBACK(receive)
        self.callbacks.append(done)
        callback_args = [done]
        if name == "DownloadFiles":
            ignore = self.CALLBACK(lambda raw: None)
            self.callbacks.append(ignore)
            callback_args = [ignore, ignore, done]
        fn = getattr(self.lib, name)
        fn.restype = None
        fn.argtypes = ([ctypes.c_char_p] if payload is not None else []) + [self.CALLBACK] * len(callback_args)
        fn(*([json.dumps(payload).encode("utf-8")] if payload is not None else []), *callback_args)
        if not responses:
            raise RuntimeError("MTP не вернул результат")
        response = responses[-1]
        if response.get("error"):
            raise RuntimeError("Ошибка чтения Kindle по MTP. Закройте OpenMTP и другие программы передачи файлов, затем повторите синхронизацию.")
        return response.get("data")

    def walk(self, storage_id: int, path: str) -> list[dict[str, Any]]:
        return self.call("Walk", {"storageId": storage_id, "fullPath": path, "recursive": False,
                                  "skipDisallowedFiles": False, "skipHiddenFiles": False}) or []

    def download(self, storage_id: int, sources: list[str], destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        self.call("DownloadFiles", {"storageId": storage_id, "sources": sources,
                                    "destination": str(destination), "preprocessFiles": True})


def is_kindle_device(info: dict[str, Any]) -> bool:
    usb = info.get("usbDeviceInfo") or {}
    return usb.get("IdVendor") == AMAZON_VENDOR_ID and "kindle" in str(usb.get("Product", "")).casefold()


def safe_thumbnail(item: dict[str, Any]) -> bool:
    name = str(item.get("name") or "")
    return (not item.get("isFolder") and Path(name).name == name
            and name.startswith("thumbnail_") and name.endswith(".jpg")
            and str(item.get("path")) == f"/system/thumbnails/{name}"
            and 0 < int(item.get("size") or 0) <= MAX_THUMBNAIL_BYTES)


def sync_session(session: KalamSession, cache_dir: Path) -> dict[str, int]:
    from kindle_vocab_app.kindle_db import validate_vocab_db

    info = session.call("Initialize")
    try:
        if not is_kindle_device(info or {}):
            raise RuntimeError("MTP открыл другое устройство. Отключите его и повторите подключение Kindle.")
        storages = session.call("FetchStorages") or []
        for storage in storages:
            storage_id = int(storage["Sid"])
            try:
                files = session.walk(storage_id, "/system/vocabulary")
            except RuntimeError:
                continue
            vocab = next((f for f in files if f.get("path") == "/system/vocabulary/vocab.db" and not f.get("isFolder")), None)
            if vocab is None:
                continue
            size = int(vocab.get("size") or 0)
            if not 0 < size <= MAX_VOCAB_BYTES:
                raise RuntimeError("Некорректный размер базы Vocabulary Builder")
            with tempfile.TemporaryDirectory(prefix="mtp-", dir=cache_dir) as temporary:
                staging = Path(temporary)
                session.download(storage_id, ["/system/vocabulary/vocab.db"], staging)
                copied = staging / "vocab.db"
                if not copied.is_file() or copied.stat().st_size != size:
                    raise RuntimeError("База Kindle скопирована не полностью. Повторите синхронизацию.")
                validate_vocab_db(copied)
                copied.replace(cache_dir / "vocab.db")
                try:
                    root_files = session.walk(storage_id, "/")
                    metadata = next((f for f in root_files if f.get("path") == "/metadata.calibre" and not f.get("isFolder")), None)
                    if metadata and 0 < int(metadata.get("size") or 0) <= 2 * 1024 * 1024:
                        session.download(storage_id, ["/metadata.calibre"], staging)
                        metadata_path = staging / "metadata.calibre"
                        parsed = json.loads(metadata_path.read_bytes())
                        if isinstance(parsed, (dict, list)):
                            metadata_path.replace(cache_dir / "metadata.calibre")
                except (RuntimeError, OSError, ValueError):
                    pass
                # Covers are optional; a missing image must not undo vocabulary sync.
                count = 0
                try:
                    thumbnails = [f for f in session.walk(storage_id, "/system/thumbnails") if safe_thumbnail(f)][:500]
                    if sum(int(f["size"]) for f in thumbnails) <= 25 * 1024 * 1024:
                        destination = staging / "thumbnails"
                        if thumbnails:
                            session.download(storage_id, [str(f["path"]) for f in thumbnails], destination)
                        target = cache_dir / "kindle-thumbnails"
                        target.mkdir(exist_ok=True)
                        for item in thumbnails:
                            image = destination / str(item["name"])
                            if image.is_file() and image.stat().st_size == int(item["size"]):
                                image.replace(target / image.name)
                                count += 1
                except (RuntimeError, OSError, ValueError):
                    pass
            return {"vocab_bytes": size, "thumbnails": count}
        raise RuntimeError("На Kindle не найдена база Vocabulary Builder. Проверьте, что словарь Vocabulary Builder включён.")
    finally:
        try:
            session.call("Dispose")
        except RuntimeError:
            pass  # A detached USB device must not mask the original result.


def main() -> int:
    # Native runtimes can write diagnostics directly to fd 1; preserve JSON stdout.
    request = json.loads(sys.stdin.read())
    saved_stdout = os.dup(1)
    os.dup2(2, 1)
    try:
        summary = sync_session(KalamSession(Path(request["library"])), Path(request["cache_dir"]))
        response = {"ok": True, "summary": summary}
        code = 0
    except Exception as exc:
        response = {"ok": False, "error": str(exc)}
        code = 1
    finally:
        os.dup2(saved_stdout, 1)
        os.close(saved_stdout)
    print(json.dumps(response, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
