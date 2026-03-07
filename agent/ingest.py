"""
ingest.py — Phase 1: Execute all search queries and collect into a flat data lake.

All results are stored in data/lake.json with no category assignment.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from agent.search_plan import SEARCH_PLAN
from agent.tools import YouTubeSearchTool, GoogleSearchTool, BilibiliSearchTool
from agent.utils import extract_youtube_id, extract_bilibili_bvid, parse_duration_to_seconds

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Bilibili must be serialized to avoid anti-bot detection
_bilibili_lock = threading.Lock()


def _init_tools() -> dict:
    """Initialize search tools from environment variables."""
    from dotenv import load_dotenv
    # Try agent/.env first, then collector/.env
    agent_env = os.path.join(os.path.dirname(__file__), ".env")
    collector_env = os.path.join(os.path.dirname(__file__), "..", "collector", ".env")
    load_dotenv(agent_env if os.path.exists(agent_env) else collector_env)

    yt_keys = []
    for suffix in ["", "_2", "_3"]:
        key = os.environ.get(f"YOUTUBE_API_KEY{suffix}")
        if key:
            yt_keys.append(key)

    serper_key = os.environ.get("SERPER_API_KEY", "")

    tools = {}
    if yt_keys:
        tools["youtube"] = YouTubeSearchTool(yt_keys)
    if serper_key:
        tools["google"] = GoogleSearchTool(serper_key)
    tools["bilibili"] = BilibiliSearchTool()

    logger.info("Initialized tools: %s", list(tools.keys()))
    return tools


def _enrich_item(item: dict, tool_name: str, query: str) -> dict:
    """Add source, video_id, duration_seconds, search_query to a raw result."""
    item["source"] = tool_name
    item["search_query"] = query

    if tool_name == "youtube":
        vid = extract_youtube_id(item.get("url", ""))
        if vid:
            item["video_id"] = vid
    elif tool_name == "bilibili":
        bvid = item.get("bvid") or extract_bilibili_bvid(item.get("url", ""))
        if bvid:
            item["video_id"] = bvid
            item["bvid"] = bvid

    dur = item.get("duration", "")
    item["duration_seconds"] = parse_duration_to_seconds(dur)

    return item


def _execute_search(tools: dict, search: dict) -> list[dict]:
    """Execute a single search query and return enriched results."""
    tool_name = search["tool"]
    query = search["query"]
    tool = tools.get(tool_name)
    if not tool:
        logger.warning("Tool '%s' not available, skipping: %s", tool_name, query)
        return []

    try:
        if tool_name == "bilibili":
            with _bilibili_lock:
                page = search.get("page", 1)
                results = tool.search(query, page=page)
        elif tool_name == "youtube":
            results = tool.search(query)
        elif tool_name == "google":
            results = tool.search(query)
        else:
            return []
    except Exception as e:
        logger.error("Search failed [%s] '%s': %s", tool_name, query, e)
        return []

    return [_enrich_item(r, tool_name, query) for r in results]


def _collect_all_searches() -> list[dict]:
    """Flatten all searches from SEARCH_PLAN (ignore file_id)."""
    all_searches = []
    for plan in SEARCH_PLAN:
        for search in plan.get("searches", []):
            all_searches.append(search)
    return all_searches


def run_ingest(max_workers: int = 4) -> str:
    """Execute Phase 1: run all searches and save to data/lake.json.

    Returns path to the output file.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    tools = _init_tools()
    all_searches = _collect_all_searches()

    logger.info("Phase 1 (ingest): %d queries to execute", len(all_searches))

    lake: list[dict] = []
    completed = 0
    total = len(all_searches)

    # Separate bilibili searches (must be serialized) from others
    bilibili_searches = [s for s in all_searches if s["tool"] == "bilibili"]
    other_searches = [s for s in all_searches if s["tool"] != "bilibili"]

    # Execute non-bilibili searches with thread pool
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_execute_search, tools, s): s
            for s in other_searches
        }
        for future in as_completed(futures):
            search = futures[future]
            completed += 1
            try:
                results = future.result()
                lake.extend(results)
                if completed % 20 == 0:
                    logger.info("Progress: %d/%d queries (%d results so far)",
                                completed, total, len(lake))
            except Exception as e:
                logger.error("Query failed [%s] '%s': %s",
                             search["tool"], search["query"], e)

    # Execute bilibili searches serially
    for search in bilibili_searches:
        completed += 1
        results = _execute_search(tools, search)
        lake.extend(results)
        if completed % 10 == 0:
            logger.info("Progress: %d/%d queries (%d results so far)",
                        completed, total, len(lake))

    # Save lake
    output_path = os.path.join(DATA_DIR, "lake.json")
    output = {
        "phase": "ingest",
        "created_at": datetime.now().isoformat(),
        "total_queries": total,
        "total_results": len(lake),
        "results": lake,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info("Phase 1 complete: %d results from %d queries -> %s",
                len(lake), total, output_path)
    return output_path
