"""
utils.py — Shared utilities for duration parsing, title normalization, ID extraction.
"""

from __future__ import annotations

import re
import unicodedata


def parse_duration_to_seconds(s: str | None) -> int:
    """Convert duration string to seconds.

    Handles:
      - "M:SS" e.g. "4:35" -> 275
      - "MM:SS" e.g. "141:40" -> 8500
      - "H:MM:SS" e.g. "1:30:00" -> 5400
      - Empty/None -> 0
    """
    if not s:
        return 0
    s = s.strip()
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
        if len(parts) == 1:
            return int(parts[0])
    except (ValueError, IndexError):
        pass
    return 0


def normalize_title(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for fuzzy comparison."""
    s = s.lower()
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_youtube_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    if not url:
        return None
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def extract_bilibili_bvid(url: str) -> str | None:
    """Extract Bilibili BVID from URL."""
    if not url:
        return None
    m = re.search(r"(BV[A-Za-z0-9]{10})", url)
    return m.group(1) if m else None


def title_contains_any(title: str, keywords: list[str]) -> bool:
    """Check if normalized title contains any of the keywords (case-insensitive)."""
    t = normalize_title(title)
    return any(normalize_title(k) in t for k in keywords)


def title_contains_all(title: str, keywords: list[str]) -> bool:
    """Check if normalized title contains all of the keywords (case-insensitive)."""
    t = normalize_title(title)
    return all(normalize_title(k) in t for k in keywords)
