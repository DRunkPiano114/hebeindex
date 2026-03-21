#!/usr/bin/env python3
"""
review.py — Terminal UI for human review of low-confidence classified items.

Usage:
    uv run python review.py --artist artists/hebe.yaml           # review all low-confidence items
    uv run python review.py --artist artists/hebe.yaml --threshold 0.6  # custom threshold
    uv run python review.py --artist artists/hebe.yaml --category concerts  # filter by category
    uv run python review.py --artist artists/hebe.yaml --resume   # resume previous session

Actions per item:
    [a] Approve  — keep as-is, bump confidence to 1.0
    [r] Reject   — move to discarded.json
    [s] Skip     — leave unchanged, move to next
    [q] Quit     — save progress and exit
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("review")

BASE_DIR = Path(__file__).parent

# Category key -> file_id mapping (same as reclassify.py)
CATEGORY_FILE_MAP = {
    "personal_mv": 2,
    "ost_singles": 3,
    "concerts": 4,
    "variety": 5,
    "interviews": 6,
    "group_mv": 7,
    "collabs": 8,
}

CATEGORY_LABELS = {
    "personal_mv": "Personal MV",
    "ost_singles": "OST / Singles",
    "concerts": "Concerts",
    "variety": "Variety Shows",
    "interviews": "Interviews",
    "group_mv": "S.H.E MV",
    "collabs": "Collaborations",
}

# ──────────────────────────────────────────────────────────────────────
# State management
# ──────────────────────────────────────────────────────────────────────

REVIEW_STATE_FILENAME = ".review_state.json"


def _state_path(processed_dir: Path) -> Path:
    return processed_dir / REVIEW_STATE_FILENAME


def load_review_state(processed_dir: Path) -> dict:
    """Load saved review state, or return empty state."""
    path = _state_path(processed_dir)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"reviewed": {}, "session_start": None}


def save_review_state(processed_dir: Path, state: dict):
    """Persist review state to disk."""
    path = _state_path(processed_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────────────

def _item_key(item: dict) -> str:
    """Unique key for an item based on URL."""
    return item.get("url", "")


def load_items(processed_dir: Path, threshold: float, category_filter: str | None = None) -> list[dict]:
    """Load all processed items with confidence below threshold.

    Returns items sorted by confidence ascending (lowest first).
    """
    items = []

    for cat_key, file_id in CATEGORY_FILE_MAP.items():
        if category_filter and cat_key != category_filter:
            continue

        filepath = processed_dir / f"file_{file_id}.json"
        if not filepath.exists():
            logger.warning("File not found: %s", filepath)
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data.get("results", []):
            conf = item.get("confidence")
            if conf is not None and conf < threshold:
                item["_source_file_id"] = file_id
                items.append(item)

    items.sort(key=lambda x: x.get("confidence", 0.0))
    return items


# ──────────────────────────────────────────────────────────────────────
# Display helpers
# ──────────────────────────────────────────────────────────────────────

def _truncate(text: str, max_len: int = 80) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _format_views(count: int | None) -> str:
    if count is None or count == 0:
        return "N/A"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def _confidence_bar(confidence: float, width: int = 20) -> str:
    """Visual bar for confidence score."""
    filled = int(confidence * width)
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {confidence:.3f}"


def display_item(item: dict, index: int, total: int):
    """Display a single item for review."""
    title = item.get("title", "N/A")
    url = item.get("url", "N/A")
    channel = item.get("channel") or item.get("author") or "N/A"
    source = item.get("source", "N/A")
    duration = item.get("duration", "N/A")
    views = _format_views(item.get("view_count") or item.get("play_count"))
    category = item.get("category", "N/A")
    reason = item.get("classification_reason", "N/A")
    confidence = item.get("confidence", 0.0)
    signals = item.get("confidence_signals", {})

    cat_label = CATEGORY_LABELS.get(category, category)

    print()
    print("=" * 70)
    print(f"  Item {index + 1} of {total}")
    print("=" * 70)
    print(f"  Title:      {title}")
    print(f"  URL:        {url}")
    print(f"  Channel:    {channel}")
    print(f"  Source:      {source}  |  Duration: {duration}  |  Views: {views}")
    print(f"  Category:   {cat_label} ({category})")
    print(f"  Reason:     {reason}")
    print(f"  Confidence: {_confidence_bar(confidence)}")
    if signals:
        print("  Signals:")
        for sig_name, sig_val in sorted(signals.items(), key=lambda x: -x[1]):
            bar = "#" * int(sig_val * 10)
            print(f"    {sig_name:22s} {sig_val:.2f}  {bar}")
    print("-" * 70)


def display_summary(actions: Counter, total: int):
    """Display end-of-session summary."""
    approved = actions.get("approve", 0)
    rejected = actions.get("reject", 0)
    skipped = actions.get("skip", 0)

    print()
    print("=" * 50)
    print("  REVIEW SESSION SUMMARY")
    print("=" * 50)
    print(f"  Total items reviewed:  {approved + rejected + skipped}")
    print(f"  Approved:              {approved}")
    print(f"  Rejected:              {rejected}")
    print(f"  Skipped:               {skipped}")
    remaining = total - (approved + rejected + skipped)
    if remaining > 0:
        print(f"  Remaining:             {remaining}")
    print("=" * 50)
    print()


# ──────────────────────────────────────────────────────────────────────
# Review actions
# ──────────────────────────────────────────────────────────────────────

def apply_review_results(processed_dir: Path, state: dict):
    """Write review decisions back to processed JSON files.

    - Approved items get confidence bumped to 1.0
    - Rejected items are removed from their file and added to discarded.json
    """
    reviewed = state.get("reviewed", {})
    if not reviewed:
        return

    approved_urls = {url for url, action in reviewed.items() if action == "approve"}
    rejected_urls = {url for url, action in reviewed.items() if action == "reject"}

    if not approved_urls and not rejected_urls:
        return

    rejected_items = []

    for cat_key, file_id in CATEGORY_FILE_MAP.items():
        filepath = processed_dir / f"file_{file_id}.json"
        if not filepath.exists():
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        original_count = len(data.get("results", []))
        kept = []
        modified = False
        for item in data.get("results", []):
            url = item.get("url", "")
            if url in rejected_urls:
                item["category"] = "discard"
                item["classification_reason"] = "review_rejected"
                rejected_items.append(item)
                modified = True
            elif url in approved_urls:
                item["confidence"] = 1.0
                item["confidence_signals"] = {"review_approved": 1.0}
                kept.append(item)
                modified = True
            else:
                kept.append(item)

        if modified:
            data["results"] = kept
            data["total_results"] = len(kept)
            data["processed_at"] = datetime.now().isoformat()
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Updated %s: %d -> %d items", filepath.name, original_count, len(kept))

    # Append to discarded.json
    if rejected_items:
        discarded_path = processed_dir / "discarded.json"
        existing_discarded = []
        if discarded_path.exists():
            with open(discarded_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
                existing_discarded = existing.get("items", [])

        all_discarded = existing_discarded + rejected_items
        with open(discarded_path, "w", encoding="utf-8") as f:
            json.dump(
                {"total": len(all_discarded), "items": all_discarded},
                f, ensure_ascii=False, indent=2,
            )
        logger.info("Added %d rejected items to discarded.json (total: %d)",
                     len(rejected_items), len(all_discarded))


# ──────────────────────────────────────────────────────────────────────
# Main review loop
# ──────────────────────────────────────────────────────────────────────

def run_review(
    processed_dir: Path,
    threshold: float = 0.7,
    category_filter: str | None = None,
    resume: bool = False,
    input_fn=None,
):
    """Run the interactive review session.

    Args:
        processed_dir: Path to processed JSON files
        threshold: Only show items with confidence below this
        category_filter: Optional category key to filter items
        resume: Whether to resume a previous session
        input_fn: Optional callable for input (for testing). Defaults to builtin input().

    Returns:
        Counter of actions taken (approve/reject/skip)
    """
    if input_fn is None:
        input_fn = input

    # Load state
    state = load_review_state(processed_dir) if resume else {"reviewed": {}, "session_start": None}
    if state.get("session_start") is None:
        state["session_start"] = datetime.now().isoformat()

    # Load items
    items = load_items(processed_dir, threshold, category_filter)
    if not items:
        print(f"\nNo items found with confidence < {threshold}")
        if category_filter:
            print(f"  (filtered to category: {category_filter})")
        print("Nothing to review.")
        return Counter()

    # Filter out already-reviewed items
    already_reviewed = set(state.get("reviewed", {}).keys())
    pending = [item for item in items if _item_key(item) not in already_reviewed]

    total_all = len(items)
    total_pending = len(pending)
    already_done = total_all - total_pending

    print(f"\nFound {total_all} items with confidence < {threshold}")
    if already_done > 0:
        print(f"  ({already_done} already reviewed, {total_pending} remaining)")
    if category_filter:
        print(f"  Filtered to category: {CATEGORY_LABELS.get(category_filter, category_filter)}")
    print(f"\nActions: [a]pprove  [r]eject  [s]kip  [q]uit\n")

    actions: Counter = Counter()
    quit_requested = False

    for idx, item in enumerate(pending):
        display_item(item, already_done + idx, total_all)

        while True:
            try:
                choice = input_fn("  Action [a/r/s/q]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "q"

            if choice in ("a", "approve"):
                actions["approve"] += 1
                state["reviewed"][_item_key(item)] = "approve"
                print("  -> Approved")
                break
            elif choice in ("r", "reject"):
                actions["reject"] += 1
                state["reviewed"][_item_key(item)] = "reject"
                print("  -> Rejected")
                break
            elif choice in ("s", "skip"):
                actions["skip"] += 1
                state["reviewed"][_item_key(item)] = "skip"
                print("  -> Skipped")
                break
            elif choice in ("q", "quit"):
                quit_requested = True
                break
            else:
                print("  Invalid choice. Use [a]pprove, [r]eject, [s]kip, or [q]uit.")

        # Save state after each action
        save_review_state(processed_dir, state)

        if quit_requested:
            print("\n  Session paused. Use --resume to continue later.")
            break

    # Display summary
    display_summary(actions, total_all)

    # Apply results
    if actions.get("approve", 0) > 0 or actions.get("reject", 0) > 0:
        apply_review_results(processed_dir, state)

    # Clean up state file if all items reviewed
    if not quit_requested and total_pending == sum(actions.values()):
        state_path = _state_path(processed_dir)
        if state_path.exists():
            state_path.unlink()
            logger.info("Review complete — removed state file")

    return actions


# ──────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Review low-confidence classified items in HebeIndex"
    )
    parser.add_argument(
        "--artist", type=str, default=None,
        help="Path to artist YAML (unused for review, kept for CLI consistency)"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.7,
        help="Confidence threshold — items below this are shown for review (default: 0.7)"
    )
    parser.add_argument(
        "--category", type=str, default=None,
        choices=list(CATEGORY_FILE_MAP.keys()),
        help="Only review items in this category"
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume a previous review session"
    )
    parser.add_argument(
        "--processed-dir", type=str, default=None,
        help="Path to processed/ directory (default: collector/processed/)"
    )
    args = parser.parse_args()

    processed_dir = Path(args.processed_dir) if args.processed_dir else BASE_DIR / "processed"

    if not processed_dir.exists():
        print(f"Error: processed directory not found: {processed_dir}")
        sys.exit(1)

    run_review(
        processed_dir=processed_dir,
        threshold=args.threshold,
        category_filter=args.category,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
