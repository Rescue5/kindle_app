from __future__ import annotations

import subprocess
import os
import shutil
import sys
from pathlib import Path

from kindle_vocab_app.logging_config import configure_logging, get_logger


logger = get_logger(__name__)


def main() -> int:
    """Compatibility launcher for the new Tauri-based UI."""

    root = Path(__file__).resolve().parents[1]
    configure_logging(root / ".app-data" / "logs", console=True)
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        logger.error("npm was not found; cannot launch Tauri UI")
        print("npm не найден. Запусти интерфейс вручную после установки Node.js: npm run dev")
        return 2
    env = os.environ.copy()
    env["KINDLE_CARDS_PYTHON"] = sys.executable
    logger.info("Launching Tauri dev UI npm=%s cwd=%s python=%s", npm, root, sys.executable)
    return subprocess.call([npm, "run", "tauri", "dev"], cwd=root, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
