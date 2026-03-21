# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HebeIndex is a two-part project for collecting and displaying video content about music artists. It has a Python collector pipeline and an Astro/React web frontend. The collector is multi-artist: swap the `artist.yaml` to collect for a different artist.

## Monorepo Structure

- **`collector/`** — Python pipeline that searches YouTube/Bilibili/Google, verifies URLs, classifies videos, and outputs structured JSON
- **`web/`** — Astro 5 + React 19 static site that reads collector output and displays it with search/filtering

## Commands

### Collector (Python)

```bash
cd collector
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Run pipeline (default: auto-detect artist from artists/)
uv run python pipeline.py                                    # all phases
uv run python pipeline.py --artist artists/hebe.yaml         # specify artist
uv run python pipeline.py --phase 1                          # search only
uv run python pipeline.py --phase 2                          # dedup + verify
uv run python pipeline.py --phase 3                          # format
uv run python pipeline.py --no-llm                           # template fallback

# Reclassify existing data (by content, not search query origin)
uv run python reclassify.py --artist artists/hebe.yaml --apply    # write to processed/
uv run python reclassify.py --dry-run                              # stats only
uv run python reclassify.py --no-llm                               # rules only
uv run python reclassify.py --workers 4                            # parallel LLM workers

# Generate new artist YAML
uv run python create_artist.py "周杰伦" "Jay Chou"

# Tests
pytest tests/
pytest tests/test_tools.py
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

Single execution mode: **Pipeline** (`pipeline.py`) — deterministic 3-phase (search → dedup/verify → format) with `--artist` parameter. Search queries are generated from `artist.yaml` via `query_generator.py`. Data is stored per-artist in `data/{slug}/`.

Key modules:
- `artist_profile.py` — Pydantic data models, loads/validates artist YAML
- `query_generator.py` — Data-driven search query generation from artist profile
- `claude_llm.py` — Thin wrapper around `claude -p` CLI for all LLM calls
- `reclassify.py` — 7-rule waterfall classifier + LLM fallback
- `tools.py` — YouTubeSearchTool, GoogleSearchTool, BilibiliSearchTool, URLVerifier, DuplicateTracker, FileWriter
- `formatter.py` — LLM markdown generation with template fallback
- `config.py` — Rate limits, verification settings

Data flow: `data/{slug}/raw_results/` → `data/{slug}/processed/` → `data/{slug}/output/`

### Web

The frontend reads `collector/data/{slug}/processed/file_{id}.json` at build time via `src/data/loader.ts`. Each category page renders a `ContentTable` React component with:
- Fuzzy search via Fuse.js
- Platform filtering (YouTube/Bilibili)
- Virtualized list via TanStack Virtual

Astro config uses `@astrojs/react` integration and `@tailwindcss/vite` plugin.

## Environment Variables

Collector requires API keys in `collector/.env`:
- `YOUTUBE_API_KEY` — YouTube Data API v3 (supports multiple: `_2`, `_3`)
- `SERPER_API_KEY` — Google search

LLM calls use `claude` CLI (must be installed and authenticated). No API keys needed for LLM.

## Package Managers

- **Python**: Use `uv`, not pip
- **JavaScript**: Use `pnpm`, not npm/yarn
