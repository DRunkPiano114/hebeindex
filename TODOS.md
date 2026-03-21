# TODOs

Implementation order: TODO 2 → TODO 3 → TODO 1 (generator depends on scoring + review mode).

## Confidence Scoring + Review Mode

**Two sub-components:**

### A) Additive confidence scoring in `reclassify.py`

Extend the 8-rule waterfall classifier to return a confidence score (0.0–1.0) alongside category. Signals:
- Official channel match: +0.3
- Exact track name in title: +0.2
- Category keyword match (MV/演唱會/etc.): +0.2
- Multiple rule signals agree: +0.2
- High view count (>100K): +0.1

Threshold for review flagging: 0.5 (configurable). **Critical:** items scoring 0.0 must fall through to LLM fallback, not be auto-rejected — a zero score means no signals fired, not that the item is bad.

### B) Separate `collector/review.py` for terminal UI

Interactive approve/reject/skip for flagged items. Reads flagged items from reclassify output, writes decisions back to processed/. Supports bulk approve/reject. See design doc for UX mockup.

**Why:** Collector sometimes lets inappropriate data through. Confidence scoring + review mode catches bad data before it hits the site.
**Depends on:** Nothing — implement first.
**Effort:** ~400 lines across reclassify.py + new review.py.

## Channel-Crawl + Coverage Gap Detection

Rewrite `search_channel_videos()` in `tools.py` to use YouTube **PlaylistItems API** (1 quota unit/call, paginated) instead of current Search API (100 units/call, 50 results max). This is a 100x quota savings and required for comprehensive channel crawling.

Sub-tasks:
1. **PlaylistItems rewrite:** Use `channels.list` to get uploads playlist ID, then `playlistItems.list` with pagination. Auto-resolve channel IDs from channel names via YouTube API (current YAMLs have channel names, not IDs).
2. **Coverage checker:** Cross-reference YAML discography (via `all_track_names()`) against found videos using fuzzy matching (`thefuzz`, already in requirements.txt). Report gaps: "album X has 12 tracks but only 8 MVs found."
3. **Pipeline integration:** Wire channel crawl into pipeline phase 1 as an additional data source alongside search queries.

**Why:** Search-only collection misses videos that aren't titled conventionally. Channel crawling is the most reliable way to get complete coverage.
**Depends on:** TODO 1 (Confidence Scoring) for scoring integration.
**Effort:** ~300 lines. Rewrite existing method + new coverage.py module.

## Generator CLI

Top-level `generate.py` at repo root. Orchestrates the full flow:

```
python generate.py "周杰伦" "Jay Chou"
  → Step 1: Preflight checks (claude CLI, pnpm, .env API keys)
  → Step 2: Create artist YAML (calls create_artist.py, or skip if YAML exists)
  → Step 3: Run pipeline phases 1-2 (skip if data/{slug}/raw_results/ already populated)
  → Step 4: Run reclassify with confidence scoring
  → Step 5: Review mode — show flagged items (skip if none flagged)
  → Step 6: Run pipeline phase 3 (format)
  → Step 7: Build site (pnpm run build in web/)
  → Step 8: Summary — "Added Jay Chou: 487 videos across 7 categories"
```

**Lightweight checkpoint:** Check if each phase's output directory exists and has files before running it. Skip completed phases. Uses existing data dir structure as implicit state — no separate state file needed.

**Preflight checks:** Verify claude CLI is installed and authenticated, pnpm is available, .env has required API keys. Fail fast before starting a 30-45 min pipeline run.

**Why:** Core value prop from the design doc. Without it, adding an artist is 3+ manual steps.
**Depends on:** Confidence Scoring + Review Mode (for step 5). Channel-Crawl (for comprehensive search in step 3).
**Effort:** ~250 lines Python orchestration.

## Test Coverage

Cross-cutting requirement — implement tests alongside each TODO above.

- **Confidence scoring:** Unit tests for each signal (official channel boost, track match, keyword match, multi-signal, view count). Integration test for full scoring pipeline. Edge case: item with zero signals → verify LLM fallback, not auto-reject.
- **Generator CLI:** Integration test with mocked subprocess calls. Test checkpoint logic (skip completed phases). Test preflight check failures.
- **Channel crawl:** Mocked YouTube PlaylistItems API responses. Test pagination. Test fuzzy coverage matching (exact match, partial match, no match, CJK variations).
- **Review mode:** Manual testing for v1 (interactive terminal UI is hard to auto-test).

**Files:** Extend `test_tools.py` for channel crawl. New `test_reclassify.py` for scoring. New `test_generate.py` for orchestration.
**Effort:** ~150 lines total. (human: ~1 day / CC: ~15min)
