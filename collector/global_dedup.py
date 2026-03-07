"""
global_dedup.py — Global deduplication + same-content multi-version selection.

1. Exact dedup: YouTube by video ID, Bilibili by BVID
2. Fuzzy dedup: normalize titles, match with rapidfuzz token_sort_ratio >= 85
   - Same platform: keep best version (official channel > non-official; higher plays wins)
   - Cross platform: keep both, link them via cross_platform_url
"""

from __future__ import annotations

import re
import logging

from rapidfuzz import fuzz

from artist_profile import ArtistProfile, load_profile

logger = logging.getLogger(__name__)

# Noise words to strip before fuzzy matching
NOISE_PATTERNS = re.compile(
    r"\[MV\]|\(MV\)|【MV】|MV|Official|官方|HD|4K|1080[pP]|720[pP]|"
    r"纯享版|完整版|高清|字幕版|Lyric Video|Music Video|"
    r"官方版|正式版|full version|live version|"
    r"\s+",
    re.IGNORECASE,
)

FUZZY_THRESHOLD = 85


def normalize_title(title: str) -> str:
    """Normalize a title for fuzzy comparison."""
    t = NOISE_PATTERNS.sub(" ", title)
    t = re.sub(r"[^\w\s]", "", t)
    return t.strip().lower()


def extract_video_id(result: dict) -> str | None:
    """Extract platform-specific video ID."""
    source = result.get("source", "")
    if source == "youtube":
        url = result.get("url", "")
        if "v=" in url:
            return "yt:" + url.split("v=")[-1].split("&")[0]
        return ("yt:" + url) if url else None
    if source == "bilibili":
        bvid = result.get("bvid")
        return ("bili:" + bvid) if bvid else None
    return ("url:" + result.get("url", "")) if result.get("url") else None


def get_play_count(result: dict) -> int:
    """Get normalized play count regardless of platform."""
    return result.get("view_count") or result.get("play_count") or 0


def is_official_channel(result: dict, profile: ArtistProfile) -> bool:
    """Check if result is from an official channel."""
    channel = result.get("channel") or result.get("author") or ""
    return channel.strip() in set(profile.artist.official_channels)


def get_platform(result: dict) -> str:
    """Get platform from result."""
    source = result.get("source", "")
    if source == "youtube":
        return "youtube"
    if source == "bilibili":
        return "bilibili"
    return "other"


def global_dedup(
    results: list[dict],
    profile: ArtistProfile | None = None,
) -> list[dict]:
    """
    Deduplicate results globally.

    Returns deduplicated list with cross_platform_url set where applicable.
    """
    if profile is None:
        profile = load_profile()

    # Step 1: Exact dedup by video ID
    seen_ids: dict[str, int] = {}  # video_id -> index in unique list
    unique: list[dict] = []

    for r in results:
        vid = extract_video_id(r)
        if vid and vid in seen_ids:
            continue
        if vid:
            seen_ids[vid] = len(unique)
        unique.append(r)

    logger.info("Exact dedup: %d -> %d results", len(results), len(unique))

    # Step 2: Fuzzy dedup within same platform + cross-platform linking
    # Group by normalized title for fuzzy matching
    norm_map: list[tuple[str, int]] = []  # (normalized_title, index)
    for i, r in enumerate(unique):
        norm_map.append((normalize_title(r.get("title", "")), i))

    # Find fuzzy matches
    to_remove: set[int] = set()
    cross_links: dict[int, str] = {}  # index -> cross_platform_url

    matched: set[int] = set()
    for i in range(len(norm_map)):
        if i in to_remove or i in matched:
            continue
        cluster = [i]
        for j in range(i + 1, len(norm_map)):
            if j in to_remove or j in matched:
                continue
            score = fuzz.token_sort_ratio(norm_map[i][0], norm_map[j][0])
            if score >= FUZZY_THRESHOLD:
                cluster.append(j)
                matched.add(j)

        if len(cluster) <= 1:
            continue

        # Group cluster by platform
        by_platform: dict[str, list[int]] = {}
        for idx in cluster:
            plat = get_platform(unique[idx])
            by_platform.setdefault(plat, []).append(idx)

        # Within each platform, keep best version
        for plat, indices in by_platform.items():
            if len(indices) <= 1:
                continue
            best = _pick_best(indices, unique, profile)
            for idx in indices:
                if idx != best:
                    to_remove.add(idx)

        # Cross-platform linking
        platforms = list(by_platform.keys())
        if len(platforms) >= 2:
            # Pick best from each platform and link them
            bests = {}
            for plat in platforms:
                indices = [idx for idx in by_platform[plat] if idx not in to_remove]
                if indices:
                    bests[plat] = indices[0]  # already the best after within-platform dedup

            # Link YouTube <-> Bilibili
            if "youtube" in bests and "bilibili" in bests:
                yt_idx = bests["youtube"]
                bl_idx = bests["bilibili"]
                cross_links[yt_idx] = unique[bl_idx].get("url", "")
                cross_links[bl_idx] = unique[yt_idx].get("url", "")

    # Apply results
    deduped = []
    for i, r in enumerate(unique):
        if i in to_remove:
            continue
        if i in cross_links:
            r["cross_platform_url"] = cross_links[i]
        deduped.append(r)

    logger.info(
        "Fuzzy dedup: %d -> %d results (removed %d same-platform dupes, %d cross-platform links)",
        len(unique), len(deduped), len(to_remove), len(cross_links),
    )

    return deduped


def _pick_best(indices: list[int], results: list[dict], profile: ArtistProfile) -> int:
    """Pick the best version among same-content videos on the same platform."""
    def score(idx: int) -> tuple[int, int]:
        r = results[idx]
        official = 1 if is_official_channel(r, profile) else 0
        plays = get_play_count(r)
        return (official, plays)

    return max(indices, key=score)
