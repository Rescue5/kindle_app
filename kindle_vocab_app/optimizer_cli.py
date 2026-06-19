from __future__ import annotations

import argparse
from pathlib import Path

from kindle_vocab_app.kindle_db import fetch_entries, validate_vocab_db
from kindle_vocab_app.vocab_optimizer import optimize_entries, seed_snapshot_from_optimized_tsv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize new Kindle vocabulary entries.")
    parser.add_argument("database", type=Path, help="Path to Kindle vocab.db")
    parser.add_argument("output_dir", type=Path, help="Directory for optimized.tsv and JSON analysis")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="Persistent processed snapshot. Defaults to output_dir/processed_snapshot.json",
    )
    parser.add_argument("--book-key", default=None, help="Optional Kindle book key filter")
    parser.add_argument("--config", type=Path, default=None, help="Optional processing TOML config")
    parser.add_argument(
        "--seed-optimized-tsv",
        type=Path,
        default=None,
        help="Import already optimized words into the processed snapshot before processing",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    validate_vocab_db(args.database)
    snapshot_path = args.snapshot or args.output_dir / "processed_snapshot.json"
    if args.seed_optimized_tsv:
        seeded = seed_snapshot_from_optimized_tsv(snapshot_path, args.seed_optimized_tsv)
        print(f"Seeded processed snapshot from TSV: {seeded}")
    result = optimize_entries(
        fetch_entries(args.database, args.book_key),
        args.output_dir,
        snapshot_path,
        config_path=args.config,
    )
    print(f"Processed new lexical items: {result.processed_new}")
    print(f"Accepted new lexical items: {result.accepted_new}")
    print(f"Rejected new lexical items: {result.rejected_new}")
    print(f"Skipped existing lexical items: {result.skipped_existing}")
    print(f"TSV: {result.tsv_path}")
    print(f"JSON: {result.analysis_dir}")
    print(f"Snapshot: {result.snapshot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
