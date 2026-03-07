"""
pipeline.py — CLI orchestrator for the V2 agent pipeline.

Run from project root (hebeindex/):

    source collector/.venv/bin/activate

    python -m agent.pipeline                    # all phases
    python -m agent.pipeline --phase ingest     # phase 1 only
    python -m agent.pipeline --phase dedup      # phase 2 only
    python -m agent.pipeline --phase classify   # phase 3 only
    python -m agent.pipeline --phase output     # phase 4 only
    python -m agent.pipeline --stats            # print statistics
"""

from __future__ import annotations

import argparse
import logging
import sys
import os
import time

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ingest import run_ingest
from agent.dedup import run_dedup
from agent.classify import run_classify
from agent.output import run_output, print_stats


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                os.path.join(os.path.dirname(__file__), "pipeline_run.log"),
                encoding="utf-8",
            ),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="V2 Agent Pipeline")
    parser.add_argument(
        "--phase",
        choices=["ingest", "dedup", "classify", "output"],
        help="Run a specific phase only",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print pipeline statistics",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of worker threads for ingest (default: 4)",
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("pipeline")

    if args.stats:
        print_stats()
        return

    start = time.time()

    if args.phase is None or args.phase == "ingest":
        logger.info("=" * 60)
        logger.info("PHASE 1: INGEST")
        logger.info("=" * 60)
        lake_path = run_ingest(max_workers=args.workers)
        logger.info("Ingest output: %s", lake_path)

    if args.phase is None or args.phase == "dedup":
        logger.info("=" * 60)
        logger.info("PHASE 2: DEDUP")
        logger.info("=" * 60)
        deduped_path = run_dedup()
        logger.info("Dedup output: %s", deduped_path)

    if args.phase is None or args.phase == "classify":
        logger.info("=" * 60)
        logger.info("PHASE 3: CLASSIFY")
        logger.info("=" * 60)
        classified_path = run_classify()
        logger.info("Classify output: %s", classified_path)

    if args.phase is None or args.phase == "output":
        logger.info("=" * 60)
        logger.info("PHASE 4: OUTPUT")
        logger.info("=" * 60)
        output_paths = run_output()
        logger.info("Output files: %s", output_paths)

    elapsed = time.time() - start
    logger.info("Pipeline completed in %.1f seconds", elapsed)

    if args.phase is None:
        print_stats()


if __name__ == "__main__":
    main()
