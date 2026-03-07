"""
output.py — Phase 4: Group by category and write frontend-compatible JSON.

Output to collector/processed/file_{id}.json matching the existing schema.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from agent.models import CATEGORY_FILE_MAP

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PROCESSED_DIR = os.path.join(os.path.dirname(__file__), "..", "collector", "processed")

# Category metadata for output files
CATEGORY_META = {
    "personalMV": {
        "output_path": "MV/个人MV.md",
        "title": "田馥甄个人 MV 完整列表",
        "description": "按专辑分组，每首MV一行，含：歌名、链接、平台、发布日期、播放量、导演/频道、简介。",
    },
    "singles": {
        "output_path": "歌曲与合作/影视单曲.md",
        "title": "田馥甄影视歌曲与单曲",
        "description": "影视主题曲、官方数字单曲等非专辑收录作品。",
    },
    "concerts": {
        "output_path": "演唱会/演唱会.md",
        "title": "田馥甄演唱会视频",
        "description": "个人演唱会 + S.H.E 历代演唱会，区分官方影像、现场录像、精彩片段。",
    },
    "variety": {
        "output_path": "节目与访谈/综艺节目.md",
        "title": "田馥甄综艺节目视频",
        "description": "按节目分组：梦想的声音（逐期）、其他综艺、历史片段。每条注明原唱。",
    },
    "interviews": {
        "output_path": "节目与访谈/采访访谈.md",
        "title": "田馥甄采访与访谈视频",
        "description": "专访、采访、金曲奖访谈等。",
    },
    "sheMV": {
        "output_path": "MV/SHE_MV.md",
        "title": "S.H.E MV 完整列表",
        "description": "S.H.E MV 按年代排列，注明 Hebe 在各曲中的作用（领唱/主唱/合唱）。",
    },
    "collabs": {
        "output_path": "歌曲与合作/合唱合作.md",
        "title": "田馥甄合唱与合作",
        "description": "与其他歌手的合唱、合作视频。",
    },
}

# Official channel names for sort priority
OFFICIAL_CHANNELS = {
    "華研國際", "him international music", "himshero",
    "hebe tien's official channel田馥甄官方專屬頻道",
    "hebe tien - topic", "田馥甄 - 主題", "田馥甄hebe",
    "hebe田馥甄官方", "him international music inc.",
}


def _is_official(item: dict) -> bool:
    """Check if item is from an official channel."""
    channel = (item.get("channel") or item.get("author") or "").lower()
    return any(name.lower() in channel for name in OFFICIAL_CHANNELS)


def _sort_key(item: dict) -> tuple:
    """Sort key: official first, then by play count desc, then date desc."""
    official = 0 if _is_official(item) else 1
    count = -(item.get("view_count", 0) or item.get("play_count", 0) or 0)
    date = item.get("published_at", "0000-00-00")
    return (official, count, date)


def _to_content_item(item: dict) -> dict:
    """Convert internal item to frontend ContentItem format."""
    result: dict = {
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "source": item.get("source", "youtube"),
        "verified": item.get("verified", False) or False,
    }

    # Optional fields — only include if present
    for field in ["published_at", "view_count", "play_count", "channel",
                  "author", "duration", "verify_status", "search_query",
                  "bvid", "description"]:
        if item.get(field) is not None:
            result[field] = item[field]

    return result


def run_output(classified_path: str | None = None) -> list[str]:
    """Execute Phase 4: group by category and write file_{id}.json files.

    Returns list of output file paths.
    """
    if classified_path is None:
        classified_path = os.path.join(DATA_DIR, "classified.json")

    with open(classified_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data["results"]
    logger.info("Phase 4 (output): %d items to distribute", len(items))

    # Group by category
    groups: dict[str, list[dict]] = {}
    excluded_count = 0
    for item in items:
        cat = item.get("category", "")
        if cat == "exclude" or cat not in CATEGORY_FILE_MAP:
            excluded_count += 1
            continue
        groups.setdefault(cat, []).append(item)

    logger.info("Excluded %d items", excluded_count)

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    output_paths = []

    for cat_name, file_id in CATEGORY_FILE_MAP.items():
        cat_items = groups.get(cat_name, [])
        meta = CATEGORY_META.get(cat_name, {})

        # Sort
        cat_items.sort(key=_sort_key)

        # Convert to frontend format
        content_items = [_to_content_item(item) for item in cat_items]

        # Build output JSON
        output = {
            "file_id": file_id,
            "output_path": meta.get("output_path", f"file_{file_id}"),
            "title": meta.get("title", cat_name),
            "description": meta.get("description", ""),
            "processed_at": datetime.now().isoformat(),
            "total_results": len(content_items),
            "results": content_items,
        }

        output_path = os.path.join(PROCESSED_DIR, f"file_{file_id}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        output_paths.append(output_path)
        logger.info("Wrote %s: %d items -> %s", cat_name, len(content_items), output_path)

    logger.info("Phase 4 complete: %d files written", len(output_paths))
    return output_paths


def print_stats(classified_path: str | None = None) -> None:
    """Print classification statistics."""
    if classified_path is None:
        classified_path = os.path.join(DATA_DIR, "classified.json")

    if not os.path.exists(classified_path):
        print("No classified data found. Run the pipeline first.")
        return

    with open(classified_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n{'='*60}")
    print(f"V2 Agent Pipeline Statistics")
    print(f"{'='*60}")
    print(f"Total items: {data['total_items']}")

    print(f"\nCategory distribution:")
    for cat, count in sorted(data.get("category_stats", {}).items(), key=lambda x: -x[1]):
        pct = count / max(data["total_items"], 1) * 100
        bar = "#" * int(pct / 2)
        print(f"  {cat:15s}: {count:5d} ({pct:5.1f}%) {bar}")

    print(f"\nClassification method:")
    for method, count in sorted(data.get("method_stats", {}).items(), key=lambda x: -x[1]):
        pct = count / max(data["total_items"], 1) * 100
        print(f"  {method:10s}: {count:5d} ({pct:5.1f}%)")

    # Check for cross-file duplicate URLs
    groups: dict[str, set[str]] = {}
    for item in data["results"]:
        cat = item.get("category", "")
        if cat == "exclude":
            continue
        url = item.get("url", "")
        if url:
            groups.setdefault(cat, set()).add(url)

    all_urls = set()
    dup_count = 0
    for cat, urls in groups.items():
        overlap = urls & all_urls
        dup_count += len(overlap)
        all_urls |= urls

    print(f"\nCross-category duplicate URLs: {dup_count}")
    print(f"{'='*60}\n")

    # Also check intermediate files
    for phase_file in ["lake.json", "deduped.json"]:
        path = os.path.join(DATA_DIR, phase_file)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            count = d.get("total_results") or d.get("output_count") or len(d.get("results", []))
            print(f"  {phase_file}: {count} items")
            if "reduction_pct" in d:
                print(f"    Dedup reduction: {d['reduction_pct']}%")
