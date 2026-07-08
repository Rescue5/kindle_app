from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def npm_command() -> str | None:
    return shutil.which("npm.cmd") or shutil.which("npm")


def check_command(name: str, command: list[str], *, cwd: Path | None = None) -> CheckResult:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        return CheckResult(name, False, f"{command[0]} was not found")
    except subprocess.TimeoutExpired:
        return CheckResult(name, False, "command timed out")

    output = (result.stdout or result.stderr).strip().splitlines()
    detail = output[0] if output else f"exit code {result.returncode}"
    return CheckResult(name, result.returncode == 0, detail)


def check_nltk_resources() -> CheckResult:
    try:
        import nltk
    except ImportError as error:
        return CheckResult("nltk resources", False, f"nltk import failed: {error}")

    resources = {
        "wordnet": ["corpora/wordnet", "corpora/wordnet.zip"],
        "omw-1.4": ["corpora/omw-1.4", "corpora/omw-1.4.zip"],
        "averaged_perceptron_tagger_eng": [
            "taggers/averaged_perceptron_tagger_eng",
            "taggers/averaged_perceptron_tagger_eng.zip",
        ],
        "punkt_tab": ["tokenizers/punkt_tab", "tokenizers/punkt_tab.zip"],
    }
    missing = []
    for name, candidates in resources.items():
        for candidate in candidates:
            try:
                nltk.data.find(candidate)
                break
            except LookupError:
                continue
        else:
            missing.append(name)

    if missing:
        return CheckResult("nltk resources", False, "missing: " + ", ".join(missing))
    return CheckResult("nltk resources", True, "installed")


def run_checks(*, include_slow: bool = True) -> list[CheckResult]:
    root = project_root()
    npm = npm_command()
    checks = [
        CheckResult("python", True, sys.executable),
        CheckResult("package", True, str(Path(__file__).resolve())),
        check_command("node", ["node", "--version"]),
        check_command("npm", [npm or "npm", "--version"]),
        check_command("cargo", ["cargo", "--version"]),
        check_command("rustc", ["rustc", "--version"]),
        check_nltk_resources(),
    ]
    if include_slow:
        checks.append(check_command("vite", [npm or "npm", "exec", "vite", "--", "--version"], cwd=root))
        metadata = check_command(
            "cargo metadata",
            [
                "cargo",
                "metadata",
                "--manifest-path",
                str(root / "src-tauri" / "Cargo.toml"),
                "--no-deps",
                "--format-version",
                "1",
            ],
            cwd=root,
        )
        checks.append(CheckResult(metadata.name, metadata.ok, "metadata ok" if metadata.ok else metadata.detail))
    return checks


def print_checks(checks: list[CheckResult]) -> None:
    for check in checks:
        status = "OK" if check.ok else "FAIL"
        print(f"[{status}] {check.name}: {check.detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Kindle Vocabulary Builder dev runtime.")
    parser.add_argument("--fast", action="store_true", help="Skip npm/vite and cargo metadata checks.")
    args = parser.parse_args(argv)

    checks = run_checks(include_slow=not args.fast)
    print_checks(checks)
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
