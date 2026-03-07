# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package Manager

Always use **pnpm** instead of npm or yarn for all JavaScript/TypeScript work in this project.

## Project Overview

This is a Python-based AI agent that collects, verifies, and organizes content about Taiwanese singer Hebe Tien (田馥甄) from YouTube, Bilibili, and Google Search, outputting verified markdown files.

## Commands

**Setup:**
```bash
uv venv && uv pip install -r requirements.txt
# or: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

**Run agent (interactive LLM-orchestrated mode):**
```bash
uv run python agent.py           # fresh run
uv run python agent.py --resume  # resume from .checkpoint.json
```

**Run pipeline (deterministic 3-phase mode):**
```bash
uv run python pipeline.py                 # all phases
uv run python pipeline.py --phase 1       # search only → raw_results/
uv run python pipeline.py --phase 2       # dedup + verify → processed/
uv run python pipeline.py --phase 3       # LLM format → output/
uv run python pipeline.py --no-llm        # phase 3 with template fallback
```

**Reclassify existing data (by content, not search query origin):**
```bash
uv run python reclassify.py --apply       # rules + LLM, write to processed/
uv run python reclassify.py --dry-run     # stats only, no file writes
uv run python reclassify.py               # rules + LLM, write to reclassified/
uv run python reclassify.py --no-llm      # rules only, skip LLM fallback
uv run python reclassify.py --workers 8   # custom parallel LLM workers (default: 12)
```

**Tests:**
```bash
pytest tests/
pytest tests/test_tools.py   # tool unit tests
pytest tests/test_agent.py   # agent loop tests
```

## Architecture

Two execution modes with shared tool layer:

### Agent Mode (`agent.py`)
LLM (via LiteLLM Router) orchestrates tool calls in a loop (max 250 iterations). Saves `.checkpoint.json` after each turn for resume. Trims conversation history (keeps first msg + last 60) when approaching context limits. Model fallback order: Gemini → Claude Sonnet → OpenAI (via OpenRouter).

### Pipeline Mode (`pipeline.py`)
Deterministic 3-phase execution. Phase 1 uses 4 worker threads (one per file category) with `search_plan.py` defining all 170+ queries declaratively. Bilibili calls serialized via global lock across threads. Phases write to `raw_results/` → `processed/` → `output/`.

### Tools (`tools.py`)
- **YouTubeSearchTool**: YouTube Data API v3, auto-rotates API keys on quota exhaustion, results are `verified=True`
- **GoogleSearchTool**: Serper.dev gateway, results `verified=None`
- **BilibiliSearchTool**: Public API, auto-manages cookies (buvid3/buvid4) for anti-bot bypass, handles 412 with retry
- **URLVerifier**: HEAD/GET with 405 fallback; YouTube URLs fast-tracked as valid
- **DuplicateTracker**: Source-aware dedup (YouTube by video ID, Bilibili by BVID, others by URL)
- **FileWriter**: Writes to `output/` with pre-created subdirectories

### Key Files
- `config.py` — rate limits, output paths, model names, context window thresholds
- `search_plan.py` — declarative search config (8 file categories, 170+ queries)
- `prompts.py` — system prompt (tool descriptions, Hebe's discography context) + 186-line initial task
- `formatter.py` — LLM markdown generation with template fallback; instructed never to hallucinate links

## Required Environment Variables (`.env`)
```
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=...          # for LiteLLM multi-model routing
YOUTUBE_API_KEY=AIza...         # supports multiple: YOUTUBE_API_KEY_2, _3
SERPER_API_KEY=...
```

## Data Flow
```
raw_results/file_{id}.json   ← Phase 1 raw API responses
processed/file_{id}.json     ← Phase 2 deduplicated + verified
output/{category}/*.md       ← Phase 3 formatted markdown tables
agent_run.log / pipeline_run.log  ← execution logs
.checkpoint.json             ← auto-saved resume state (deleted on success)
```
