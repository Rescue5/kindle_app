from __future__ import annotations

import argparse
from pathlib import Path

from kindle_vocab_app.llm_enricher import LLMEnrichmentError, enrich_optimized_tsv
from kindle_vocab_app.logging_config import configure_logging, get_logger


logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize new Kindle vocabulary entries.")
    parser.add_argument("database", type=Path, nargs="?", help="Path to Kindle vocab.db")
    parser.add_argument(
        "output_dir",
        type=Path,
        nargs="?",
        help="Directory for optimized.tsv and JSON analysis",
    )
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
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Fill translations, generated context, and revised importance with DeepSeek V4 Flash",
    )
    parser.add_argument(
        "--llm-force",
        action="store_true",
        help="Re-run DeepSeek enrichment even for rows that already have generated fields",
    )
    parser.add_argument(
        "--llm-limit",
        type=int,
        default=None,
        help="Limit the number of rows sent to the LLM in this run",
    )
    parser.add_argument(
        "--enrich-existing-tsv",
        type=Path,
        default=None,
        help="Only enrich an existing optimized TSV and skip reading the Kindle database",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.enrich_existing_tsv and args.output_dir is None and args.database is not None:
        args.output_dir = args.database
        args.database = None
    if args.output_dir is None:
        print("Missing output_dir.")
        return 2
    log_path = configure_logging(args.output_dir / "logs", console=True)
    logger.info("Optimizer CLI started args=%s log_path=%s", vars(args), log_path)
    if args.enrich_existing_tsv:
        try:
            result = enrich_optimized_tsv(
                args.enrich_existing_tsv,
                analysis_dir=args.output_dir / "word_analysis",
                force=args.llm_force,
                limit=args.llm_limit,
            )
        except LLMEnrichmentError as exc:
            logger.exception("LLM enrichment command failed tsv=%s", args.enrich_existing_tsv)
            print(f"LLM enrichment skipped: {exc}")
            return 2
        print(f"LLM enriched rows: {result.processed}")
        print(f"LLM skipped rows: {result.skipped}")
        print(f"LLM failed rows: {result.failed}")
        print(f"TSV: {result.tsv_path}")
        logger.info("Optimizer CLI finished enrich-existing mode result=%s", result)
        return 0

    if args.database is None:
        logger.error("Optimizer CLI missing database path")
        print("Missing database path.")
        return 2

    from kindle_vocab_app.kindle_db import fetch_entries, validate_vocab_db
    from kindle_vocab_app.vocab_optimizer import optimize_entries, seed_snapshot_from_optimized_tsv

    validate_vocab_db(args.database)
    snapshot_path = args.snapshot or args.output_dir / "processed_snapshot.json"
    if args.seed_optimized_tsv:
        seeded = seed_snapshot_from_optimized_tsv(snapshot_path, args.seed_optimized_tsv)
        logger.info("Seeded snapshot from TSV seeded=%d path=%s", seeded, args.seed_optimized_tsv)
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
    logger.info("Local optimization completed result=%s", result)
    if args.llm:
        try:
            enrichment = enrich_optimized_tsv(
                result.tsv_path,
                analysis_dir=result.analysis_dir,
                force=args.llm_force,
                limit=args.llm_limit,
            )
        except LLMEnrichmentError as exc:
            logger.exception("LLM enrichment after optimization failed tsv=%s", result.tsv_path)
            print(f"LLM enrichment skipped: {exc}")
            return 2
        print(f"LLM enriched rows: {enrichment.processed}")
        print(f"LLM skipped rows: {enrichment.skipped}")
        print(f"LLM failed rows: {enrichment.failed}")
        logger.info("LLM enrichment after optimization completed result=%s", enrichment)
    logger.info("Optimizer CLI finished successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
