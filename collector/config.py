import os

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

LOG_MODEL_LABEL = "hebe-agent-v2"
MAX_TOKENS = 65536

# All LLM calls go through OpenRouter (openrouter.ai).
# Routing order managed by LiteLLM Router (order= param):
#   Tier 1 (primary)  : Gemini 3.1 Pro Preview
#   Tier 2            : Anthropic Claude Sonnet
#   Tier 3 (fallback) : OpenAI
OPENROUTER_MODEL_GEMINI  = "openrouter/google/gemini-3.1-flash-lite-preview"
OPENROUTER_MODEL_SONNET  = "openrouter/anthropic/claude-sonnet-4-6"
OPENROUTER_MODEL_OPENAI  = "openrouter/openai/gpt-5.2-2025-12-11"

# LiteLLM Router settings
ROUTER_ALLOWED_FAILS = 1    # cooldown a key after this many consecutive failures
ROUTER_COOLDOWN_TIME = 120  # seconds to cool down a rate-limited key
ROUTER_NUM_RETRIES   = 2    # SDK-level retries before marking a key as failed

# Safety limit on tool-use iterations (prevents infinite loops)
MAX_ITERATIONS = 250

# Output subdirectories to pre-create
OUTPUT_SUBDIRS = [
    "MV",
    "演唱会",
    "节目与访谈",
    "歌曲与合作",
]

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

# Context window monitoring
CONTEXT_WINDOW_LIMIT = 1_000_000
CONTEXT_WARNING_THRESHOLD = 0.8
