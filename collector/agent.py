"""
agent.py — 田馥甄内容收集 Agent 主入口

使用 LiteLLM Router + OpenRouter 统一网关，单个 OPENROUTER_API_KEY 即可
访问多个 provider；路由顺序：Gemini 3.1 Pro → Claude Sonnet → OpenAI。
最终输出完整、准确的 Markdown 资料库到 output/ 目录。

运行：
    uv run python agent.py
    uv run python agent.py --resume   # 从 checkpoint 续跑
"""

import os
import sys
import json
import time
import logging
import argparse
import traceback
from pathlib import Path
from datetime import datetime

import litellm
from litellm import Router
from dotenv import load_dotenv

from config import (
    LOG_MODEL_LABEL,
    MAX_TOKENS,
    MAX_ITERATIONS,
    OUTPUT_DIR,
    OPENROUTER_MODEL_GEMINI,
    OPENROUTER_MODEL_SONNET,
    OPENROUTER_MODEL_OPENAI,
    ROUTER_ALLOWED_FAILS,
    ROUTER_COOLDOWN_TIME,
    ROUTER_NUM_RETRIES,
    CONTEXT_WINDOW_LIMIT,
    CONTEXT_WARNING_THRESHOLD,
)
from tools import (
    YouTubeSearchTool,
    GoogleSearchTool,
    BilibiliSearchTool,
    URLVerifier,
    FileWriter,
    DuplicateTracker,
)
from prompts import SYSTEM_PROMPT, INITIAL_TASK

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            Path(OUTPUT_DIR).parent / "agent_run.log",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("hebe_agent")
litellm.suppress_debug_info = True


# ---------------------------------------------------------------------------
# Tool schemas — OpenAI function-calling format (used by LiteLLM)
# ---------------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "youtube_search",
            "description": (
                "在 YouTube 搜索田馥甄（Hebe）相关视频，使用 YouTube Data API v3。"
                "返回结果均由官方 API 确认为真实存在的公开视频，无需再验证。"
                "每次最多返回 30 条，建议多次用不同查询词搜索以覆盖全面。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，支持中英文",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "返回结果数量，最大 30，默认 20",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "google_search",
            "description": (
                "通过 Serper.dev 调用 Google 搜索。适合搜索 Bilibili 视频页面链接、"
                "新闻报道、采访文章等。返回结果需要 verify_urls 验证。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，可用 site:bilibili.com 限定站点",
                    },
                    "num": {
                        "type": "integer",
                        "description": "返回结果数，最大 10，默认 10",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bilibili_search",
            "description": (
                "搜索 Bilibili（哔哩哔哩）视频。使用 Bilibili 公开搜索接口，无需密钥。"
                "返回视频列表含标题、BV 链接、播放量、作者、发布日期。"
                "结果需要通过 verify_urls 验证后才能写入文件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                    "page": {
                        "type": "integer",
                        "description": "页码，从 1 开始，每页最多 50 条，默认 1",
                    },
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_urls",
            "description": (
                "验证 URL 列表是否可访问。YouTube 链接默认已验证，不必传入。"
                "Bilibili 和 Google 搜索结果的链接必须通过此工具验证，"
                "valid=false（404/0 等）的链接不应写入输出文件。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "需要验证的 URL 列表（最多一次 50 条）",
                    }
                },
                "required": ["urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "将 Markdown 内容写入 output/ 目录下的指定文件。"
                "写入前请确保：已完成该文件的所有搜索、去重、链接验证。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "相对于 output/ 的路径，例如 '专辑与MV/个人MV完整列表.md'",
                    },
                    "content": {
                        "type": "string",
                        "description": "完整的 Markdown 文件内容",
                    },
                },
                "required": ["relative_path", "content"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def execute_tool(
    name: str,
    inputs: dict,
    tools_map: dict,
    tracker: DuplicateTracker | None = None,
) -> str:
    """
    Dispatch a tool call and return the result as a JSON string.
    Never raises — all errors are caught and returned as error strings.
    """
    logger.info(
        "TOOL CALL: %s | inputs: %s",
        name,
        json.dumps(inputs, ensure_ascii=False)[:120],
    )

    try:
        if name == "youtube_search":
            results = tools_map["youtube"].search(
                query=inputs["query"],
                max_results=inputs.get("max_results", 20),
            )
            if tracker:
                results = tracker.filter_results(results, "youtube")
            return json.dumps(results, ensure_ascii=False)

        elif name == "google_search":
            results = tools_map["google"].search(
                query=inputs["query"],
                num=inputs.get("num", 10),
            )
            if tracker:
                results = tracker.filter_results(results, "google")
            return json.dumps(results, ensure_ascii=False)

        elif name == "bilibili_search":
            results = tools_map["bilibili"].search(
                keyword=inputs["keyword"],
                page=inputs.get("page", 1),
            )
            if tracker:
                results = tracker.filter_results(results, "bilibili")
            return json.dumps(results, ensure_ascii=False)

        elif name == "verify_urls":
            urls = inputs.get("urls", [])
            if not urls:
                return json.dumps({})
            all_results: dict = {}
            for i in range(0, len(urls), 50):
                batch = urls[i : i + 50]
                all_results.update(tools_map["verifier"].verify(batch))
            return json.dumps(all_results, ensure_ascii=False)

        elif name == "write_file":
            result = tools_map["writer"].write(
                relative_path=inputs["relative_path"],
                content=inputs["content"],
            )
            return result

        else:
            return f"ERROR: Unknown tool '{name}'"

    except Exception as exc:
        logger.error("Tool %s raised: %s", name, traceback.format_exc())
        return f"ERROR: {type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# LiteLLM Router builder
# ---------------------------------------------------------------------------

def build_router(openrouter_key: str) -> Router:
    """
    Build a LiteLLM Router backed by OpenRouter (single API key).
    Routing order:
      order=1  Gemini 3.1 Pro Preview  (primary)
      order=2  Claude Sonnet           (secondary)
      order=3  OpenAI                  (final fallback)
    """
    model_list = [
        {
            "model_name": "primary",
            "litellm_params": {
                "model": OPENROUTER_MODEL_GEMINI,
                "api_key": openrouter_key,
                "order": 1,
            },
        },
        {
            "model_name": "primary",
            "litellm_params": {
                "model": OPENROUTER_MODEL_SONNET,
                "api_key": openrouter_key,
                "order": 2,
            },
        },
        {
            "model_name": "primary",
            "litellm_params": {
                "model": OPENROUTER_MODEL_OPENAI,
                "api_key": openrouter_key,
                "order": 3,
            },
        },
    ]

    router = Router(
        model_list=model_list,
        allowed_fails=ROUTER_ALLOWED_FAILS,
        cooldown_time=ROUTER_COOLDOWN_TIME,
        num_retries=ROUTER_NUM_RETRIES,
        enable_pre_call_checks=True,
    )
    logger.info(
        "LiteLLM Router built via OpenRouter: %s → %s → %s",
        OPENROUTER_MODEL_GEMINI,
        OPENROUTER_MODEL_SONNET,
        OPENROUTER_MODEL_OPENAI,
    )
    return router


# ---------------------------------------------------------------------------
# Message helpers (OpenAI format)
# ---------------------------------------------------------------------------

def make_user_message(content: str) -> dict:
    return {"role": "user", "content": content}


def make_tool_result_messages(
    tool_calls,
    tools_map: dict,
    tracker: DuplicateTracker | None = None,
) -> list[dict]:
    """Execute all tool calls and return OpenAI-format tool result messages."""
    results = []
    for tc in tool_calls:
        try:
            inputs = json.loads(tc.function.arguments)
        except Exception:
            inputs = {}
        raw = execute_tool(tc.function.name, inputs, tools_map, tracker=tracker)
        results.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": raw,
        })
    return results


# ---------------------------------------------------------------------------
# Checkpoint (save/load messages for resume)
# ---------------------------------------------------------------------------
CHECKPOINT_PATH = Path(__file__).parent / ".checkpoint.json"


def save_checkpoint(messages: list) -> None:
    CHECKPOINT_PATH.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.debug("Checkpoint saved (%d messages)", len(messages))


def load_checkpoint() -> list | None:
    if CHECKPOINT_PATH.exists():
        try:
            return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Context trimming — respects conversation turn boundaries
# ---------------------------------------------------------------------------

def _trim_messages_safe(messages: list[dict], keep_last: int = 60) -> list[dict]:
    """Trim old messages while preserving tool-call / tool-result pairs.

    Keeps messages[0] (initial task) + the last ~keep_last messages, but
    adjusts the cut point forward so it never lands on a "tool" role message
    (which would orphan it from its preceding assistant tool_calls).
    """
    if len(messages) <= keep_last + 1:
        return messages

    candidate = len(messages) - keep_last

    for i in range(candidate, len(messages)):
        if messages[i]["role"] != "tool":
            return [messages[0]] + messages[i:]

    return [messages[0]] + messages[candidate:]


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

def run_agent(resume: bool = False) -> None:
    load_dotenv()

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    serper_key     = os.getenv("SERPER_API_KEY")

    # Collect all provided YouTube keys (key 1 required, keys 2–3 optional)
    youtube_keys = [
        k for k in [
            os.getenv("YOUTUBE_API_KEY"),
            os.getenv("YOUTUBE_API_KEY_2"),
            os.getenv("YOUTUBE_API_KEY_3"),
        ] if k
    ]

    missing = [k for k, v in [
        ("OPENROUTER_API_KEY", openrouter_key),
        ("YOUTUBE_API_KEY",    youtube_keys[0] if youtube_keys else None),
        ("SERPER_API_KEY",     serper_key),
    ] if not v]
    if missing:
        logger.error("Missing required API keys in .env: %s", ", ".join(missing))
        sys.exit(1)

    logger.info(
        "YouTube: %d key(s) loaded → %d units/day capacity",
        len(youtube_keys),
        len(youtube_keys) * 10_000,
    )

    # Build tools
    tools_map = {
        "youtube":  YouTubeSearchTool(youtube_keys),
        "google":   GoogleSearchTool(serper_key),
        "bilibili": BilibiliSearchTool(),
        "verifier": URLVerifier(),
        "writer":   FileWriter(OUTPUT_DIR),
    }

    tracker = DuplicateTracker()
    router = build_router(openrouter_key)

    # Initialize or restore conversation (OpenAI format)
    if resume and (checkpoint := load_checkpoint()):
        messages = checkpoint
        logger.info("Resumed from checkpoint (%d messages)", len(messages))
    else:
        messages = [make_user_message(INITIAL_TASK)]
        logger.info("Starting fresh run")

    start_time = time.time()
    iteration   = 0
    tool_calls_total = 0
    empty_response_streak = 0
    MAX_EMPTY_RETRIES = 3

    logger.info("=" * 60)
    logger.info("Hebe Content Collection Agent — %s", LOG_MODEL_LABEL)
    logger.info("Output directory: %s", OUTPUT_DIR)
    logger.info("=" * 60)

    while iteration < MAX_ITERATIONS:
        iteration += 1
        logger.info("--- Iteration %d ---", iteration)

        # ---- Call LLM via Router ----
        try:
            response = router.completion(
                model="primary",
                max_tokens=MAX_TOKENS,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
            )
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            time.sleep(10)
            continue

        choice = response.choices[0]
        finish_reason = choice.finish_reason
        msg = choice.message

        prompt_tokens = response.usage.prompt_tokens
        logger.info(
            "finish_reason: %s | usage: input=%d output=%d",
            finish_reason,
            prompt_tokens,
            response.usage.completion_tokens,
        )

        if prompt_tokens > CONTEXT_WINDOW_LIMIT * 0.95:
            logger.warning(
                "Context 95%% full (%d tokens), trimming old messages",
                prompt_tokens,
            )
            messages = _trim_messages_safe(messages)
        elif prompt_tokens > CONTEXT_WINDOW_LIMIT * CONTEXT_WARNING_THRESHOLD:
            logger.warning(
                "Context %.0f%% full (%d / %d tokens)",
                prompt_tokens / CONTEXT_WINDOW_LIMIT * 100,
                prompt_tokens,
                CONTEXT_WINDOW_LIMIT,
            )

        completion_tokens = response.usage.completion_tokens

        # ---- Guard: detect empty response (0 output tokens) ----
        is_empty = (
            completion_tokens == 0
            or (not msg.content and not msg.tool_calls)
        )

        if is_empty:
            empty_response_streak += 1
            logger.warning(
                "Empty response detected (streak %d/%d) — "
                "finish_reason=%s, output_tokens=%d, input_tokens=%d",
                empty_response_streak, MAX_EMPTY_RETRIES,
                finish_reason, completion_tokens, prompt_tokens,
            )
            if empty_response_streak >= MAX_EMPTY_RETRIES:
                logger.error(
                    "Aborting: %d consecutive empty responses. "
                    "Context may be too large (%d tokens) or model is failing.",
                    MAX_EMPTY_RETRIES, prompt_tokens,
                )
                break

            if prompt_tokens > CONTEXT_WINDOW_LIMIT * 0.7:
                logger.warning("Trimming context to recover from empty response")
                messages = _trim_messages_safe(messages, keep_last=30)

            time.sleep(5 * empty_response_streak)
            continue

        empty_response_streak = 0

        # Append assistant turn
        assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)
        save_checkpoint(messages)

        # ---- Done (only when model actually produced text, not empty) ----
        if finish_reason == "stop":
            logger.info("Agent signaled completion.")
            break

        # ---- Execute tool calls ----
        if finish_reason == "tool_calls" and msg.tool_calls:
            tool_calls_total += len(msg.tool_calls)
            tool_results = make_tool_result_messages(msg.tool_calls, tools_map, tracker=tracker)
            messages.extend(tool_results)
            save_checkpoint(messages)

        time.sleep(1)

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info(
        "Finished in %.1f s | %d iterations | %d tool calls",
        elapsed, iteration, tool_calls_total,
    )
    logger.info("Output: %s", OUTPUT_DIR)
    logger.info("=" * 60)

    # Clean up checkpoint on success
    if iteration < MAX_ITERATIONS and CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
        logger.info("Checkpoint removed.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="田馥甄 Hebe Content Collection Agent")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="从上次 checkpoint 续跑（断点续传）",
    )
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    run_agent(resume=args.resume)
