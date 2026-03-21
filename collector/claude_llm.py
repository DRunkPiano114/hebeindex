"""
claude_llm.py — Thin wrapper around `claude -p` CLI for LLM calls.

All LLM calls in the collector go through this module.
Uses `claude` CLI (already installed and authenticated) instead of
LiteLLM + OpenRouter, eliminating the need for OPENROUTER_API_KEY.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time

logger = logging.getLogger(__name__)

# Module-level flag: set to True to show real-time progress via stream-json.
# Toggled by pipeline.py / reclassify.py --verbose flag.
VERBOSE = False


def _stream_claude(cmd: list[str], timeout: int) -> str:
    """Run claude with stream-json + partial messages, show real-time progress."""
    cmd = cmd + ["--include-partial-messages"]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    result_text = ""
    t0 = time.time()
    # Track state for throttled progress updates
    thinking_chars = 0
    text_chars = 0
    last_thinking_log = 0.0
    last_text_log = 0.0
    current_phase = ""  # "thinking" or "text"

    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            elapsed = time.time() - t0
            etype = event.get("type", "")

            if etype == "system":
                model = event.get("model", "?")
                logger.info("  [%5.1fs] connected, model=%s", elapsed, model)

            elif etype == "stream_event":
                ev = event.get("event", {})
                ev_type = ev.get("type", "")

                if ev_type == "content_block_start":
                    block = ev.get("content_block", {})
                    btype = block.get("type", "")
                    if btype == "thinking":
                        current_phase = "thinking"
                        thinking_chars = 0
                        logger.info("  [%5.1fs] thinking...", elapsed)
                    elif btype == "text":
                        current_phase = "text"
                        text_chars = 0
                        logger.info("  [%5.1fs] generating...", elapsed)
                    elif btype == "tool_use":
                        current_phase = "tool"
                        tool_name = block.get("name", "?")
                        logger.info("  [%5.1fs] calling tool: %s", elapsed, tool_name)

                elif ev_type == "content_block_delta":
                    delta = ev.get("delta", {})
                    dtype = delta.get("type", "")

                    if dtype == "thinking_delta":
                        thinking_chars += len(delta.get("thinking", ""))
                        # Log every 2 seconds
                        if elapsed - last_thinking_log >= 2.0:
                            last_thinking_log = elapsed
                            logger.info("  [%5.1fs] thinking... (%d chars)",
                                        elapsed, thinking_chars)

                    elif dtype == "text_delta":
                        text_chars += len(delta.get("text", ""))
                        # Log every 2 seconds
                        if elapsed - last_text_log >= 2.0:
                            last_text_log = elapsed
                            logger.info("  [%5.1fs] generating... (%d chars)",
                                        elapsed, text_chars)

                    elif dtype == "input_json_delta":
                        pass  # tool input streaming, skip

                elif ev_type == "content_block_stop":
                    if current_phase == "thinking":
                        logger.info("  [%5.1fs] thinking done (%d chars)",
                                    elapsed, thinking_chars)
                    elif current_phase == "text":
                        logger.info("  [%5.1fs] generation done (%d chars)",
                                    elapsed, text_chars)

            elif etype == "assistant":
                # Complete message — check for tool_use blocks
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") == "tool_use":
                        tool = block.get("name", "?")
                        inp = block.get("input", {})
                        detail = (inp.get("command") or inp.get("query")
                                  or inp.get("pattern") or str(inp))[:80]
                        logger.info("  [%5.1fs] tool: %s → %s", elapsed, tool, detail)

            elif etype == "result":
                result_text = event.get("result", "")
                usage = event.get("usage", {})
                cost = event.get("total_cost_usd", 0)
                logger.info("  [%5.1fs] done! tokens: %s→%s, cost: $%.4f",
                            elapsed,
                            usage.get("input_tokens", "?"),
                            usage.get("output_tokens", "?"),
                            cost)

        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise

    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI error (rc={proc.returncode})")

    return result_text


def _extract_text_from_list(data: list) -> str:
    """Extract text content from a list of message objects or content blocks."""
    texts = []
    for item in data:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict):
            # Message with content blocks
            if "content" in item:
                content = item["content"]
                if isinstance(content, str):
                    texts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            texts.append(block.get("text", ""))
            # Direct content block
            elif item.get("type") == "text":
                texts.append(item.get("text", ""))
            # Object with result field
            elif "result" in item:
                texts.append(str(item["result"]))
    return "\n".join(texts) if texts else json.dumps(data)


def claude_call(
    prompt: str,
    system_prompt: str = "",
    json_schema: dict | None = None,
    model: str = "sonnet",
    needs_tools: bool = False,
    timeout: int = 120,
    verbose: bool = False,
) -> str:
    """
    Call claude CLI in non-interactive mode.

    Args:
        prompt: The user prompt to send.
        system_prompt: Optional system prompt.
        json_schema: If provided, enforces JSON output matching this schema.
        model: Model name (sonnet, opus, haiku).
        needs_tools: If True, uses --dangerously-skip-permissions (for web search etc).
                     If False, uses --tools "" to disable tools (faster, safer).
        timeout: Subprocess timeout in seconds.
        verbose: If True, use stream-json to show real-time progress.

    Returns:
        The result text from Claude's response.
    """
    effective_verbose = verbose or VERBOSE
    output_format = "stream-json" if effective_verbose else "json"

    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", output_format]

    if needs_tools:
        cmd.append("--dangerously-skip-permissions")
    else:
        cmd.extend(["--tools", ""])

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    if json_schema:
        cmd.extend(["--json-schema", json.dumps(json_schema)])

    logger.info("claude → model=%s, prompt=%d chars, schema=%s, timeout=%ds",
                model, len(prompt), bool(json_schema), timeout)

    if effective_verbose:
        return _stream_claude(cmd, timeout)

    t0 = time.time()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    elapsed = time.time() - t0

    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.error("claude ✗ rc=%d after %.1fs: %s", result.returncode, elapsed, stderr[:500])
        raise RuntimeError(f"claude CLI error: {stderr[:500]}")

    try:
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            usage = data.get("usage", {})
            input_tokens = usage.get("input_tokens", "?")
            output_tokens = usage.get("output_tokens", "?")
            result_text = data.get("result", result.stdout)
        elif isinstance(data, list):
            result_text = _extract_text_from_list(data)
            input_tokens = "?"
            output_tokens = "?"
        else:
            result_text = str(data)
            input_tokens = "?"
            output_tokens = "?"
        logger.info("claude ✓ %.1fs, tokens: %s→%s, result=%d chars",
                    elapsed, input_tokens, output_tokens, len(result_text))
        return result_text
    except json.JSONDecodeError:
        logger.info("claude ✓ %.1fs, raw output=%d chars", elapsed, len(result.stdout))
        return result.stdout.strip()


def classify_batch(
    items: list[dict],
    categories: list[str],
    artist_name: str,  # noqa: ARG001 — used by callers to build system_prompt
    system_prompt: str,
) -> list[dict]:
    """
    Classify a batch of videos using claude CLI with JSON schema enforcement.

    Returns list of {"index": int, "category": str, "reason": str}.
    """
    lines = []
    for i, item in enumerate(items):
        desc = (item.get("description") or "")[:200]
        dur = item.get("duration", "N/A")
        channel = item.get("channel") or item.get("author") or "N/A"
        lines.append(
            f"[{i}] 标题: {item.get('title', 'N/A')}\n"
            f"    频道: {channel}\n"
            f"    时长: {dur}\n"
            f"    简介: {desc}"
        )

    user_msg = f"请对以下 {len(items)} 条视频进行分类：\n\n" + "\n\n".join(lines)

    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "category": {"type": "string", "enum": categories + ["discard"]},
                "reason": {"type": "string"},
            },
            "required": ["index", "category", "reason"],
        },
    }

    logger.info("classify_batch: %d items, %d categories", len(items), len(categories))
    try:
        raw = claude_call(
            prompt=user_msg,
            system_prompt=system_prompt,
            json_schema=schema,
            model="sonnet",
            timeout=180,
        )
        results = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(results, list):
            logger.info("classify_batch: got %d classifications", len(results))
            return results
        logger.warning("Unexpected classify response type: %s", type(results))
        return []
    except Exception as e:
        logger.error("classify_batch failed: %s", e)
        return []


def format_markdown(
    data: dict,
    system_prompt: str,
) -> str:
    """
    Format processed data as markdown using claude CLI.

    Args:
        data: Compact results dict with title, description, results.
        system_prompt: Formatting instructions.

    Returns:
        Formatted markdown string.
    """
    user_msg = (
        f"请将以下搜索结果整理成 Markdown 文件。\n\n"
        f"文件标题：{data['title']}\n"
        f"文件说明：{data['description']}\n"
        f"结果总数：{data['total_results']}\n\n"
        f"搜索结果 JSON：\n```json\n{json.dumps(data['results'], ensure_ascii=False)}\n```"
    )

    logger.info("format_markdown: '%s', %d results, prompt=%d chars",
                data['title'], data['total_results'], len(user_msg))

    raw = claude_call(
        prompt=user_msg,
        system_prompt=system_prompt,
        model="sonnet",
        timeout=180,
    )

    # Strip wrapping code fences if present
    text = raw.strip()
    if text.startswith("```"):
        first_nl = text.index("\n") if "\n" in text else len(text)
        text = text[first_nl + 1:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
