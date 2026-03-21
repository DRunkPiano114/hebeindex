#!/usr/bin/env python3
"""
reclassify.py — Reclassify existing video data based on content, not search query origin.

Usage:
    uv run python reclassify.py                        # full run (rules + LLM)
    uv run python reclassify.py --no-llm               # rules only, skip LLM
    uv run python reclassify.py --dry-run              # stats only, no file writes
    uv run python reclassify.py --output-dir reclass/  # custom output directory

Each classified item receives a confidence score (0.0-1.0) based on multiple signals:
    - Title keyword match strength (exact vs partial)
    - Source reliability (official channel vs random uploader)
    - Duration appropriateness for category
    - View count relative to artist average
    - Whether classification came from rules vs LLM fallback
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("reclassify")

BASE_DIR = Path(__file__).parent
PROCESSED_DIR = BASE_DIR / "processed"
ARTIST_YAML = BASE_DIR / "artist.yaml"

# Category key -> file_id mapping
CATEGORY_FILE_MAP = {
    "personal_mv": 2,
    "ost_singles": 3,
    "concerts": 4,
    "variety": 5,
    "interviews": 6,
    "group_mv": 7,
    "collabs": 8,
}

# ──────────────────────────────────────────────────────────────────────
# Load artist.yaml reference data
# ──────────────────────────────────────────────────────────────────────

def load_artist_data() -> dict:
    with open(ARTIST_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ──────────────────────────────────────────────────────────────────────
# Step 1: Merge & cross-file dedup
# ──────────────────────────────────────────────────────────────────────

def extract_youtube_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if "youtube.com" in host or "youtu.be" in host:
        if host == "youtu.be":
            return parsed.path.lstrip("/")
        qs = parse_qs(parsed.query)
        if "v" in qs:
            return qs["v"][0]
    return None


def dedup_key(item: dict) -> str:
    """Generate a dedup key for an item."""
    url = item.get("url", "")
    source = item.get("source", "")

    if source == "youtube":
        vid = extract_youtube_id(url)
        if vid:
            return f"yt:{vid}"

    if source == "bilibili":
        bvid = item.get("bvid", "")
        if bvid:
            return f"bili:{bvid}"

    return f"url:{url}"


def richness_score(item: dict) -> int:
    """Score how rich an item's metadata is (higher = better to keep)."""
    score = 0
    for key in ("title", "channel", "author", "description", "published_at", "duration"):
        if item.get(key):
            score += 1
    score += min((item.get("view_count") or item.get("play_count") or 0) // 1000, 100)
    if item.get("verified"):
        score += 5
    return score


def merge_and_dedup(file_ids: list[int], processed_dir: Path | None = None) -> list[dict]:
    """Read all processed files, merge, tag original_file_id, and cross-file dedup."""
    processed_dir = processed_dir or PROCESSED_DIR
    all_items = []
    for fid in file_ids:
        filepath = processed_dir / f"file_{fid}.json"
        if not filepath.exists():
            logger.warning("File not found: %s", filepath)
            continue
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("results", []):
            item["original_file_id"] = fid
            all_items.append(item)

    logger.info("Total items loaded: %d", len(all_items))

    # Dedup: group by key, keep the richest
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in all_items:
        key = dedup_key(item)
        groups[key].append(item)

    deduped = []
    dup_count = 0
    for key, items in groups.items():
        if len(items) > 1:
            dup_count += len(items) - 1
        best = max(items, key=richness_score)
        deduped.append(best)

    logger.info("After cross-file dedup: %d items (removed %d duplicates)", len(deduped), dup_count)
    return deduped


# ──────────────────────────────────────────────────────────────────────
# Step 2: Waterfall rule classification
# ──────────────────────────────────────────────────────────────────────

def build_classifier(data: dict):
    """Build a RuleClassifier from artist.yaml data."""
    return RuleClassifier(data)


def filter_low_views(
    classified: dict[str, list[dict]],
    official_channels: set[str],
    thresholds: dict[str, int] | None = None,
) -> dict[str, list[dict]]:
    """Move items with view counts below threshold to 'discard'.

    - Items with view_count=0/None are kept (API didn't return data).
    - Items from official channels are always exempt.
    """
    from config import MIN_VIEW_COUNT

    thresholds = thresholds or MIN_VIEW_COUNT
    default_threshold = thresholds.get("default", 1000)
    filtered = defaultdict(list)
    moved = 0

    for category, items in classified.items():
        if category == "discard":
            filtered["discard"].extend(items)
            continue

        threshold = thresholds.get(category, default_threshold)
        for item in items:
            views = item.get("view_count") or item.get("play_count")
            channel = item.get("channel") or item.get("author") or ""

            # Keep: no view data, or from official channel
            if not views or channel in official_channels:
                filtered[category].append(item)
                continue

            if views < threshold:
                item["classification_reason"] = "filtered_low_views"
                item["category"] = "discard"
                filtered["discard"].append(item)
                moved += 1
            else:
                filtered[category].append(item)

    if moved:
        logger.info("View count filter: moved %d items to discard", moved)

    return filtered


class RuleClassifier:
    def __init__(self, data: dict):
        self.data = data
        artist = data["artist"]
        group = data.get("group")
        disco = data["discography"]

        # Artist aliases for presence check
        self.artist_names = set(artist["names"]["aliases"] + [artist["names"]["primary"], artist["names"]["english"]])
        # Group aliases (optional — None for solo artists)
        self.has_group = group is not None
        if group:
            self.group_names = set([group["name"]] + group.get("aliases", []))
            self.group_member_names = set(group.get("member_names", []))
        else:
            self.group_names = set()
            self.group_member_names = set()

        # Official channels
        self.official_channels = set(artist.get("official_channels", []))

        # Solo album tracks (flat set)
        self.solo_tracks = set()
        for album in disco.get("solo_albums", []):
            self.solo_tracks.update(album["tracks"])

        # OST singles
        self.ost_singles = disco.get("ost_singles", [])
        self.ost_names = {s["name"] for s in self.ost_singles}
        self.ost_with_source = [(s["name"], s["source"]) for s in self.ost_singles if s.get("source")]

        # Variety show singles
        self.variety_singles = disco.get("variety_show_singles", [])
        self.variety_single_names = {s["name"] for s in self.variety_singles}

        # Concerts
        self.concerts = disco.get("concerts", [])
        self.group_concerts = disco.get("group_concerts", [])
        self._build_concert_patterns()

        # Variety shows
        self.variety_shows = disco.get("variety_shows", [])
        self.variety_show_names = {s["name"] for s in self.variety_shows}
        self.variety_networks = set()
        for s in self.variety_shows:
            if s.get("network"):
                self.variety_networks.add(s["network"])
        # Additional known TV channels
        self.variety_networks.update([
            "浙江卫视", "湖南卫视", "芒果TV", "芒果tv", "中天电视", "三立电视",
            "东方卫视", "CCTV", "央视", "江苏卫视", "北京卫视",
            "浙江衛視", "湖南衛視", "東方衛視",
        ])

        # Collaborators
        self.collaborators = disco.get("collaborators", [])
        self._build_collab_patterns()

        # Group MVs (e.g., S.H.E MVs)
        self.group_mvs = set(disco.get("group_mvs", []))

        # Blacklists
        self.western_blacklist = [s.lower() for s in disco.get("western_artist_blacklist", [])]
        self.chinese_blacklist = disco.get("other_chinese_artist_blacklist", [])
        _DEFAULT_NEGATIVE_PATTERNS = [
            "reaction", "反應", "反应",
            "翻唱", "cover version",
            "教學", "tutorial",
            "鈴聲", "铃声", "ringtone",
            "karaoke", "ktv",
            "piano cover", "guitar cover",
            "drum cover", "bass cover",
        ]
        self.wrong_context = (
            [s.lower() for s in disco.get("wrong_context_patterns", [])]
            + [s.lower() for s in _DEFAULT_NEGATIVE_PATTERNS]
        )

        # Known venues
        self.venues = ["小巨蛋", "红馆", "紅館", "巨蛋", "体育馆", "體育館",
                       "卫武营", "衛武營", "Legacy", "两厅院", "兩廳院"]

        # Known interview media channels
        self.interview_channels = [
            "娱乐星天地", "ETtoday", "TVBS", "三立新闻", "东森新闻", "中时",
            "联合报", "自由时报", "苹果日报", "壹周刊", "GQ", "ELLE", "Vogue",
            "BAZAAR", "InStyle", "Marie Claire", "Esquire", "理科太太",
            "唐绮阳", "聯合報", "自由時報",
        ]

    def _build_concert_patterns(self):
        """Build regex-friendly concert name patterns."""
        self.concert_names = []
        self.concert_aliases = []
        for c in self.concerts:
            self.concert_names.append(c["name"])
            for alias in c.get("aliases", []):
                self.concert_aliases.append(alias)
        for c in self.group_concerts:
            self.concert_names.append(c["name"])

    def _build_collab_patterns(self):
        """Build collaborator lookup."""
        self.collab_name_songs: dict[str, list[str]] = {}
        self.collab_all_names: list[str] = []
        for c in self.collaborators:
            names = [c["name"]] + c.get("aliases", [])
            songs = c.get("songs", [])
            for n in names:
                self.collab_name_songs[n] = songs
                self.collab_all_names.append(n)

    def _title_lower(self, item: dict) -> str:
        return (item.get("title") or "").lower()

    def _title(self, item: dict) -> str:
        return item.get("title") or ""

    def _channel(self, item: dict) -> str:
        return item.get("channel") or item.get("author") or ""

    def _has_artist_name(self, text: str) -> bool:
        for name in self.artist_names:
            if name.lower() in text.lower():
                return True
        return False

    def _has_group_name(self, text: str) -> bool:
        t = text.lower()
        for name in self.group_names:
            if name.lower() in t:
                return True
        return False

    def _has_live_indicator(self, title: str) -> bool:
        t = title.lower()
        return bool(re.search(r'live|演唱会|演唱會|concert|现场|現場|演出', t))

    def _has_other_category_indicator(self, title: str) -> bool:
        """Check if title has indicators for concerts, variety, interviews, or collabs."""
        t = title.lower()
        # Concert indicators
        if re.search(r'演唱会|演唱會|concert|巡演|巡迴', t):
            return True
        for name in self.concert_names + self.concert_aliases:
            if name.lower() in t:
                return True
        # Variety indicators
        for show in self.variety_show_names:
            if show in title:
                return True
        if re.search(r'颁奖|頒獎|晚会|晚會|典礼|典禮|盛典|跨年|第\d+期|EP\d+', t):
            return True
        # Interview indicators
        if re.search(r'采访|採訪|专访|專訪|访谈|訪談|interview|幕后|幕後|花絮|记者会|記者會|发布会|發布會', t):
            return True
        # Collab indicators
        if re.search(r'feat|ft\.|合唱|合作|duet|×', t):
            return True
        for collab_name in self.collab_all_names:
            if collab_name in title:
                return True
        return False

    def _duration_seconds(self, item: dict) -> int | None:
        dur = item.get("duration", "")
        if not dur:
            return None
        parts = dur.split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            return None
        return None

    def _detect_song_performance(self, item: dict) -> bool:
        """Return True if this item is actually a song/concert performance,
        not variety or interview content. Used by Rules 6 & 7 to let these
        items fall through to Rule 5 (concerts) instead."""
        title = self._title(item)
        title_lower = self._title_lower(item)

        # Guard: if a known variety show name is present, variety context wins
        for show in self.variety_show_names:
            if show in title:
                return False

        has_known_track = any(t in title for t in self.solo_tracks)
        has_known_ost = any(t in title for t in self.ost_names)
        has_known_group_track = any(t.lower() in title_lower for t in self.group_mvs)
        has_track = has_known_track or has_known_ost or has_known_group_track

        # Check 1: Known track + concert name → concert footage
        has_concert = any(
            c in title or c.lower() in title_lower
            for c in self.concert_names + self.concert_aliases
        )
        if has_track and has_concert:
            return True

        # Check 2: Known track + live indicators, no interview framing
        if has_track:
            has_live = bool(re.search(r'live|現場|现场|演唱會|演唱会|concert', title_lower))
            has_interview_frame = bool(re.search(
                r'采访|採訪|专访|專訪|访谈|訪談|interview|幕后|幕後', title_lower))
            if has_live and not has_interview_frame:
                return True

        # Check 3: Multiple track names → medley/concert compilation
        track_count = sum(1 for t in self.solo_tracks if t in title)
        track_count += sum(1 for t in self.ost_names if t in title)
        if track_count >= 2:
            return True

        return False

    # ── Rule 0: Blacklist ──
    def _rule0_blacklist(self, item: dict) -> str | None:
        title = self._title(item)
        title_lower = self._title_lower(item)
        channel = self._channel(item).lower()

        # Wrong context patterns — always discard
        for pat in self.wrong_context:
            if pat in title_lower:
                return "rule0_wrong_context"

        # Western/Chinese artist blacklist: discard if title has blacklisted artist
        # AND title does NOT contain any of our artist's names
        has_artist = self._has_artist_name(title)

        for artist in self.western_blacklist:
            if artist in title_lower or artist in channel:
                if not has_artist:
                    return "rule0_western_blacklist"

        for artist in self.chinese_blacklist:
            if artist in title or artist in self._channel(item):
                if not has_artist:
                    return "rule0_chinese_blacklist"

        # Artist relevance gate: discard if no connection to artist at all
        relevance = self._is_artist_irrelevant(item, title)
        if relevance:
            return relevance

        return None

    def _is_artist_irrelevant(self, item: dict, title: str) -> str | None:
        """Check if the video has no connection to the target artist."""
        channel = self._channel(item)

        # Exempt: official channels are always relevant
        if channel in self.official_channels:
            return None

        # Exempt: title contains artist name
        if self._has_artist_name(title):
            return None

        # Exempt: title contains group name
        if self._has_group_name(title):
            return None

        # Exempt: title contains known content (track, concert, OST, variety show, collab song)
        for track in self.solo_tracks:
            if track in title:
                return None
        for name in self.concert_names + self.concert_aliases:
            if name in title or name.lower() in title.lower():
                return None
        for name in self.ost_names:
            if name in title:
                return None
        for name in self.variety_show_names:
            if name in title:
                return None
        for track in self.group_mvs:
            if track.lower() in title.lower():
                return None
        for collab_name, songs in self.collab_name_songs.items():
            for song in songs:
                if song in title:
                    return None
        for venue in self.venues:
            if venue in title:
                return None

        # No connection to artist found
        return "rule0_artist_not_primary"

    # ── Rule 1: Personal MV ──
    def _rule1_personal_mv(self, item: dict) -> str | None:
        title = self._title(item)
        title_lower = self._title_lower(item)
        channel = self._channel(item)

        # Exclude if S.H.E related
        if self._has_group_name(title) and not self._has_artist_name(title):
            return None
        # Official channel + Official MV marker
        is_official_channel = channel in self.official_channels
        has_mv_marker = bool(re.search(r'official\s*mv|official\s*music\s*video|官方\s*mv', title_lower))

        if is_official_channel and has_mv_marker:
            # Check it's not S.H.E
            if not self._has_group_name(title):
                return "rule1_official_mv"

        # Known solo track + MV keyword, no live indicator
        if not self._has_live_indicator(title):
            for track in self.solo_tracks:
                if track in title:
                    if re.search(r'mv|music\s*video', title_lower):
                        if not self._has_group_name(title):
                            # Check it's not also an OST with movie name present
                            is_ost_context = False
                            for ost_name, ost_source in self.ost_with_source:
                                if ost_name == track and ost_source and ost_source in title:
                                    is_ost_context = True
                                    break
                            if not is_ost_context:
                                return "rule1_known_track_mv"

        # Broader: Known solo track + Hebe name, no live/concert/variety/interview indicator
        # Catches lyric videos, KTV, audio uploads, fan edits
        if not self._has_live_indicator(title) and not self._has_other_category_indicator(title):
            for track in self.solo_tracks:
                if track in title and self._has_artist_name(title):
                    if not self._has_group_name(title):
                        # Exclude if OST context
                        is_ost_context = False
                        for ost_name, ost_source in self.ost_with_source:
                            if ost_name == track and ost_source and ost_source in title:
                                is_ost_context = True
                                break
                        if not is_ost_context:
                            return "rule1_known_track_broad"

        return None

    # ── Rule 2: Group MV (e.g., S.H.E) ──
    def _rule2_she_mv(self, item: dict) -> str | None:
        if not self.has_group:
            return None

        title = self._title(item)
        title_lower = self._title_lower(item)

        has_she = self._has_group_name(title)
        has_mv = bool(re.search(r'mv|music\s*video', title_lower))

        if has_she and has_mv and not self._has_live_indicator(title):
            return "rule2_she_mv"

        # Known S.H.E MV track + MV marker
        if not self._has_live_indicator(title):
            for track in self.group_mvs:
                if track.lower() in title_lower:
                    if has_mv:
                        return "rule2_she_known_track_mv"

        # Broader: Known S.H.E track + S.H.E name (no MV keyword needed)
        if not self._has_live_indicator(title) and not self._has_other_category_indicator(title):
            if has_she:
                for track in self.group_mvs:
                    if track.lower() in title_lower:
                        return "rule2_she_known_track_broad"

        return None

    # ── Rule 3: OST / Singles ──
    def _rule3_ost_singles(self, item: dict) -> str | None:
        title = self._title(item)
        title_lower = self._title_lower(item)

        # Known OST + corresponding movie/show name
        for ost_name, ost_source in self.ost_with_source:
            if ost_name in title and ost_source and ost_source in title:
                if not self._has_live_indicator(title):
                    return "rule3_ost_with_source"

        # Known OST name + Official/MV marker, no live
        for ost in self.ost_singles:
            if ost["name"] in title:
                if re.search(r'official|mv|官方|music\s*video|lyrics?\s*video|lyric', title_lower):
                    if not self._has_live_indicator(title):
                        # Disambiguate: if also a solo track, check if movie name present
                        if ost["name"] in self.solo_tracks and ost.get("source"):
                            if ost["source"] not in title:
                                continue  # Let rule 1 handle it
                        return "rule3_ost_official"

        # Variety show digital singles (e.g., 梦想的声音 singles)
        for vs in self.variety_singles:
            if vs["name"] in title:
                if re.search(r'单曲|digital|数位', title_lower):
                    return "rule3_variety_single"

        # Broader: Known OST name + Hebe name, no live indicator, not a solo album track
        if not self._has_live_indicator(title):
            for ost in self.ost_singles:
                if ost["name"] in title and self._has_artist_name(title):
                    # Only if it's NOT also a solo album track (avoid stealing from rule 1)
                    if ost["name"] not in self.solo_tracks:
                        return "rule3_ost_broad"

        return None

    # ── Rule 4: Collaborations ──
    def _rule4_collabs(self, item: dict) -> str | None:
        title = self._title(item)
        title_lower = self._title_lower(item)

        for collab_name, songs in self.collab_name_songs.items():
            if collab_name in title or collab_name.lower() in title_lower:
                # Collaborator name + known collab song
                for song in songs:
                    if song in title:
                        return "rule4_collab_known_song"
                # Collaborator + feat/ft/合唱 pattern
                if re.search(r'feat|ft\.?|×|合唱|合作|duet|collaboration|&', title_lower):
                    if self._has_artist_name(title):
                        return "rule4_collab_pattern"

        return None

    # ── Rule 5: Concerts ──
    def _rule5_concerts(self, item: dict) -> str | None:
        title = self._title(item)
        title_lower = self._title_lower(item)
        channel = self._channel(item)

        # Known concert name or alias
        for name in self.concert_names + self.concert_aliases:
            if name in title or name.lower() in title_lower:
                return "rule5_known_concert"

        # S.H.E concert names
        for c in self.group_concerts:
            name = c["name"]
            # Match partial (e.g., "奇幻乐园" from "SHE 奇幻乐园演唱会")
            short_name = name.replace("SHE ", "").replace("S.H.E ", "")
            if short_name in title:
                return "rule5_she_concert"

        # 演唱会/Concert + Hebe/S.H.E name
        if re.search(r'演唱会|演唱會|concert', title_lower):
            if self._has_artist_name(title) or self._has_group_name(title):
                return "rule5_concert_keyword"

        # Long duration (>30min) + Live/现场 + Hebe name (not variety show)
        dur = self._duration_seconds(item)
        if dur and dur > 1800:
            if re.search(r'live|现场|現場|全场|全場', title_lower):
                if self._has_artist_name(title):
                    # Exclude if it matches a known variety show
                    is_variety = any(v in title for v in self.variety_show_names)
                    if not is_variety:
                        return "rule5_long_live"

        # Known venue + Hebe name
        for venue in self.venues:
            if venue in title:
                if self._has_artist_name(title) or self._has_group_name(title):
                    if re.search(r'live|现场|現場|演出|演唱', title_lower):
                        return "rule5_venue"

        return None

    # ── Rule 6: Variety shows ──
    def _rule6_variety(self, item: dict) -> str | None:
        # Concert footage misclassified as variety → let Rule 5 handle it
        if self._detect_song_performance(item):
            return None

        title = self._title(item)
        title_lower = self._title_lower(item)
        channel = self._channel(item)

        # Known variety show name
        for show_name in self.variety_show_names:
            if show_name in title:
                # Boundary: if also has interview markers and no performance markers
                if re.search(r'专访|採訪|采访|访谈|訪談|interview', title_lower):
                    if not re.search(r'表演|演唱|演出|perform', title_lower):
                        return None  # Let rule 7 (interviews) handle it
                return "rule6_known_show"

        # Known TV network channel
        for net in self.variety_networks:
            if net in channel or net in title:
                if self._has_artist_name(title) or self._has_group_name(title):
                    return "rule6_tv_network"

        # Award shows / galas
        if re.search(r'颁奖|頒獎|晚会|晚會|典礼|典禮|盛典|跨年', title_lower):
            if self._has_artist_name(title) or self._has_group_name(title):
                return "rule6_award_gala"

        # Episode pattern
        if re.search(r'第\d+期|EP\d+|ep\d+', title):
            if self._has_artist_name(title) or self._has_group_name(title):
                return "rule6_episode_pattern"

        return None

    # ── Rule 7: Interviews ──
    def _rule7_interviews(self, item: dict) -> str | None:
        # Concert footage misclassified as interview → let Rule 5 handle it
        if self._detect_song_performance(item):
            return None

        title = self._title(item)
        title_lower = self._title_lower(item)
        channel = self._channel(item)

        # Interview keywords
        if re.search(r'采访|採訪|专访|專訪|访谈|訪談|interview', title_lower):
            return "rule7_interview_keyword"

        # Behind-the-scenes / press
        if re.search(r'幕后|幕後|花絮|记者会|記者會|发布会|發布會|press\s*conference', title_lower):
            return "rule7_behind_scenes"

        # News / report
        if re.search(r'新闻|新聞|报道|報導|独家|獨家', title_lower):
            if self._has_artist_name(title):
                return "rule7_news"

        # Known interview media channel
        for media in self.interview_channels:
            if media in channel:
                if self._has_artist_name(title) or self._has_group_name(title):
                    return "rule7_media_channel"

        return None

    def classify(self, item: dict) -> tuple[str, str]:
        """
        Classify a single item through the waterfall rules.
        Returns (category_key, reason).
        """
        # Rule 0: Blacklist
        reason = self._rule0_blacklist(item)
        if reason:
            return "discard", reason

        # Rule 1: Personal MV
        reason = self._rule1_personal_mv(item)
        if reason:
            return "personal_mv", reason

        # Rule 2: Group MV
        reason = self._rule2_she_mv(item)
        if reason:
            return "group_mv", reason

        # Rule 3: OST / Singles
        reason = self._rule3_ost_singles(item)
        if reason:
            return "ost_singles", reason

        # Rule 4: Collaborations
        reason = self._rule4_collabs(item)
        if reason:
            return "collabs", reason

        # Rule 5: Concerts
        reason = self._rule5_concerts(item)
        if reason:
            return "concerts", reason

        # Rule 6: Variety
        reason = self._rule6_variety(item)
        if reason:
            return "variety", reason

        # Rule 7: Interviews
        reason = self._rule7_interviews(item)
        if reason:
            return "interviews", reason

        return "unclassified", "no_rule_match"


# ──────────────────────────────────────────────────────────────────────
# Confidence scoring
# ──────────────────────────────────────────────────────────────────────

# Expected duration ranges per category (seconds): (min, ideal_min, ideal_max, max)
DURATION_RANGES: dict[str, tuple[int, int, int, int]] = {
    "personal_mv": (120, 180, 360, 480),
    "group_mv": (120, 180, 360, 480),
    "ost_singles": (120, 180, 360, 480),
    "collabs": (120, 180, 420, 600),
    "concerts": (300, 1800, 7200, 14400),
    "variety": (120, 300, 5400, 7200),
    "interviews": (60, 180, 3600, 7200),
}

# Strong rule reasons — these indicate high-confidence rule matches
STRONG_RULE_REASONS = {
    "rule1_official_mv",
    "rule1_known_track_mv",
    "rule2_she_mv",
    "rule2_she_known_track_mv",
    "rule3_ost_with_source",
    "rule3_ost_official",
    "rule4_collab_known_song",
    "rule5_known_concert",
    "rule5_she_concert",
    "rule6_known_show",
    "rule0_wrong_context",
    "rule0_western_blacklist",
    "rule0_chinese_blacklist",
    "rule0_artist_not_primary",
}

# Medium rule reasons — decent match but less certain
MEDIUM_RULE_REASONS = {
    "rule1_known_track_broad",
    "rule2_she_known_track_broad",
    "rule3_ost_broad",
    "rule3_variety_single",
    "rule4_collab_pattern",
    "rule5_concert_keyword",
    "rule5_long_live",
    "rule5_venue",
    "rule6_tv_network",
    "rule6_award_gala",
    "rule6_episode_pattern",
    "rule7_interview_keyword",
    "rule7_behind_scenes",
    "rule7_news",
    "rule7_media_channel",
}


class ConfidenceScorer:
    """Compute multi-signal confidence scores for classified items."""

    def __init__(self, classifier: RuleClassifier):
        self.classifier = classifier

    def _duration_seconds(self, item: dict) -> int | None:
        """Parse duration string to seconds."""
        dur = item.get("duration", "")
        if not dur:
            return None
        parts = dur.split(":")
        try:
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            return None
        return None

    def signal_rule_strength(self, reason: str) -> tuple[str, float]:
        """Score based on which rule matched and how specific it was.
        Returns (signal_name, score) where score is 0.0-1.0."""
        if reason in STRONG_RULE_REASONS:
            return ("rule_strength", 1.0)
        if reason in MEDIUM_RULE_REASONS:
            return ("rule_strength", 0.7)
        if reason.startswith("llm_"):
            return ("rule_strength", 0.5)
        if reason == "no_rule_match":
            return ("rule_strength", 0.0)
        # Unknown rule — treat as medium
        return ("rule_strength", 0.6)

    def signal_source_reliability(self, item: dict) -> tuple[str, float]:
        """Score based on the source channel's reliability."""
        channel = item.get("channel") or item.get("author") or ""
        source = item.get("source", "")

        # Official channel = highest reliability
        if channel in self.classifier.official_channels:
            return ("source_reliability", 1.0)

        # YouTube Topic channels (auto-generated, reliable metadata)
        if "- Topic" in channel or "- 主題" in channel:
            return ("source_reliability", 0.85)

        # YouTube source with verified status
        if source == "youtube" and item.get("verified"):
            return ("source_reliability", 0.7)

        # Bilibili verified
        if source == "bilibili" and item.get("verified"):
            return ("source_reliability", 0.6)

        # Known media/label channels
        labels = set(self.classifier.data.get("artist", {}).get("labels", []))
        if channel in labels:
            return ("source_reliability", 0.9)

        # Unverified or unknown
        if item.get("verified") is False:
            return ("source_reliability", 0.3)

        return ("source_reliability", 0.5)

    def signal_duration_fit(self, item: dict, category: str) -> tuple[str, float]:
        """Score how well the item's duration fits the expected range for its category."""
        dur = self._duration_seconds(item)
        if dur is None or category not in DURATION_RANGES:
            return ("duration_fit", 0.5)  # neutral when unknown

        lo, ideal_lo, ideal_hi, hi = DURATION_RANGES[category]

        if ideal_lo <= dur <= ideal_hi:
            return ("duration_fit", 1.0)
        if lo <= dur <= hi:
            # Proportional score for being within the acceptable range
            if dur < ideal_lo:
                score = 0.6 + 0.4 * (dur - lo) / max(ideal_lo - lo, 1)
            else:
                score = 0.6 + 0.4 * (hi - dur) / max(hi - ideal_hi, 1)
            return ("duration_fit", round(min(max(score, 0.6), 1.0), 2))
        # Outside acceptable range
        return ("duration_fit", 0.2)

    def signal_view_count(self, item: dict) -> tuple[str, float]:
        """Score based on view count — higher views generally mean more legitimate content."""
        views = item.get("view_count") or item.get("play_count") or 0
        if views == 0:
            return ("view_count", 0.4)  # unknown/zero views
        if views >= 1_000_000:
            return ("view_count", 1.0)
        if views >= 100_000:
            return ("view_count", 0.85)
        if views >= 10_000:
            return ("view_count", 0.7)
        if views >= 1_000:
            return ("view_count", 0.55)
        return ("view_count", 0.4)

    def signal_title_keyword_match(self, item: dict, category: str) -> tuple[str, float]:
        """Score based on how strongly the title matches expected keywords for the category."""
        title = (item.get("title") or "").lower()

        if category == "personal_mv":
            if re.search(r'official\s*mv|official\s*music\s*video|官方\s*mv', title):
                return ("title_match", 1.0)
            if re.search(r'\bmv\b|music\s*video', title):
                return ("title_match", 0.8)
            if any(t.lower() in title for t in self.classifier.solo_tracks):
                return ("title_match", 0.6)
            return ("title_match", 0.3)

        if category == "group_mv":
            has_she = self.classifier._has_group_name(item.get("title", ""))
            has_mv = bool(re.search(r'\bmv\b|music\s*video', title))
            if has_she and has_mv:
                return ("title_match", 1.0)
            if has_she or has_mv:
                return ("title_match", 0.6)
            return ("title_match", 0.3)

        if category == "concerts":
            if re.search(r'演唱会|演唱會|concert', title):
                return ("title_match", 1.0)
            if re.search(r'live|现场|現場|巡演', title):
                return ("title_match", 0.7)
            return ("title_match", 0.3)

        if category == "variety":
            if any(s.lower() in title for s in self.classifier.variety_show_names):
                return ("title_match", 1.0)
            if re.search(r'颁奖|頒獎|晚会|晚會|典礼|典禮|跨年', title):
                return ("title_match", 0.8)
            return ("title_match", 0.3)

        if category == "interviews":
            if re.search(r'采访|採訪|专访|專訪|访谈|訪談|interview', title):
                return ("title_match", 1.0)
            if re.search(r'幕后|幕後|花絮|记者会|記者會', title):
                return ("title_match", 0.8)
            return ("title_match", 0.3)

        if category == "ost_singles":
            if any(n.lower() in title for n in self.classifier.ost_names):
                return ("title_match", 0.9)
            if re.search(r'ost|主题曲|主題曲|插曲|片尾曲', title):
                return ("title_match", 0.8)
            return ("title_match", 0.3)

        if category == "collabs":
            if re.search(r'feat|ft\.|×|合唱|duet', title):
                return ("title_match", 1.0)
            for name in self.classifier.collab_all_names:
                if name.lower() in title:
                    return ("title_match", 0.8)
            return ("title_match", 0.3)

        return ("title_match", 0.5)

    def score(self, item: dict, category: str, reason: str) -> tuple[float, dict[str, float]]:
        """Compute overall confidence score and individual signal breakdown.

        Returns:
            (confidence, signals) where confidence is 0.0-1.0 and signals is
            a dict mapping signal names to their individual scores.
        """
        if category == "discard":
            # Discarded items: confidence represents how sure we are it should be discarded
            rule_name, rule_score = self.signal_rule_strength(reason)
            signals = {rule_name: rule_score}
            return (rule_score, signals)

        signals: dict[str, float] = {}

        # Gather all signals
        name, val = self.signal_rule_strength(reason)
        signals[name] = val

        name, val = self.signal_source_reliability(item)
        signals[name] = val

        name, val = self.signal_duration_fit(item, category)
        signals[name] = val

        name, val = self.signal_view_count(item)
        signals[name] = val

        name, val = self.signal_title_keyword_match(item, category)
        signals[name] = val

        # Weighted average: rule_strength is the most important signal
        weights = {
            "rule_strength": 0.35,
            "title_match": 0.25,
            "source_reliability": 0.20,
            "duration_fit": 0.10,
            "view_count": 0.10,
        }

        total_weight = sum(weights.get(k, 0.1) for k in signals)
        confidence = sum(signals[k] * weights.get(k, 0.1) for k in signals) / total_weight
        confidence = round(min(max(confidence, 0.0), 1.0), 3)

        return (confidence, signals)


# ──────────────────────────────────────────────────────────────────────
# Step 3: LLM fallback for unclassified items
# ──────────────────────────────────────────────────────────────────────

LLM_SYSTEM_PROMPT = """你是一个视频分类助手。请将以下田馥甄（Hebe Tien）相关的视频分类到以下类别之一：

- personal_mv: 田馥甄个人MV（官方音乐录影带，非现场版）
- group_mv: S.H.E 团体MV
- ost_singles: 影视单曲、OST、数字单曲（非专辑收录的独立发行曲目）
- collabs: 合唱合作（与其他歌手的合唱、feat、合作视频）
- concerts: 演唱会（个人或S.H.E演唱会完整场/片段/花絮）
- variety: 综艺节目（综艺出演、颁奖典礼表演、跨年晚会）
- interviews: 采访访谈（专访、幕后花絮、记者会、新闻报道）
- discard: 与田馥甄无关的内容

请严格按照JSON格式输出，每条一个JSON对象，用JSON array包裹：
[{"index": 0, "category": "category_key", "reason": "简短理由"}]

注意：
1. 演唱会片段即使很短，只要能确认来自某场演唱会，仍归concerts
2. 综艺节目中的表演片段归variety，除非是纯采访内容
3. MV必须是音乐录影带，不是现场演唱
4. 如果无法确定，请归入最可能的类别"""


def build_llm_prompt(profile) -> str:
    """Generate LLM classification prompt from artist profile."""
    primary = profile.artist.names.primary
    english = profile.artist.names.english
    categories = profile.categories
    cat_lines = []
    for cat in categories:
        cat_lines.append(f"- {cat.key}: {cat.description or cat.label}")
    cat_lines.append(f"- discard: 与{primary}无关的内容")
    cat_block = "\n".join(cat_lines)

    return f"""你是一个视频分类助手。请将以下{primary}（{english}）相关的视频分类到以下类别之一：

{cat_block}

请严格按照JSON格式输出，每条一个JSON对象，用JSON array包裹：
[{{"index": 0, "category": "category_key", "reason": "简短理由"}}]

注意：
1. 演唱会片段即使很短，只要能确认来自某场演唱会，仍归concerts
2. 综艺节目中的表演片段归variety，除非是纯采访内容
3. MV必须是音乐录影带，不是现场演唱
4. 如果无法确定，请归入最可能的类别"""


def llm_classify_parallel(
    unclassified_items: list[tuple[int, dict]],
    max_workers: int = 4,
    batch_size: int = 20,
    system_prompt: str | None = None,
    valid_categories: list[str] | None = None,
) -> list[tuple[int, dict, str, str]]:
    """Classify unclassified items via LLM in parallel batches.
    Returns list of (original_index, item, category, reason).
    Uses claude_llm.classify_batch() via the claude CLI."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from claude_llm import classify_batch

    prompt = system_prompt or LLM_SYSTEM_PROMPT
    valid_categories = valid_categories or list(CATEGORY_FILE_MAP.keys())

    # Split into batches
    batches: list[list[tuple[int, dict]]] = []
    for i in range(0, len(unclassified_items), batch_size):
        batches.append(unclassified_items[i:i + batch_size])

    total_batches = len(batches)
    logger.info("LLM fallback: %d items in %d batches, %d parallel workers",
                len(unclassified_items), total_batches, max_workers)

    all_results: list[tuple[int, dict, str, str]] = []
    completed = 0

    def _classify_one_batch(batch_idx: int, batch: list[tuple[int, dict]]) -> list[tuple[int, dict, str, str]]:
        batch_items = [item for _, item in batch]
        try:
            raw = classify_batch(
                items=batch_items,
                categories=valid_categories,
                artist_name="",
                system_prompt=prompt,
            )
            results_map = {}
            for r in raw:
                idx = r.get("index", -1)
                cat = r.get("category", "unclassified")
                reason = r.get("reason", "llm_fallback")
                if cat not in set(valid_categories) | {"discard"}:
                    cat = "unclassified"
                results_map[idx] = (cat, f"llm_{reason}")

            return [
                (orig_idx, item, *results_map.get(i, ("unclassified", "llm_missing_index")))
                for i, (orig_idx, item) in enumerate(batch)
            ]
        except Exception as e:
            logger.error("Batch %d LLM error: %s", batch_idx, e)
            return [(orig_idx, item, "unclassified", "llm_error") for orig_idx, item in batch]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_batch = {}
        for batch_idx, batch in enumerate(batches):
            future = executor.submit(_classify_one_batch, batch_idx, batch)
            future_to_batch[future] = batch_idx

        for future in as_completed(future_to_batch):
            batch_results = future.result()
            all_results.extend(batch_results)
            completed += 1
            if completed % 10 == 0 or completed == total_batches:
                logger.info("LLM progress: %d/%d batches done", completed, total_batches)

    return all_results


# ──────────────────────────────────────────────────────────────────────
# Step 4: Output
# ──────────────────────────────────────────────────────────────────────

# Original file metadata (from search_plan.py)
FILE_METADATA = {
    2: {"output_path": "MV/个人MV.md", "title": "田馥甄个人 MV 完整列表", "description": "按专辑分组，每首MV一行，含：歌名、链接、平台、发布日期、播放量、导演/频道、简介。"},
    3: {"output_path": "歌曲与合作/影视单曲.md", "title": "田馥甄影视歌曲与单曲", "description": "影视主题曲、官方数字单曲等非专辑收录作品。"},
    4: {"output_path": "演唱会/演唱会.md", "title": "田馥甄演唱会视频", "description": "个人演唱会 + S.H.E 历代演唱会，区分官方影像、现场录像、精彩片段。"},
    5: {"output_path": "节目与访谈/综艺节目.md", "title": "田馥甄综艺节目视频", "description": "按节目分组：梦想的声音（逐期）、其他综艺、历史片段。每条注明原唱。"},
    6: {"output_path": "节目与访谈/采访访谈.md", "title": "田馥甄采访与访谈视频", "description": "专访、采访、金曲奖访谈等。"},
    7: {"output_path": "MV/SHE_MV.md", "title": "S.H.E MV 完整列表", "description": "S.H.E MV 按年代排列，注明 Hebe 在各曲中的作用（领唱/主唱/合唱）。"},
    8: {"output_path": "歌曲与合作/合唱合作.md", "title": "田馥甄合唱与合作", "description": "与其他歌手的合唱、合作视频。"},
}


def write_output(
    classified: dict[str, list[dict]],
    output_dir: Path,
    category_file_map: dict[str, int] | None = None,
    file_metadata: dict[int, dict] | None = None,
):
    """Write classified items back to processed JSON files."""
    from datetime import datetime

    category_file_map = category_file_map or CATEGORY_FILE_MAP
    file_metadata = file_metadata or FILE_METADATA

    output_dir.mkdir(parents=True, exist_ok=True)

    for category_key, file_id in category_file_map.items():
        items = classified.get(category_key, [])
        meta = file_metadata.get(file_id, {"output_path": "", "title": category_key, "description": ""})

        # Strip internal classification fields from results for frontend compat
        clean_results = []
        for item in items:
            result = dict(item)
            # Keep category and classification_reason as new fields
            # Keep original_file_id for audit
            clean_results.append(result)

        output = {
            "file_id": file_id,
            "output_path": meta["output_path"],
            "title": meta["title"],
            "description": meta["description"],
            "processed_at": datetime.now().isoformat(),
            "total_results": len(clean_results),
            "results": clean_results,
        }

        filepath = output_dir / f"file_{file_id}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info("Wrote %s: %d items", filepath.name, len(clean_results))

    # Write discarded items
    discarded = classified.get("discard", [])
    if discarded:
        filepath = output_dir / "discarded.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"total": len(discarded), "items": discarded}, f, ensure_ascii=False, indent=2)
        logger.info("Wrote discarded.json: %d items", len(discarded))


# ──────────────────────────────────────────────────────────────────────
# Reporting
# ──────────────────────────────────────────────────────────────────────

def print_report(classified: dict[str, list[dict]], category_file_map: dict[str, int] | None = None):
    """Print classification statistics and migration matrix."""
    category_file_map = category_file_map or CATEGORY_FILE_MAP

    print("\n" + "=" * 60)
    print("CLASSIFICATION REPORT")
    print("=" * 60)

    # Category counts
    print("\nCategory Distribution:")
    total = 0
    for cat in list(category_file_map.keys()) + ["discard", "unclassified"]:
        count = len(classified.get(cat, []))
        total += count
        file_id = category_file_map.get(cat, "-")
        print(f"  {cat:20s} (file_{file_id}): {count:5d}")
    print(f"  {'TOTAL':20s}        : {total:5d}")

    # Rule distribution
    print("\nClassification Reasons:")
    reason_counts: Counter = Counter()
    for cat, items in classified.items():
        for item in items:
            reason_counts[item.get("classification_reason", "unknown")] += 1
    for reason, count in reason_counts.most_common():
        print(f"  {reason:40s}: {count:5d}")

    # Confidence distribution
    print("\nConfidence Distribution:")
    all_confidences = []
    for cat, items in classified.items():
        for item in items:
            conf = item.get("confidence")
            if conf is not None:
                all_confidences.append(conf)
    if all_confidences:
        buckets = {"high (>=0.8)": 0, "medium (0.5-0.8)": 0, "low (<0.5)": 0}
        for c in all_confidences:
            if c >= 0.8:
                buckets["high (>=0.8)"] += 1
            elif c >= 0.5:
                buckets["medium (0.5-0.8)"] += 1
            else:
                buckets["low (<0.5)"] += 1
        avg = sum(all_confidences) / len(all_confidences)
        for label, count in buckets.items():
            print(f"  {label:25s}: {count:5d} ({100*count/len(all_confidences):.1f}%)")
        print(f"  {'avg confidence':25s}: {avg:.3f}")

    # Migration matrix
    print("\nMigration Matrix (original_file_id -> new category):")
    matrix: dict[int, Counter] = defaultdict(Counter)
    for cat, items in classified.items():
        for item in items:
            orig = item.get("original_file_id", "?")
            matrix[orig][cat] += 1

    cats = list(category_file_map.keys()) + ["discard", "unclassified"]
    header = f"  {'orig':>6s} | " + " | ".join(f"{c[:8]:>8s}" for c in cats)
    print(header)
    print("  " + "-" * len(header))
    for orig_fid in sorted(matrix.keys()):
        row = f"  file_{orig_fid} | "
        row += " | ".join(f"{matrix[orig_fid].get(c, 0):8d}" for c in cats)
        print(row)

    print()


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main():
    from artist_profile import load_profile

    parser = argparse.ArgumentParser(description="Reclassify video data")
    parser.add_argument("--artist", type=str, default=None,
                        help="Path to artist YAML (default: auto-detect)")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM fallback, mark unclassified")
    parser.add_argument("--dry-run", action="store_true", help="Print stats only, don't write files")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (default: reclassified/)")
    parser.add_argument("--apply", action="store_true",
                        help="Write directly to processed/ (overwrite originals)")
    parser.add_argument("--workers", type=int, default=12,
                        help="Parallel LLM workers (default: 12)")
    args = parser.parse_args()

    # Load artist profile
    profile = load_profile(args.artist)
    artist_data = profile.model_dump()
    slug = profile.slug()
    processed_dir = BASE_DIR / "data" / slug / "processed"
    logger.info("Artist: %s (%s), data: %s", profile.artist.names.primary, slug, processed_dir)

    if args.apply:
        output_dir = processed_dir
    elif args.output_dir:
        output_dir = BASE_DIR / args.output_dir
    else:
        output_dir = BASE_DIR / "reclassified"

    # Build category map from profile
    category_file_map = profile.category_file_map()
    file_metadata = {}
    for cat in profile.categories:
        file_metadata[cat.id] = {
            "output_path": cat.output_path,
            "title": cat.label,
            "description": cat.description,
        }

    # Load reference data
    classifier = RuleClassifier(artist_data)
    scorer = ConfidenceScorer(classifier)

    # Step 1: Merge & dedup
    file_ids = profile.file_ids()
    all_items = merge_and_dedup(file_ids, processed_dir)

    # Step 2: Rule-based classification + confidence scoring
    classified: dict[str, list[dict]] = defaultdict(list)
    unclassified_items: list[tuple[int, dict]] = []

    for i, item in enumerate(all_items):
        category, reason = classifier.classify(item)
        item["category"] = category
        item["classification_reason"] = reason
        if category == "unclassified":
            unclassified_items.append((i, item))
        else:
            confidence, signals = scorer.score(item, category, reason)
            item["confidence"] = confidence
            item["confidence_signals"] = signals
            classified[category].append(item)

    rule_classified = sum(len(v) for v in classified.values())
    logger.info("Rule-based: %d classified, %d unclassified", rule_classified, len(unclassified_items))

    # Step 2.5: Filter low-view items
    classified = filter_low_views(classified, classifier.official_channels)

    # Step 3: LLM fallback (parallel) + confidence scoring
    if unclassified_items and not args.no_llm:
        llm_prompt = build_llm_prompt(profile)
        results = llm_classify_parallel(
            unclassified_items, max_workers=args.workers,
            system_prompt=llm_prompt, valid_categories=list(category_file_map.keys()),
        )
        for _, item, cat, reason in results:
            item["category"] = cat
            item["classification_reason"] = reason
            confidence, signals = scorer.score(item, cat, reason)
            item["confidence"] = confidence
            item["confidence_signals"] = signals
            classified[cat].append(item)
        logger.info("LLM fallback complete")
    elif unclassified_items and args.no_llm:
        for _, item in unclassified_items:
            confidence, signals = scorer.score(item, "unclassified", "no_rule_match")
            item["confidence"] = confidence
            item["confidence_signals"] = signals
            classified["unclassified"].append(item)

    # Report
    print_report(classified, category_file_map)

    # Step 4: Write output
    if not args.dry_run:
        write_output(classified, output_dir, category_file_map, file_metadata)
        logger.info("Done! Output written to %s", output_dir)
    else:
        logger.info("Dry run — no files written")


if __name__ == "__main__":
    main()
