"""
agent.config — Agent-local configuration constants.
"""

import os

# Paths — note: BASE_DIR is agent/config/, so go up one level for agent/
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_AGENT_DIR = os.path.dirname(_CONFIG_DIR)

BASE_DIR = _AGENT_DIR
DATA_DIR = os.path.join(_AGENT_DIR, "data")
CONFIG_DIR = _CONFIG_DIR
PROCESSED_DIR = os.path.join(_AGENT_DIR, "..", "collector", "processed")

# Tool rate limits (seconds between calls)
YOUTUBE_RATE_LIMIT = 0.2   # YouTube API: 10,000 units/day free
GOOGLE_RATE_LIMIT  = 0.5   # Serper: 2,500 req/month free
BILIBILI_RATE_LIMIT = 1.2  # Be polite to Bilibili

# HTTP verification settings
VERIFY_TIMEOUT = 8          # seconds
VERIFY_MAX_RETRIES = 1

# YouTube search: max results per query
YOUTUBE_MAX_RESULTS = 30

# Bilibili search: results per page
BILIBILI_PAGE_SIZE = 50
