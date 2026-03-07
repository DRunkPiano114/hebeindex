"""
models.py — Shared types and constants for the V2 agent pipeline.
"""

from __future__ import annotations

from typing import Literal, TypedDict

CategoryName = Literal[
    "personalMV", "singles", "concerts", "variety",
    "interviews", "sheMV", "collabs", "exclude",
]

CATEGORY_FILE_MAP: dict[str, int] = {
    "personalMV": 2,
    "singles": 3,
    "concerts": 4,
    "variety": 5,
    "interviews": 6,
    "sheMV": 7,
    "collabs": 8,
}

FILE_CATEGORY_MAP: dict[int, str] = {v: k for k, v in CATEGORY_FILE_MAP.items()}


class RawItem(TypedDict, total=False):
    title: str
    url: str
    source: str                # "youtube" | "bilibili" | "google"
    published_at: str
    view_count: int
    play_count: int
    channel: str
    author: str
    duration: str
    duration_seconds: int
    verified: bool | None
    verify_status: int
    search_query: str
    bvid: str
    description: str
    video_id: str              # YouTube video ID or Bilibili BVID
    aliases: list[str]         # URLs merged into this record
    category: str              # CategoryName once classified
    classify_method: str       # "rule" | "llm"
    classify_rule: str         # Which rule matched
    snippet: str               # Google search snippet
