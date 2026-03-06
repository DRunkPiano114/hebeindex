"""
pipeline.py — 3-phase pipeline for content collection.

Phase 1: Execute all predefined searches (deterministic, no LLM), save raw JSON
Phase 2: Deduplicate + verify URLs (deterministic), save processed JSON
Phase 3: LLM organizes + formats processed JSON into Markdown (per-file, ~3-5K
         tokens each — no context overload). Falls back to template on failure.

Usage:
    uv run python pipeline.py               # run all phases (LLM formatting)
    uv run python pipeline.py --phase 1     # search only
    uv run python pipeline.py --phase 2     # dedup + verify only
    uv run python pipeline.py --phase 3     # LLM format + write only
    uv run python pipeline.py --no-llm      # use template fallback, skip LLM
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

from config import OUTPUT_DIR, OUTPUT_SUBDIRS, BILIBILI_RATE_LIMIT
from agent import build_router
from search_plan import SEARCH_PLAN
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
RAW_DIR = BASE_DIR / "raw_results"
PROCESSED_DIR = BASE_DIR / "processed"


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
) -> None:
    """Process all searches for a single file with its own tool instances."""
    fid = file_spec["file_id"]
    searches = file_spec["searches"]
    out_path = RAW_DIR / f"file_{fid}.json"

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


def phase1_search() -> None:
    """Execute every search in SEARCH_PLAN and persist raw results as JSON.

    Files are processed in parallel (max 4 workers). Each worker owns its own
    tool instances to avoid shared-state race conditions. Bilibili calls are
    serialized across threads via _bilibili_global_rate_limit().
    """
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

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    tasks = [s for s in SEARCH_PLAN if s["searches"]]
    skipped = [s for s in SEARCH_PLAN if not s["searches"]]
    for spec in skipped:
        logger.info(
            "File %d (%s): no searches, skipping phase 1",
            spec["file_id"], spec["output_path"],
        )

    logger.info("Phase 1: processing %d files in parallel (max_workers=%d)", len(tasks), len(tasks))

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {
            executor.submit(_phase1_file_worker, spec, youtube_keys, serper_key): spec
            for spec in tasks
        }
        for future in as_completed(futures):
            spec = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.error("File %d phase1 failed: %s", spec["file_id"], exc)

    logger.info("Phase 1 complete — all raw results saved to %s", RAW_DIR)


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

def _phase2_file_worker(file_spec: dict, verifier: URLVerifier) -> None:
    """Deduplicate and verify a single file. Fully independent of other files."""
    fid = file_spec["file_id"]
    raw_path = RAW_DIR / f"file_{fid}.json"
    proc_path = PROCESSED_DIR / f"file_{fid}.json"

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


def phase2_process() -> None:
    """Deduplicate results and verify non-YouTube URLs.

    All files are processed in parallel — each file's dedup and HTTP verification
    is fully independent. URLVerifier is stateless (new httpx.Client per check)
    and safe to share across threads.
    """
    load_dotenv()
    verifier = URLVerifier()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    tasks = [s for s in SEARCH_PLAN if s["searches"]]
    logger.info("Phase 2: processing %d files in parallel (max_workers=%d)", len(tasks), len(tasks))

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {
            executor.submit(_phase2_file_worker, spec, verifier): spec
            for spec in tasks
        }
        for future in as_completed(futures):
            spec = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.error("File %d phase2 failed: %s", spec["file_id"], exc)

    logger.info("Phase 2 complete — processed results saved to %s", PROCESSED_DIR)


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

def _format_one(file_spec: dict, use_llm: bool, router) -> tuple[str, int]:
    """Format a single file and write it to disk. Returns (output_path, result_count)."""
    fid = file_spec["file_id"]
    output_path = os.path.join(OUTPUT_DIR, file_spec["output_path"])

    proc_path = PROCESSED_DIR / f"file_{fid}.json"
    if not proc_path.exists():
        logger.warning("File %d: no processed data, run phases 1-2 first", fid)
        return output_path, 0

    proc_data = json.loads(proc_path.read_text("utf-8"))

    if use_llm:
        md = format_file_with_llm(proc_data, router)
    else:
        md = format_file_template(proc_data)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)

    logger.info("Written: %s (%d chars, %d results)", output_path, len(md), proc_data["total_results"])
    return output_path, proc_data["total_results"]


def phase3_format(use_llm: bool = True) -> None:
    """Render processed JSON into Markdown files and write to output/.

    When use_llm=True, each file gets an independent LLM call (~3-5K tokens)
    for intelligent grouping and context.  Falls back to template on failure.
    When use_llm=False, uses deterministic template rendering only.
    Files 2-8 are processed in parallel via ThreadPoolExecutor.
    """
    load_dotenv()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for sub in OUTPUT_SUBDIRS:
        os.makedirs(os.path.join(OUTPUT_DIR, sub), exist_ok=True)

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    if use_llm and not openrouter_key:
        logger.warning("No OPENROUTER_API_KEY set, falling back to template mode")
        use_llm = False

    router = build_router(openrouter_key) if use_llm else None

    readme_spec = next((s for s in SEARCH_PLAN if s["file_id"] == 1), None)
    if readme_spec:
        _write_readme(os.path.join(OUTPUT_DIR, readme_spec["output_path"]))

    tasks = [s for s in SEARCH_PLAN if s["file_id"] != 1]
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {
            executor.submit(_format_one, s, use_llm, router): s
            for s in tasks
        }
        for future in as_completed(futures):
            spec = futures[future]
            try:
                future.result()
            except Exception as exc:
                logger.error("File %d failed: %s", spec["file_id"], exc)

    _update_readme_index()
    logger.info("Phase 3 complete — output files written to %s", OUTPUT_DIR)


def _write_readme(path: str) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    content = f"""# 田馥甄（Hebe）内容资料库

> 本资料库系统性收录田馥甄（Hebe Tien）相关视频、音频及文字内容。
> 所有链接均来自 YouTube Data API v3、Bilibili 搜索 API、Google 搜索（Serper.dev）的真实搜索结果。
> 最后更新：{today}

---

## 田馥甄基本信息

| 项目 | 内容 |
|------|------|
| 本名 | 田馥甄 |
| 英文名 | Hebe Tien |
| 出生日期 | 1983年3月30日 |
| 出道 | 2001年（S.H.E 成员） |
| 个人出道 | 2010年9月3日 |

### 个人专辑

| 专辑 | 年份 |
|------|------|
| To Hebe | 2010 |
| My Love | 2011 |
| 渺小 | 2013 |
| 日常 | 2016 |
| 无人知晓 | 2020 |

### 重要演唱会

- **如果世界巡迴演唱会** (2014–2017，38场)
- **一一巡迴演唱会** (2020–2023，11场)

### 主要奖项

- 第32届金曲奖最佳华语女歌手（2021）

---

## 官方平台

| 平台 | 链接 |
|------|------|
| YouTube | [HIM International Music](https://www.youtube.com/@HIM_International) |
| Bilibili | 搜索 "Hebe田馥甄官方" |
| Facebook | [田馥甄 Hebe](https://www.facebook.com/HebeTien) |
| Instagram | [@haborstory](https://www.instagram.com/haborstory/) |

---

## 文件索引

| 文件 | 路径 | 说明 |
|------|------|------|
| 个人MV | [MV/个人MV.md](MV/个人MV.md) | 个人专辑全部 MV |
| S.H.E MV | [MV/SHE_MV.md](MV/SHE_MV.md) | S.H.E 时期 MV |
| 演唱会 | [演唱会/演唱会.md](演唱会/演唱会.md) | 个人 + S.H.E 演唱会 |
| 综艺节目 | [节目与访谈/综艺节目.md](节目与访谈/综艺节目.md) | 综艺出演 |
| 采访访谈 | [节目与访谈/采访访谈.md](节目与访谈/采访访谈.md) | 专访与访谈 |
| 影视单曲 | [歌曲与合作/影视单曲.md](歌曲与合作/影视单曲.md) | OST 与独立单曲 |
| 合唱合作 | [歌曲与合作/合唱合作.md](歌曲与合作/合唱合作.md) | 合唱与跨艺人合作 |
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Written README: %s", path)


def _update_readme_index() -> None:
    """Rewrite README with result counts from processed data."""
    readme_path = os.path.join(OUTPUT_DIR, "README.md")
    if not os.path.exists(readme_path):
        return

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove any previous stats section before rewriting
    marker = "\n---\n\n## 收录统计\n"
    idx = content.find(marker)
    if idx != -1:
        content = content[:idx]

    counts: list[str] = []
    for file_spec in SEARCH_PLAN:
        fid = file_spec["file_id"]
        if fid == 1:
            continue
        proc_path = PROCESSED_DIR / f"file_{fid}.json"
        if proc_path.exists():
            data = json.loads(proc_path.read_text("utf-8"))
            counts.append(f"- **{file_spec['title']}**: {data['total_results']} 条结果")
        else:
            counts.append(f"- **{file_spec['title']}**: 未生成")

    content += "\n---\n\n## 收录统计\n\n" + "\n".join(counts) + "\n"

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("README index updated with result counts")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="3-phase content collection pipeline"
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
    args = parser.parse_args()

    start = time.time()

    if args.phase is None or args.phase == 1:
        logger.info("=" * 60)
        logger.info("PHASE 1: Deterministic Search")
        logger.info("=" * 60)
        phase1_search()

    if args.phase is None or args.phase == 2:
        logger.info("=" * 60)
        logger.info("PHASE 2: Dedup + Verify")
        logger.info("=" * 60)
        phase2_process()

    if args.phase is None or args.phase == 3:
        logger.info("=" * 60)
        logger.info("PHASE 3: Format + Write (%s)", "template" if args.no_llm else "LLM")
        logger.info("=" * 60)
        phase3_format(use_llm=not args.no_llm)

    logger.info("=" * 60)
    logger.info("Pipeline finished in %.1f seconds", time.time() - start)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
