"""
formatter.py — Markdown formatter with LLM-powered organization.

Phase 3 calls format_file_with_llm() for each file individually.
Each LLM call receives only that file's processed JSON (~3-5K tokens),
so context overload is impossible.

Falls back to a deterministic template if the LLM call fails.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-file formatting prompt
# ---------------------------------------------------------------------------

FORMAT_SYSTEM_PROMPT = """你是一个专业的华语音乐资料整理编辑。你的任务是将搜索结果 JSON 整理成格式规范的 Markdown 文件。

## 你必须遵守的规则

1. **只使用提供的 JSON 数据**，不得编造任何链接、标题、播放量或其他信息。
2. **每条结果都必须出现在输出中**，不得遗漏任何一条。
3. 根据内容类型进行智能分组（如按专辑、按节目、按年代等）。
4. 为分组和条目添加有意义的上下文说明（如"这首歌是《我的少女时代》主题曲"）。
5. 区分官方版本和非官方版本（翻唱、歌词版、live 版等）。

## 输出格式

```markdown
# 标题

> 简介说明（数据来源、收录范围、更新日期）

---

## 分组名称（如：专辑《To Hebe》/ 梦想的声音第X期）

| 内容名称 | 链接 | 平台 | 发布日期 | 播放量 | 频道/作者 | 备注 |
|---------|------|------|---------|-------|---------|------|
```

## 播放量格式
- 100万以上：`123.4万`
- 1万以上：`1.2万`
- 1万以下：直接写数字

## 验证标记
- verified=true：正常写入
- verified=false 且 verify_status=0：加 ⚠️ 标记
- verified=false 且 verify_status 为 404 等：不应出现在数据中（已被过滤）

## 田馥甄背景知识（用于分组和添加上下文）

- 个人专辑（共5张）：To Hebe(2010) / My Love(2011) / 渺小(2013) / 日常(2016) / 无人知晓(2020)
- 重要单曲：小幸运（《我的少女时代》主题曲）、爱了很久的朋友（《后来的我们》插曲）
- 演唱会：如果世界巡迴演唱会(2014–2017)、一一巡迴演唱会(2020–2023)
- 综艺：梦想的声音（2016，浙江卫视）
- S.H.E 成员：田馥甄(Hebe)、任家萱(Selina)、陈嘉桦(Ella)

只输出最终的 Markdown 内容，不要解释你的分组思路。"""


def format_file_with_llm(
    proc_data: dict,
    router,
    max_retries: int = 2,
) -> str:
    """Use LLM to organize and format one file's results into Markdown.

    Each call is independent and small (~3-5K input tokens).
    Uses the LiteLLM Router for Gemini → Sonnet → OpenAI model fallback.
    Retries with exponential backoff before falling back to template.
    """
    results = proc_data["results"]
    title = proc_data["title"]
    description = proc_data["description"]
    total = proc_data["total_results"]

    compact_results = _compact_results(results)

    user_msg = (
        f"请将以下搜索结果整理成 Markdown 文件。\n\n"
        f"文件标题：{title}\n"
        f"文件说明：{description}\n"
        f"结果总数：{total}\n"
        f"今日日期：{datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"搜索结果 JSON：\n```json\n{json.dumps(compact_results, ensure_ascii=False)}\n```"
    )

    for attempt in range(max_retries + 1):
        try:
            response = router.completion(
                model="primary",
                max_tokens=64000,
                messages=[
                    {"role": "system", "content": FORMAT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
            )

            content = response.choices[0].message.content or ""
            out_tokens = response.usage.completion_tokens

            if out_tokens == 0 or not content.strip():
                logger.warning(
                    "LLM returned empty for '%s' (attempt %d/%d)",
                    title, attempt + 1, max_retries + 1,
                )
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                continue

            md = _strip_code_fences(content)
            logger.info(
                "LLM formatted '%s': %d chars, %d input / %d output tokens",
                title, len(md),
                response.usage.prompt_tokens, out_tokens,
            )
            return md

        except Exception as exc:
            logger.error(
                "LLM format call failed for '%s' (attempt %d/%d): %s",
                title, attempt + 1, max_retries + 1, exc,
            )
            if attempt < max_retries:
                time.sleep(2 ** attempt)

    logger.warning("All LLM attempts failed for '%s', falling back to template", title)
    return format_file_template(proc_data)


def _compact_results(results: list[dict]) -> list[dict]:
    """Strip internal metadata fields to keep the LLM payload small."""
    compact = []
    for r in results:
        c: dict = {}
        for key in (
            "title", "url", "source", "published_at", "view_count",
            "play_count", "channel", "author", "duration", "description",
            "snippet", "bvid", "date", "verified", "verify_status",
        ):
            if key in r and r[key] is not None:
                c[key] = r[key]
        compact.append(c)
    return compact


def _strip_code_fences(text: str) -> str:
    """Remove wrapping ```markdown ... ``` if LLM added them."""
    text = text.strip()
    if text.startswith("```"):
        first_nl = text.index("\n") if "\n" in text else len(text)
        text = text[first_nl + 1:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


# ---------------------------------------------------------------------------
# Template fallback (no LLM needed)
# ---------------------------------------------------------------------------

def format_file_template(proc_data: dict) -> str:
    """Deterministic template renderer — used as fallback if LLM fails."""
    title = proc_data["title"]
    description = proc_data["description"]
    results = proc_data["results"]
    total = proc_data["total_results"]
    today = datetime.now().strftime("%Y-%m-%d")

    youtube_results = [r for r in results if r.get("source") == "youtube"]
    bilibili_results = [r for r in results if r.get("source") == "bilibili"]
    google_results = [r for r in results if r.get("source") == "google"]

    lines = [
        f"# {title}",
        "",
        f"> {description}",
        f"> 数据来源：YouTube Data API v3、Bilibili 搜索 API、Google 搜索（Serper.dev）",
        f"> 共收录 {total} 条结果 | 最后更新：{today}",
        "",
        "---",
        "",
    ]

    if youtube_results:
        lines.append("## YouTube 视频")
        lines.append("")
        lines.append(_render_video_table(youtube_results, "youtube"))
        lines.append("")

    if bilibili_results:
        lines.append("## Bilibili 视频")
        lines.append("")
        lines.append(_render_video_table(bilibili_results, "bilibili"))
        lines.append("")

    if google_results:
        lines.append("## 其他来源")
        lines.append("")
        lines.append(_render_google_table(google_results))
        lines.append("")

    if not results:
        lines.append("*暂无搜索结果。*")
        lines.append("")

    return "\n".join(lines)


def _render_video_table(results: list[dict], source: str) -> str:
    header = "| 内容名称 | 链接 | 平台 | 发布日期 | 播放量 | 频道/作者 | 时长 |"
    sep    = "|---------|------|------|---------|-------|---------|------|"
    platform = "YouTube" if source == "youtube" else "Bilibili"
    rows = [header, sep]

    for r in results:
        title = _escape_md(r.get("title", ""))
        url = r.get("url", "")
        date = r.get("published_at", "")
        views = _format_views(r.get("view_count") or r.get("play_count") or 0)
        who = _escape_md(r.get("channel") or r.get("author") or "")
        duration = r.get("duration", "")
        mark = _verify_mark(r)

        rows.append(
            f"| {title} | [观看]({url}) | {platform} | {date} | {views} | {who} | {duration} {mark}|"
        )

    return "\n".join(rows)


def _render_google_table(results: list[dict]) -> str:
    header = "| 内容名称 | 链接 | 来源 | 日期 | 摘要 |"
    sep    = "|---------|------|------|------|------|"
    rows = [header, sep]

    for r in results:
        title = _escape_md(r.get("title", ""))
        url = r.get("url", "")
        date = r.get("date", "")
        snippet = _escape_md(r.get("snippet", ""))[:80]
        mark = _verify_mark(r)

        rows.append(
            f"| {title} | [链接]({url}) | Google | {date} | {snippet} {mark}|"
        )

    return "\n".join(rows)


def _format_views(count: int | str) -> str:
    try:
        n = int(count)
    except (ValueError, TypeError):
        return str(count) if count else ""

    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)


def _escape_md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _verify_mark(r: dict) -> str:
    verified = r.get("verified")
    if verified is False and r.get("verify_status", 0) == 0:
        return "⚠️"
    return ""
