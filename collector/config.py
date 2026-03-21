import os

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

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

# Minimum view count per category (items below threshold are discarded).
# Items with view_count=0/None are kept (means API didn't return data).
# Items from official channels are always exempt.
MIN_VIEW_COUNT = {
    "default": 1000,
    "personal_mv": 500,
    "group_mv": 500,
    "ost_singles": 500,
    "collabs": 500,
    "concerts": 1000,
    "variety": 1000,
    "interviews": 500,
}
