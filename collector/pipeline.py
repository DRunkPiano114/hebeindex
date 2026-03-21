"""
pipeline.py — 3-phase pipeline for content collection.

Phase 1: Execute all predefined searches (deterministic, no LLM), save raw JSON
Phase 2: Deduplicate + verify URLs (deterministic), save processed JSON
Phase 3: LLM organizes + formats processed JSON into Markdown (per-file, ~3-5K
         tokens each — no context overload). Falls back to template on failure.

Usage:
    uv run python pipeline.py                               # run all phases
    uv run python pipeline.py --artist artists/hebe.yaml    # specify artist
    uv run python pipeline.py --phase 1                     # search only
    uv run python pipeline.py --phase 2                     # dedup + verify only
    uv run python pipeline.py --phase 3                     # LLM format + write only
    uv run python pipeline.py --no-llm                      # use template fallback
"""

from __future__ import annotations

import os
import sys
import json
import time
import logging
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

from config import BILIBILI_RATE_LIMIT
from artist_profile import ArtistProfile, load_profile
from query_generator import build_search_plan
from tools import (
    YouTubeSearchTool,
    GoogleSearchTool,
    BilibiliSearchTool,
    URLVerifier,
)
from formatter import format_file_with_llm, format_file_template

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            Path(__file__).parent / "pipeline_run.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("pipeline")

BASE_DIR = Path(__file__).parent


def _data_dir(profile: ArtistProfile) -> Path:
    """Per-artist data directory: data/{slug}/"""
    return BASE_DIR / "data" / profile.slug()


# ---------------------------------------------------------------------------
# Bilibili global rate-limiter (shared across threads)
# ---------------------------------------------------------------------------

_BILIBILI_GLOBAL_LOCK = threading.Lock()
_BILIBILI_LAST_CALL: float = 0.0


def _bilibili_global_rate_limit() -> None:
    """Enforce BILIBILI_RATE_LIMIT globally across all threads."""
    global _BILIBILI_LAST_CALL
    with _BILIBILI_GLOBAL_LOCK:
        elapsed = time.time() - _BILIBILI_LAST_CALL
        if elapsed < BILIBILI_RATE_LIMIT:
            time.sleep(BILIBILI_RATE_LIMIT - elapsed)
        _BILIBILI_LAST_CALL = time.time()


# ---------------------------------------------------------------------------
# Phase 1 — Deterministic search
# ---------------------------------------------------------------------------

def _run_search(s: dict, tools: dict) -> list[dict]:
    """Dispatch a single search entry to the appropriate tool."""
    tool_name = s["tool"]
    if tool_name == "youtube":
        return tools["youtube"].search(query=s["query"], max_results=30)
    elif tool_name == "bilibili":
        return tools["bilibili"].search(keyword=s["query"], page=s.get("page", 1))
    elif tool_name == "google":
        return tools["google"].search(query=s["query"], num=10)
    else:
        logger.warning("Unknown tool: %s", tool_name)
        return []


def _phase1_file_worker(
    file_spec: dict,
    youtube_keys: list[str],
    serper_key: str,
    raw_dir: Path,
) -> None:
    """Process all searches for a single file with its own tool instances."""
    fid = file_spec["file_id"]
    searches = file_spec["searches"]
    out_path = raw_dir / f"file_{fid}.json"

    tools = {
        "youtube": YouTubeSearchTool(youtube_keys),
        "google": GoogleSearchTool(serper_key),
        "bilibili": BilibiliSearchTool(),
    }

    logger.info("=" * 50)
    logger.info("File %d: %s — %d searches", fid, file_spec["title"], len(searches))

    all_results: list[dict] = []
    for idx, s in enumerate(searches, 1):
        tool_name = s["tool"]
        query = s["query"]
        logger.info(
            "  [%d/%d] File %d — %s: %s",
            idx, len(searches), fid, tool_name, query,
        )

        if tool_name == "bilibili":
            _bilibili_global_rate_limit()

        try:
            results = _run_search(s, tools)
        except Exception as exc:
            logger.error("File %d search failed: %s — %s", fid, query, exc)
            results = []

        all_results.append({
            "tool": tool_name,
            "query": query,
            "page": s.get("page", 1),
            "result_count": len(results),
            "results": results,
        })
        _save_raw(out_path, file_spec, all_results)

    logger.info("File %d: collected %d search batches", fid, len(all_results))


def phase1_search(profile: ArtistProfile, search_plan: list[dict]) -> None:
    """Execute every search in search_plan and persist raw results as JSON."""
    load_dotenv()

    youtube_keys = [
        k for k in [
            os.getenv("YOUTUBE_API_KEY"),
            os.getenv("YOUTUBE_API_KEY_2"),
            os.getenv("YOUTUBE_API_KEY_3"),
            os.getenv("YOUTUBE_API_KEY_4"),
            os.getenv("YOUTUBE_API_KEY_5"),
            os.getenv("YOUTUBE_API_KEY_6"),
        ] if k
    ]
    serper_key = os.getenv("SERPER_API_KEY")

    missing = []
    if not youtube_keys:
        missing.append("YOUTUBE_API_KEY")
    if not serper_key:
        missing.append("SERPER_API_KEY")
    if missing:
        logger.error("Missing API keys: %s", ", ".join(missing))
        sys.exit(1)

    raw_dir = _data_dir(profile) / "raw_results"
    raw_dir.mkdir(parents=True, exist_ok=True)

    tasks = [s for s in search_plan if s["searches"]]
    skipped = [s for s in search_plan if not s["searches"]]
    for spec in skipped:
        logger.info(
            "File %d (%s): no searches, skipping phase 1",
            spec["file_id"], spec["output_path"],
        )

    logger.info("Phase 1: processing %d files in parallel (max_workers=%d)", len(tasks), len(tasks))

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {
            executor.submit(_phase1_file_worker, spec, youtube_keys, serper_key, raw_dir): spec
            for spec in tasks
        }
        for future in as_completed(futures):
            spec = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.error("File %d phase1 failed: %s", spec["file_id"], exc)

    logger.info("Phase 1 complete — all raw results saved to %s", raw_dir)


def _save_raw(path: Path, file_spec: dict, searches: list[dict]) -> None:
    data = {
        "file_id": file_spec["file_id"],
        "output_path": file_spec["output_path"],
        "title": file_spec["title"],
        "description": file_spec["description"],
        "collected_at": datetime.now().isoformat(),
        "searches": searches,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Phase 2 — Deduplicate + verify
# ---------------------------------------------------------------------------

def _phase2_file_worker(file_spec: dict, verifier: URLVerifier, raw_dir: Path, proc_dir: Path) -> None:
    """Deduplicate and verify a single file."""
    fid = file_spec["file_id"]
    raw_path = raw_dir / f"file_{fid}.json"
    proc_path = proc_dir / f"file_{fid}.json"

    if not raw_path.exists():
        logger.warning("File %d: no raw results found, run phase 1 first", fid)
        return

    raw = json.loads(raw_path.read_text("utf-8"))
    logger.info("=" * 50)
    logger.info("File %d: processing %d search batches", fid, len(raw["searches"]))

    flat_results = _flatten_and_dedup(raw["searches"])
    logger.info("  File %d — after dedup: %d unique results", fid, len(flat_results))

    urls_to_verify = [
        r["url"] for r in flat_results
        if r.get("source") in ("bilibili", "google")
        and r.get("url", "").startswith("http")
    ]

    verification: dict[str, dict] = {}
    if urls_to_verify:
        logger.info("  File %d — verifying %d non-YouTube URLs ...", fid, len(urls_to_verify))
        for i in range(0, len(urls_to_verify), 50):
            batch = urls_to_verify[i : i + 50]
            verification.update(verifier.verify(batch))

    verified_results = []
    for r in flat_results:
        url = r.get("url", "")
        if r.get("source") == "youtube":
            r["verified"] = True
            verified_results.append(r)
        elif url in verification:
            v = verification[url]
            r["verified"] = v["valid"]
            r["verify_status"] = v["status"]
            r["verify_note"] = v.get("note", "")
            if v["valid"] or v["status"] == 0:
                verified_results.append(r)
        else:
            r["verified"] = True
            verified_results.append(r)

    valid_count = sum(1 for r in verified_results if r.get("verified"))
    unverified_count = sum(1 for r in verified_results if not r.get("verified"))
    logger.info(
        "  File %d — final: %d results (%d verified, %d unverified/timeout kept)",
        fid, len(verified_results), valid_count, unverified_count,
    )

    proc_data = {
        "file_id": fid,
        "output_path": raw["output_path"],
        "title": raw["title"],
        "description": raw["description"],
        "processed_at": datetime.now().isoformat(),
        "total_results": len(verified_results),
        "results": verified_results,
    }
    proc_path.write_text(
        json.dumps(proc_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def phase2_process(profile: ArtistProfile, search_plan: list[dict]) -> None:
    """Deduplicate results and verify non-YouTube URLs."""
    load_dotenv()
    verifier = URLVerifier()

    data_root = _data_dir(profile)
    raw_dir = data_root / "raw_results"
    proc_dir = data_root / "processed"
    proc_dir.mkdir(parents=True, exist_ok=True)

    tasks = [s for s in search_plan if s["searches"]]
    logger.info("Phase 2: processing %d files in parallel (max_workers=%d)", len(tasks), len(tasks))

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {
            executor.submit(_phase2_file_worker, spec, verifier, raw_dir, proc_dir): spec
            for spec in tasks
        }
        for future in as_completed(futures):
            spec = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.error("File %d phase2 failed: %s", spec["file_id"], exc)

    logger.info("Phase 2 complete — processed results saved to %s", proc_dir)


def _flatten_and_dedup(searches: list[dict]) -> list[dict]:
    """Flatten all search batches into a single list, removing duplicates."""
    seen_keys: set[str] = set()
    unique: list[dict] = []

    for batch in searches:
        tool = batch["tool"]
        for r in batch["results"]:
            key = _dedup_key(r, tool)
            if key and key in seen_keys:
                continue
            if key:
                seen_keys.add(key)

            r["source"] = tool
            r["search_query"] = batch["query"]
            unique.append(r)

    return unique


def _dedup_key(result: dict, source: str) -> str | None:
    if source == "youtube":
        url = result.get("url", "")
        if "v=" in url:
            return "yt:" + url.split("v=")[-1].split("&")[0]
        return ("yt:" + url) if url else None
    if source == "bilibili":
        bvid = result.get("bvid")
        return ("bili:" + bvid) if bvid else None
    return ("url:" + result.get("url", "")) if result.get("url") else None


# ---------------------------------------------------------------------------
# Phase 3 — Format and write output
# ---------------------------------------------------------------------------

def _format_one(file_spec: dict, use_llm: bool, profile: ArtistProfile) -> tuple[str, int]:
    """Format a single file and write it to disk."""
    fid = file_spec["file_id"]
    data_root = _data_dir(profile)
    output_dir = data_root / "output"
    output_path = str(output_dir / file_spec["output_path"])

    proc_path = data_root / "processed" / f"file_{fid}.json"
    if not proc_path.exists():
        logger.warning("File %d: no processed data, run phases 1-2 first", fid)
        return output_path, 0

    proc_data = json.loads(proc_path.read_text("utf-8"))

    if use_llm:
        md = format_file_with_llm(proc_data, profile)
    else:
        md = format_file_template(proc_data)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)

    logger.info("Written: %s (%d chars, %d results)", output_path, len(md), proc_data["total_results"])
    return output_path, proc_data["total_results"]


def phase3_format(profile: ArtistProfile, search_plan: list[dict], use_llm: bool = True) -> None:
    """Render processed JSON into Markdown files and write to output/."""
    data_root = _data_dir(profile)
    output_dir = data_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create output subdirectories from category output_paths
    for cat in profile.categories:
        if cat.output_path:
            subdir = output_dir / Path(cat.output_path).parent
            subdir.mkdir(parents=True, exist_ok=True)

    # Write README
    _write_readme(str(output_dir / "README.md"), profile)

    tasks = [s for s in search_plan if s["searches"]]
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {
            executor.submit(_format_one, s, use_llm, profile): s
            for s in tasks
        }
        for future in as_completed(futures):
            spec = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.error("File %d failed: %s", spec["file_id"], exc)

    _update_readme_index(profile, search_plan)
    logger.info("Phase 3 complete — output files written to %s", output_dir)


def _write_readme(path: str, profile: ArtistProfile) -> None:
    """Write a templated README from profile data."""
    today = datetime.now().strftime("%Y-%m-%d")
    p = profile
    primary = p.artist.names.primary
    english = p.artist.names.english

    # Albums table
    album_rows = "\n".join(
        f"| {a.name} | {a.year} |" for a in p.discography.solo_albums
    )

    # Concerts section
    concerts_lines = []
    for c in p.discography.concerts:
        concerts_lines.append(f"- **{c.name}** ({c.years})")

    # Awards
    awards_lines = "\n".join(f"- {a}" for a in p.artist.awards) if p.artist.awards else "- (暂无记录)"

    # Social links
    social_rows = ""
    for platform, link in p.artist.social_links.items():
        social_rows += f"| {platform.capitalize()} | [{link}]({link}) |\n"

    # File index
    file_index_rows = ""
    for cat in p.categories:
        if cat.output_path:
            file_index_rows += f"| {cat.label} | [{cat.output_path}]({cat.output_path}) | {cat.description[:30]}... |\n"

    content = f"""# {primary}（{english}）内容资料库

> 本资料库系统性收录{primary}（{english}）相关视频、音频及文字内容。
> 所有链接均来自 YouTube Data API v3、Bilibili 搜索 API、Google 搜索（Serper.dev）的真实搜索结果。
> 最后更新：{today}

---

## 基本信息

| 项目 | 内容 |
|------|------|
| 本名 | {primary} |
| 英文名 | {english} |
{f"| 出生年份 | {p.artist.birth_year} |" if p.artist.birth_year else ""}
{f"| 风格 | {p.artist.genre} |" if p.artist.genre else ""}

### 个人专辑

| 专辑 | 年份 |
|------|------|
{album_rows}

### 重要演唱会

{chr(10).join(concerts_lines)}

### 主要奖项

{awards_lines}

---

## 官方平台

| 平台 | 链接 |
|------|------|
{social_rows}
---

## 文件索引

| 文件 | 路径 | 说明 |
|------|------|------|
{file_index_rows}"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Written README: %s", path)


def _update_readme_index(profile: ArtistProfile, search_plan: list[dict]) -> None:
    """Rewrite README with result counts from processed data."""
    data_root = _data_dir(profile)
    readme_path = data_root / "output" / "README.md"
    proc_dir = data_root / "processed"

    if not readme_path.exists():
        return

    content = readme_path.read_text("utf-8")

    # Remove any previous stats section
    marker = "\n---\n\n## 收录统计\n"
    idx = content.find(marker)
    if idx != -1:
        content = content[:idx]

    counts: list[str] = []
    for file_spec in search_plan:
        fid = file_spec["file_id"]
        proc_path = proc_dir / f"file_{fid}.json"
        if proc_path.exists():
            data = json.loads(proc_path.read_text("utf-8"))
            counts.append(f"- **{file_spec['title']}**: {data['total_results']} 条结果")
        else:
            counts.append(f"- **{file_spec['title']}**: 未生成")

    content += "\n---\n\n## 收录统计\n\n" + "\n".join(counts) + "\n"

    readme_path.write_text(content, encoding="utf-8")
    logger.info("README index updated with result counts")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="3-phase content collection pipeline"
    )
    parser.add_argument(
        "--artist",
        type=str,
        default=None,
        help="Path to artist YAML (default: auto-detect from artists/)",
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3],
        default=None,
        help="Run a specific phase (default: run all sequentially)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Phase 3: use deterministic template instead of LLM formatting",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show claude CLI internal progress on stderr",
    )
    args = parser.parse_args()

    if args.verbose:
        import claude_llm
        claude_llm.VERBOSE = True

    profile = load_profile(args.artist)
    search_plan = build_search_plan(profile)
    logger.info("Artist: %s (%s)", profile.artist.names.primary, profile.artist.names.english)
    logger.info("Categories: %d, Total queries: %d",
                len(profile.categories),
                sum(len(s["searches"]) for s in search_plan))

    start = time.time()

    if args.phase is None or args.phase == 1:
        logger.info("=" * 60)
        logger.info("PHASE 1: Deterministic Search")
        logger.info("=" * 60)
        phase1_search(profile, search_plan)

    if args.phase is None or args.phase == 2:
        logger.info("=" * 60)
        logger.info("PHASE 2: Dedup + Verify")
        logger.info("=" * 60)
        phase2_process(profile, search_plan)

    if args.phase is None or args.phase == 3:
        logger.info("=" * 60)
        logger.info("PHASE 3: Format + Write (%s)", "template" if args.no_llm else "LLM")
        logger.info("=" * 60)
        phase3_format(profile, search_plan, use_llm=not args.no_llm)

    logger.info("=" * 60)
    logger.info("Pipeline finished in %.1f seconds", time.time() - start)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
