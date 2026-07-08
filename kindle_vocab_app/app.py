from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from kindle_vocab_app.doctor import check_command, npm_command
from kindle_vocab_app.logging_config import configure_logging, get_logger


logger = get_logger(__name__)


def main() -> int:
    """Compatibility launcher for the Tauri-based UI."""

    root = Path(__file__).resolve().parents[1]
    configure_logging(root / ".app-data" / "logs", console=True)
    npm = npm_command()
    if npm is None:
        logger.error("npm was not found; cannot launch Tauri UI")
        print("npm was not found. Run scripts/setup-dev.ps1 or install Node.js, then retry.")
        return 2
    cargo = check_command("cargo", ["cargo", "--version"])
    if not cargo.ok:
        logger.error("cargo was not found; cannot launch Tauri UI detail=%s", cargo.detail)
        print("cargo was not found. Run scripts/setup-dev.ps1, then retry.")
        return 2

    env = os.environ.copy()
    env["KINDLE_CARDS_PYTHON"] = sys.executable
    logger.info("Launching Tauri dev UI npm=%s cwd=%s python=%s", npm, root, sys.executable)
    return subprocess.call([npm, "run", "tauri", "dev"], cwd=root, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
