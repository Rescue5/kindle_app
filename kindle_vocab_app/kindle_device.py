from __future__ import annotations

import ctypes
import os
import shutil
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kindle_vocab_app.logging_config import get_logger


VOCAB_RELATIVE_PATHS = (
    Path("system") / "vocabulary" / "vocab.db",
    Path("Kindle") / "system" / "vocabulary" / "vocab.db",
)

logger = get_logger(__name__)


@dataclass
class KindleVocabSource:
    label: str
    signature: tuple[str, ...]
    path: Path | None = None
    shell_item: Any | None = None

    def copy_to_cache(self, cache_dir: Path) -> Path:
        logger.info(
            "Copying Kindle vocab source to cache label=%s cache_dir=%s source_type=%s",
            self.label,
            cache_dir,
            "mtp" if self.shell_item is not None else "path",
        )
        if self.shell_item is not None:
            return _copy_shell_item(self.shell_item, cache_dir)
        if self.path is None:
            raise RuntimeError("Kindle source has no readable path")
        return _copy_path(self.path, cache_dir)


def find_kindle_source(roots: Iterable[Path] | None = None) -> KindleVocabSource | None:
    logger.info(
        "Searching for Kindle source roots=%s platform=%s",
        "<auto>" if roots is None else list(roots),
        sys.platform,
    )
    if sys.platform == "win32" and roots is None:
        mtp_source = _find_windows_mtp_vocab()
        if mtp_source is not None:
            logger.info("Found Kindle source through Windows MTP label=%s", mtp_source.label)
            return mtp_source

    path = find_kindle_vocab(roots)
    if path is None:
        logger.info("No Kindle vocab source found")
        return None
    stat = path.stat()
    volume = path.parents[2]
    label = volume.name or volume.anchor or "USB"
    source = KindleVocabSource(
        label=f"Kindle · {label}",
        signature=(str(path), str(stat.st_size), str(stat.st_mtime_ns)),
        path=path,
    )
    logger.info("Found Kindle source path=%s label=%s size=%s", path, source.label, stat.st_size)
    return source


def mounted_volume_roots() -> list[Path]:
    logger.debug("Collecting mounted volume roots platform=%s", sys.platform)
    if sys.platform == "win32":
        return _windows_volume_roots()

    roots: list[Path] = []
    if sys.platform == "darwin":
        roots.extend(_children(Path("/Volumes")))
    else:
        user = os.environ.get("USER") or os.environ.get("USERNAME")
        if user:
            roots.extend(_children(Path("/media") / user))
            roots.extend(_children(Path("/run/media") / user))
        roots.extend(_children(Path("/media")))
        roots.extend(_children(Path("/mnt")))
    unique = _unique_existing(roots)
    logger.debug("Mounted volume roots count=%d roots=%s", len(unique), unique)
    return unique


def find_kindle_vocab(roots: Iterable[Path] | None = None) -> Path | None:
    candidates = list(roots) if roots is not None else mounted_volume_roots()
    logger.debug("Scanning Kindle vocab candidates count=%d", len(candidates))
    for root in _unique_existing(candidates):
        for relative_path in VOCAB_RELATIVE_PATHS:
            vocab_path = root / relative_path
            try:
                if vocab_path.is_file():
                    logger.info("Found Kindle vocab file path=%s", vocab_path)
                    return vocab_path
            except OSError as exc:
                logger.debug("Cannot inspect Kindle vocab candidate path=%s error=%s", vocab_path, exc)
                continue
    logger.debug("Kindle vocab file not found in candidates")
    return None


def cache_vocab_database(source: Path, cache_dir: Path) -> Path:
    logger.info("Caching Kindle database source=%s cache_dir=%s", source, cache_dir)
    return _copy_path(source, cache_dir)


def file_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _find_windows_mtp_vocab() -> KindleVocabSource | None:
    logger.debug("Searching Windows MTP devices for Kindle vocab")
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        shell = win32com.client.Dispatch("Shell.Application")
        this_pc = shell.Namespace(17)
        if this_pc is None:
            return None

        for device in _shell_items(this_pc.Items()):
            if not bool(device.IsFolder) or _looks_like_drive_path(str(device.Path)):
                continue
            vocab = _find_vocab_in_shell_device(device)
            if vocab is None:
                continue
            parent_folder, item = vocab
            size = str(parent_folder.GetDetailsOf(item, 2) or "")
            modified = str(parent_folder.GetDetailsOf(item, 3) or "")
            source = KindleVocabSource(
                label=f"Kindle · {device.Name}",
                signature=(str(device.Path), str(item.Path), size, modified),
                shell_item=item,
            )
            logger.info(
                "Found Windows MTP Kindle source label=%s size=%s modified=%s",
                source.label,
                size,
                modified,
            )
            return source
    except (ImportError, OSError, AttributeError) as exc:
        logger.debug("Windows MTP search unavailable or failed error=%s", exc)
        return None
    return None


def _find_vocab_in_shell_device(device: Any) -> tuple[Any, Any] | None:
    for storage in _shell_items(device.GetFolder.Items()):
        if not bool(storage.IsFolder):
            continue
        system = _shell_child(storage, "system")
        if system is None:
            continue
        vocabulary = _shell_child(system, "vocabulary")
        if vocabulary is None:
            continue
        folder = vocabulary.GetFolder
        for item in _shell_items(folder.Items()):
            if str(item.Name).casefold() in {"vocab", "vocab.db"}:
                return folder, item
    return None


def _shell_child(parent: Any, name: str) -> Any | None:
    expected = name.casefold()
    for item in _shell_items(parent.GetFolder.Items()):
        if bool(item.IsFolder) and str(item.Name).casefold() == expected:
            return item
    return None


def _shell_items(items: Any) -> list[Any]:
    return [items.Item(index) for index in range(items.Count)]


def _copy_shell_item(shell_item: Any, cache_dir: Path) -> Path:
    logger.info("Copying Windows MTP shell item to cache cache_dir=%s", cache_dir)
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    cache_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = cache_dir / "mtp-staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)

    shell = win32com.client.Dispatch("Shell.Application")
    destination = shell.Namespace(str(staging_dir.resolve()))
    if destination is None:
        raise RuntimeError("Cannot open local cache directory")
    destination.CopyHere(shell_item, 20)

    deadline = time.monotonic() + 20
    copied: Path | None = None
    while time.monotonic() < deadline:
        files = [path for path in staging_dir.iterdir() if path.is_file()]
        if files:
            candidate = files[0]
            first_size = candidate.stat().st_size
            time.sleep(0.2)
            if candidate.exists() and candidate.stat().st_size == first_size and first_size > 0:
                copied = candidate
                break
        pythoncom.PumpWaitingMessages()
        time.sleep(0.1)

    if copied is None:
        logger.error("Timed out copying Windows MTP vocab.db cache_dir=%s", cache_dir)
        raise TimeoutError("Windows did not finish copying vocab.db from Kindle")

    target = cache_dir / "vocab.db"
    temporary = cache_dir / "vocab.db.tmp"
    shutil.copy2(copied, temporary)
    temporary.replace(target)
    shutil.rmtree(staging_dir, ignore_errors=True)
    logger.info("Copied Windows MTP vocab.db to cache target=%s size=%d", target, target.stat().st_size)
    return target


def _copy_path(source: Path, cache_dir: Path) -> Path:
    logger.info("Copying vocab.db path source=%s cache_dir=%s", source, cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / "vocab.db"
    temporary = cache_dir / "vocab.db.tmp"
    shutil.copy2(source, temporary)
    temporary.replace(target)
    logger.info("Copied vocab.db to cache target=%s size=%d", target, target.stat().st_size)
    return target


def _looks_like_drive_path(path: str) -> bool:
    return len(path) >= 3 and path[1:3] == ":\\"


def _windows_volume_roots() -> list[Path]:
    try:
        kernel32 = ctypes.windll.kernel32
        drives_mask = kernel32.GetLogicalDrives()
        roots: list[Path] = []
        for index in range(26):
            if not drives_mask & (1 << index):
                continue
            root = f"{chr(ord('A') + index)}:\\"
            drive_type = kernel32.GetDriveTypeW(root)
            if drive_type in {2, 3}:
                roots.append(Path(root))
        return roots
    except (AttributeError, OSError):
        return []


def _children(path: Path) -> list[Path]:
    try:
        return [child for child in path.iterdir() if child.is_dir()]
    except OSError:
        return []


def _unique_existing(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).casefold()
        if key in seen:
            continue
        try:
            if not path.exists():
                continue
        except OSError:
            continue
        seen.add(key)
        result.append(path)
    return result
