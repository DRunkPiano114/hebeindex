# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HebeIndex is a two-part project for collecting and displaying video content about Taiwanese singer Hebe Tien (田馥甄). It has a Python AI collector and an Astro/React web frontend.

## Monorepo Structure

- **`collector/`** — Python AI agent that searches YouTube/Bilibili/Google, verifies URLs, and outputs structured JSON
- **`web/`** — Astro 5 + React 19 static site that reads collector output and displays it with search/filtering

## Commands

### Collector (Python)

```bash
cd collector
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Run
uv run python pipeline.py                 # deterministic 3-phase pipeline
uv run python pipeline.py --phase 1       # search only → raw_results/
uv run python pipeline.py --phase 2       # dedup + verify → processed/
uv run python pipeline.py --phase 3       # format → output/
uv run python agent.py                    # LLM-orchestrated mode
uv run python agent.py --resume           # resume from checkpoint

# Reclassify existing data (by content, not search query origin)
uv run python reclassify.py --apply       # rules + LLM, write to processed/
uv run python reclassify.py --dry-run     # stats only, no file writes
uv run python reclassify.py               # rules + LLM, write to reclassified/
uv run python reclassify.py --no-llm      # rules only, skip LLM fallback
uv run python reclassify.py --workers 8   # custom parallel LLM workers (default: 12)

# Tests
pytest tests/
pytest tests/test_tools.py
pytest tests/test_agent.py
```

### Web (Astro + React)

```bash
cd web
pnpm install
pnpm dev          # dev server
pnpm run build    # production build → web/dist/
pnpm run preview  # preview production build
```

## Architecture

### Collector

Two execution modes share the same tool layer (`tools.py`):

- **Pipeline mode** (`pipeline.py`) — Deterministic 3-phase: search → dedup/verify → format. Phase 1 uses 4 worker threads. Bilibili calls serialized via global lock.
- **Agent mode** (`agent.py`) — LLM orchestrates tool calls in a loop (max 250 iterations) via LiteLLM Router with model fallback (Gemini → Claude → OpenAI, all through OpenRouter).

Key modules:
- `tools.py` — YouTubeSearchTool, GoogleSearchTool, BilibiliSearchTool, URLVerifier, DuplicateTracker, FileWriter
- `search_plan.py` — Declarative search config: 8 file categories, 170+ queries
- `config.py` — Rate limits, model names, output paths, context window thresholds
- `prompts.py` — System prompt with tool descriptions and Hebe's discography context
- `formatter.py` — LLM markdown generation with template fallback

Data flow: `raw_results/` → `processed/` → `output/`

### Web

The frontend reads `collector/processed/file_{id}.json` at build time via `src/data/loader.ts`. Each category page (MV, concerts, shows, songs) renders a `ContentTable` React component with:
- Fuzzy search via Fuse.js
- Platform filtering (YouTube/Bilibili)
- Virtualized list via TanStack Virtual

Astro config uses `@astrojs/react` integration and `@tailwindcss/vite` plugin.

## Environment Variables

Collector requires API keys in `collector/.env` (see `collector/.env.example`):
- `OPENROUTER_API_KEY` — LLM calls
- `YOUTUBE_API_KEY` — YouTube Data API v3 (supports multiple: `_2`, `_3`)
- `SERPER_API_KEY` — Google search

## Package Managers

- **Python**: Use `uv`, not pip
- **JavaScript**: Use `pnpm`, not npm/yarn
