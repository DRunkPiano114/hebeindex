"""
dedup.py — Phase 2: Multi-layer deduplication.

Layer 1: Strong key dedup (YouTube video_id / Bilibili BVID / normalized URL)
Layer 2: Fuzzy title + duration matching (same platform only)

Cross-platform matches (YT + Bilibili same video) are kept — both links
preserved in aliases[] for the frontend.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from thefuzz import fuzz

from agent.utils import (
    extract_youtube_id,
    extract_bilibili_bvid,
    normalize_title,
    parse_duration_to_seconds,
)

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Fuzzy match thresholds
TITLE_SIMILARITY_THRESHOLD = 80
DURATION_TOLERANCE_SECONDS = 5


def _get_strong_key(item: dict) -> str | None:
    """Extract a strong dedup key: YouTube video_id, Bilibili BVID, or normalized URL."""
    source = item.get("source", "")
    if source == "youtube":
        vid = item.get("video_id") or extract_youtube_id(item.get("url", ""))
        return f"yt:{vid}" if vid else None
    if source == "bilibili":
        bvid = item.get("bvid") or extract_bilibili_bvid(item.get("url", ""))
        return f"bili:{bvid}" if bvid else None
    url = item.get("url", "").rstrip("/").lower()
    return f"url:{url}" if url else None


def _pick_winner(existing: dict, new: dict) -> dict:
    """Choose the better record. Official channel > higher views > newer."""
    # Prefer items from official channels (heuristic: has 'channel' with known names)
    e_official = _is_likely_official(existing)
    n_official = _is_likely_official(new)
    if n_official and not e_official:
        winner, loser = new, existing
    elif e_official and not n_official:
        winner, loser = existing, new
    else:
        # Higher view/play count wins
        e_count = existing.get("view_count", 0) or existing.get("play_count", 0) or 0
        n_count = new.get("view_count", 0) or new.get("play_count", 0) or 0
        if n_count > e_count:
            winner, loser = new, existing
        else:
            winner, loser = existing, new

    # Absorb loser URL into aliases
    loser_url = loser.get("url", "")
    if loser_url:
        aliases = winner.get("aliases", [])
        if loser_url not in aliases:
            aliases.append(loser_url)
        winner["aliases"] = aliases

    return winner


def _is_likely_official(item: dict) -> bool:
    """Heuristic: is this from an official channel?"""
    channel = (item.get("channel") or item.get("author") or "").lower()
    official_names = [
        "華研國際", "him international", "himshero",
        "hebe tien", "田馥甄", "hebe田馥甄官方",
    ]
    return any(name.lower() in channel for name in official_names)


def _strong_key_dedup(items: list[dict]) -> list[dict]:
    """Layer 1: Dedup by strong keys (video_id, BVID, URL)."""
    seen: dict[str, int] = {}  # key -> index in result list
    result: list[dict] = []

    for item in items:
        key = _get_strong_key(item)
        if key is None:
            result.append(item)
            continue

        if key in seen:
            idx = seen[key]
            result[idx] = _pick_winner(result[idx], item)
        else:
            seen[key] = len(result)
            result.append(item)

    before = len(items)
    after = len(result)
    logger.info("Layer 1 (strong key): %d -> %d (removed %d)", before, after, before - after)
    return result


def _fuzzy_dedup(items: list[dict]) -> list[dict]:
    """Layer 2: Fuzzy title + duration matching within the same platform."""
    # Group by source platform
    by_source: dict[str, list[tuple[int, dict]]] = {}
    for i, item in enumerate(items):
        src = item.get("source", "other")
        by_source.setdefault(src, []).append((i, item))

    merged_indices: set[int] = set()

    for source, group in by_source.items():
        n = len(group)
        for i in range(n):
            if group[i][0] in merged_indices:
                continue
            idx_a, item_a = group[i]
            title_a = normalize_title(item_a.get("title", ""))
            dur_a = item_a.get("duration_seconds", 0) or parse_duration_to_seconds(
                item_a.get("duration", "")
            )

            for j in range(i + 1, n):
                if group[j][0] in merged_indices:
                    continue
                idx_b, item_b = group[j]
                title_b = normalize_title(item_b.get("title", ""))
                dur_b = item_b.get("duration_seconds", 0) or parse_duration_to_seconds(
                    item_b.get("duration", "")
                )

                # Title similarity check
                similarity = fuzz.token_sort_ratio(title_a, title_b)
                if similarity < TITLE_SIMILARITY_THRESHOLD:
                    continue

                # Duration check (skip if both are 0 — unknown duration)
                if dur_a > 0 and dur_b > 0:
                    if abs(dur_a - dur_b) > DURATION_TOLERANCE_SECONDS:
                        continue

                # Merge: item_a absorbs item_b
                items[idx_a] = _pick_winner(items[idx_a], items[idx_b])
                merged_indices.add(idx_b)

    result = [item for i, item in enumerate(items) if i not in merged_indices]
    removed = len(merged_indices)
    logger.info("Layer 2 (fuzzy): %d -> %d (removed %d)", len(items), len(result), removed)
    return result


def run_dedup(lake_path: str | None = None) -> str:
    """Execute Phase 2: deduplicate the data lake.

    Returns path to the output file.
    """
    if lake_path is None:
        lake_path = os.path.join(DATA_DIR, "lake.json")

    with open(lake_path, "r", encoding="utf-8") as f:
        lake = json.load(f)

    items = lake["results"]
    logger.info("Phase 2 (dedup): starting with %d items", len(items))

    # Layer 1: Strong key dedup
    items = _strong_key_dedup(items)

    # Layer 2: Fuzzy dedup (same platform only)
    items = _fuzzy_dedup(items)

    # Save deduped results
    output_path = os.path.join(DATA_DIR, "deduped.json")
    output = {
        "phase": "dedup",
        "created_at": datetime.now().isoformat(),
        "input_count": lake["total_results"],
        "output_count": len(items),
        "reduction_pct": round((1 - len(items) / max(lake["total_results"], 1)) * 100, 1),
        "results": items,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info("Phase 2 complete: %d -> %d items (%.1f%% reduction) -> %s",
                lake["total_results"], len(items), output["reduction_pct"], output_path)
    return output_path
