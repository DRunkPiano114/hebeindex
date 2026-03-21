# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Package Manager

Always use **pnpm** instead of npm or yarn for all JavaScript/TypeScript work in this project.

## Project Overview

Multi-artist video content collector. Reads an `artist.yaml` profile and runs a 3-phase pipeline (search → dedup/verify → format) to collect and organize video content from YouTube, Bilibili, and Google Search. The artist YAML is the single source of truth — swap the YAML to collect for a different artist.

## Commands

**Setup:**
```bash
uv venv && uv pip install -r requirements.txt
```

**Run pipeline:**
```bash
uv run python pipeline.py                                    # all phases (default artist)
uv run python pipeline.py --artist artists/hebe.yaml         # specify artist
uv run python pipeline.py --phase 1                          # search only
uv run python pipeline.py --phase 2                          # dedup + verify
uv run python pipeline.py --phase 3                          # LLM format
uv run python pipeline.py --no-llm                           # template fallback
```

**Reclassify existing data:**
```bash
uv run python reclassify.py --artist artists/hebe.yaml --apply    # write to processed/
uv run python reclassify.py --dry-run                              # stats only
uv run python reclassify.py --no-llm                               # rules only
uv run python reclassify.py --workers 4                            # parallel LLM workers
```

**Generate new artist (full flow):**
```bash
uv run python generate.py "周杰伦" "Jay Chou"                   # create YAML + pipeline + build
uv run python generate.py "周杰伦" "Jay Chou" --skip-build      # skip web build
uv run python generate.py --artist artists/jay_chou.yaml        # existing YAML, full pipeline
uv run python generate.py --artist artists/jay_chou.yaml --phase 1  # single phase only
```

**Generate artist YAML only:**
```bash
uv run python create_artist.py "周杰伦" "Jay Chou"
```

**Review low-confidence items:**
```bash
uv run python review.py                              # review items below 0.7 confidence
uv run python review.py --threshold 0.6              # custom threshold
uv run python review.py --category concerts          # filter by category
uv run python review.py --resume                     # resume previous session
```

**Channel crawl + coverage:**
```bash
uv run python channel_crawl.py --artist artists/hebe.yaml              # crawl channels
uv run python channel_crawl.py --artist artists/hebe.yaml --coverage   # coverage report
```

**Tests:**
```bash
pytest tests/
pytest tests/test_tools.py
```

## Architecture

### Pipeline Mode (`pipeline.py`)
Deterministic 3-phase execution with `--artist` parameter. Queries are generated from `artist.yaml` via `query_generator.py`. Data is stored per-artist in `data/{slug}/`. Bilibili calls serialized via global lock.

### Key Modules
- `artist_profile.py` — Pydantic data models, loads/validates artist YAML
- `query_generator.py` — Data-driven search query generation from artist profile
- `claude_llm.py` — Thin wrapper around `claude -p` CLI for all LLM calls
- `reclassify.py` — 7-rule waterfall classifier + LLM fallback + confidence scoring
- `review.py` — Terminal UI for human review of low-confidence items
- `channel_crawl.py` — YouTube channel crawling + coverage gap detection
- `generate.py` — CLI orchestrator: create YAML → pipeline → build
- `formatter.py` — LLM markdown generation with template fallback
- `tools.py` — YouTube/Bilibili/Google search, URL verification, dedup tracking
- `config.py` — Rate limits, verification settings

### Tools (`tools.py`)
- **YouTubeSearchTool**: YouTube Data API v3, auto-rotates API keys
- **GoogleSearchTool**: Serper.dev gateway
- **BilibiliSearchTool**: Public API, auto-manages cookies for anti-bot bypass
- **URLVerifier**: HEAD/GET with 405 fallback
- **DuplicateTracker**: Source-aware dedup

## Required Environment Variables (`.env`)
```
YOUTUBE_API_KEY=AIza...         # supports multiple: YOUTUBE_API_KEY_2, _3, etc.
SERPER_API_KEY=...
```

LLM calls use `claude` CLI (must be installed and authenticated). No API keys needed for LLM.

## Data Flow
```
artists/{name}.yaml                    ← Artist profile (single source of truth)
data/{slug}/raw_results/file_{id}.json ← Phase 1 raw API responses
data/{slug}/processed/file_{id}.json   ← Phase 2 deduplicated + verified
data/{slug}/output/{category}/*.md     ← Phase 3 formatted markdown
```
