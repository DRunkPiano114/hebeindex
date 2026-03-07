#!/usr/bin/env python3
"""
cleanup.py — Remove entries unrelated to Hebe Tien (田馥甄) from processed/ JSON files.

Usage:
    uv run python cleanup.py            # execute cleanup
    uv run python cleanup.py --dry-run  # preview only, no file changes
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

# File IDs that also accept S.H.E group content (Hebe is a member)
SHE_ACCEPTED_FILES = {4, 7, 8}

# Official channels — entries from these channels are always kept
OFFICIAL_CHANNELS = {
    "華研國際",
    "HIM International Music",
    "HIM International Music Inc.",
    "HIMSHERO",
    "Hebe Tien's Official Channel田馥甄官方專屬頻道",
    "Hebe Tien - Topic",
    "田馥甄 - 主題",
    "田馥甄Hebe",
    "S.H.E - Topic",
}

# Western / K-pop artist blacklist (case-insensitive matching in title/channel/description)
WESTERN_ARTISTS = [
    "rick astley", "taylor swift", "ed sheeran", "adele", "beyonce", "beyoncé",
    "ariana grande", "billie eilish", "dua lipa", "lady gaga", "katy perry",
    "justin bieber", "bruno mars", "drake", "eminem", "rihanna", "shakira",
    "the weeknd", "post malone", "harry styles", "olivia rodrigo", "doja cat",
    "miley cyrus", "selena gomez", "charlie puth", "maroon 5", "coldplay",
    "imagine dragons", "one direction", "bts", "blackpink", "twice", "stray kids",
    "aespa", "newjeans", "ive", "nct", "exo", "red velvet", "tyler the creator",
    "frank ocean", "ofwgkta", "kanye west", "travis scott", "lana del rey",
]

# Other Chinese/Mandopop artists — solo content from these is removed
OTHER_CHINESE_ARTISTS = [
    "林俊杰", "林俊傑", "张惠妹", "張惠妹", "蔡依林", "周杰伦", "周杰倫",
    "王力宏", "陶喆", "萧敬腾", "蕭敬騰", "李荣浩", "李榮浩", "邓紫棋", "鄧紫棋",
    "华晨宇", "華晨宇", "薛之谦", "薛之謙", "毛不易", "周深", "张碧晨", "張碧晨",
    "李宇春", "张靓颖", "張靚穎", "黄丽玲", "黃麗玲", "A-Lin",
    "刘若英", "劉若英", "孙燕姿", "孫燕姿", "梁静茹", "梁靜茹", "王菲",
    "那英", "韩红", "韓紅", "谭维维", "譚維維", "汪峰", "李健",
]

# Wrong context patterns
WRONG_CONTEXT_PATTERNS = [
    "hebe tabachnik",
    "护舒宝", "護舒寶",
    "whisper pad",
    "always ultra",
]

# S.H.E patterns — use lookaround instead of \b to handle adjacent Chinese chars
SHE_PATTERNS = [
    r"(?<![A-Za-z])S\.H\.E(?![A-Za-z])",
    r"(?<![A-Za-z])S\.H\.E\.",
    r"(?<![A-Za-z])SHE(?![A-Za-z])",
    r"(?<![A-Za-z])S\s+H\s+E(?![A-Za-z])",
]
SHE_REGEX = re.compile("|".join(SHE_PATTERNS), re.IGNORECASE)

# S.H.E member names (other than Hebe)
SHE_MEMBER_NAMES = ["任家萱", "Selina", "陳嘉樺", "陈嘉桦", "Ella"]


def get_text_fields(entry: dict) -> str:
    """Concatenate title + channel + description for matching."""
    parts = []
    for key in ("title", "channel", "description"):
        val = entry.get(key)
        if val:
            parts.append(val)
    return " ".join(parts)


def is_hebe_related(entry: dict, file_id: int) -> tuple[bool, str]:
    """
    Determine if an entry is related to Hebe Tien.
    Returns (keep, reason) where reason explains why it was removed.
    """
    text = get_text_fields(entry)
    text_lower = text.lower()
    channel = (entry.get("channel") or "").strip()

    # --- Positive identification (keep) ---

    # Official channel
    if channel in OFFICIAL_CHANNELS:
        return True, ""

    # Direct Hebe identifiers
    if "田馥甄" in text or "馥甄" in text:
        return True, ""
    if "hebe tien" in text_lower:
        return True, ""
    # "hebe" but not "hebe tabachnik" or other false positives
    if "hebe" in text_lower and "tabachnik" not in text_lower:
        return True, ""

    # HIM / 華研 label
    if "華研" in text or "华研" in text or "him international" in text_lower:
        return True, ""

    # S.H.E patterns (only for accepted file IDs)
    if file_id in SHE_ACCEPTED_FILES:
        if SHE_REGEX.search(text):
            return True, ""
        # Fallback: simple substring checks for edge cases like "MVS H E"
        if "s.h.e" in text_lower or "s h e" in text_lower:
            return True, ""
        for name in SHE_MEMBER_NAMES:
            if name.lower() in text_lower:
                return True, ""

    # --- Not positively identified → remove ---
    # Classify removal reason for logging

    # Wrong context
    for pattern in WRONG_CONTEXT_PATTERNS:
        if pattern.lower() in text_lower:
            return False, "wrong_context"

    # Western / K-pop artist
    for artist in WESTERN_ARTISTS:
        if artist in text_lower:
            return False, "western_artist"

    # Other Chinese artist solo content
    for artist in OTHER_CHINESE_ARTISTS:
        if artist.lower() in text_lower:
            return False, "other_artist_solo"

    return False, "no_hebe_identifier"


def process_file(filepath: Path, dry_run: bool) -> dict:
    """Process a single file. Returns stats dict."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    file_id = data.get("file_id", 0)
    results = data.get("results", [])
    original_count = len(results)

    kept = []
    removed = []

    for entry in results:
        keep, reason = is_hebe_related(entry, file_id)
        if keep:
            kept.append(entry)
        else:
            removed.append({
                "title": entry.get("title", ""),
                "url": entry.get("url", ""),
                "channel": entry.get("channel", ""),
                "reason": reason,
            })

    stats = {
        "file": filepath.name,
        "file_id": file_id,
        "original": original_count,
        "kept": len(kept),
        "removed": len(removed),
        "removed_entries": removed,
    }

    # Count by reason
    reason_counts: dict[str, int] = {}
    for r in removed:
        reason_counts[r["reason"]] = reason_counts.get(r["reason"], 0) + 1
    stats["reason_counts"] = reason_counts

    if not dry_run and removed:
        data["results"] = kept
        data["total_results"] = len(kept)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return stats


def main():
    parser = argparse.ArgumentParser(description="Clean up processed/ JSON files")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no file changes")
    args = parser.parse_args()

    processed_dir = Path(__file__).parent / "processed"
    if not processed_dir.exists():
        print(f"Error: {processed_dir} not found")
        return

    # Backup (skip for dry-run)
    if not args.dry_run:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = processed_dir.parent / f"processed_backup_{timestamp}"
        shutil.copytree(processed_dir, backup_dir)
        print(f"Backup created: {backup_dir}")

    # Find files to process (file_2 through file_8)
    files = sorted(processed_dir.glob("file_*.json"))
    if not files:
        print("No file_*.json found in processed/")
        return

    all_stats = []
    total_removed = 0
    total_original = 0

    for filepath in files:
        stats = process_file(filepath, args.dry_run)
        all_stats.append(stats)
        total_removed += stats["removed"]
        total_original += stats["original"]

        # Print summary for this file
        prefix = "[DRY-RUN] " if args.dry_run else ""
        print(f"\n{prefix}{stats['file']} (id={stats['file_id']}):")
        print(f"  {stats['original']} → {stats['kept']} (removed {stats['removed']})")
        if stats["reason_counts"]:
            for reason, count in sorted(stats["reason_counts"].items()):
                print(f"    - {reason}: {count}")

    print(f"\n{'=' * 50}")
    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(f"{prefix}Total: {total_original} → {total_original - total_removed} (removed {total_removed})")

    # Write cleanup log
    log_path = processed_dir.parent / "cleanup_log.json"
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "dry_run": args.dry_run,
        "total_original": total_original,
        "total_removed": total_removed,
        "files": all_stats,
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    print(f"\nLog written to: {log_path}")


if __name__ == "__main__":
    main()
