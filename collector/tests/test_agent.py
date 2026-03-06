"""
test_agent.py — collector/agent.py 的单元与集成测试

覆盖范围：
- execute_tool：各工具调度、未知工具、异常吞掉、DuplicateTracker 集成
- save_checkpoint / load_checkpoint：正常保存/加载、损坏文件容错、不存在时返回 None
- run_agent 主循环：
    - 缺失 API Key 时 sys.exit(1)
    - stop 时正常结束并清理 checkpoint
    - tool_calls 时执行工具并追加结果消息
    - LLM 异常时 sleep 重试
    - 超出 MAX_ITERATIONS 时退出
    - resume=True 时从 checkpoint 恢复
"""

import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import agent as agent_mod
from agent import execute_tool, save_checkpoint, load_checkpoint, CHECKPOINT_PATH, _trim_messages_safe
from tools import DuplicateTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tools_map(
    youtube_results=None,
    google_results=None,
    bilibili_results=None,
    verify_results=None,
    write_result="OK: /output/test.md",
):
    tools_map = {
        "youtube":  MagicMock(),
        "google":   MagicMock(),
        "bilibili": MagicMock(),
        "verifier": MagicMock(),
        "writer":   MagicMock(),
    }
    tools_map["youtube"].search.return_value  = youtube_results or []
    tools_map["google"].search.return_value   = google_results  or []
    tools_map["bilibili"].search.return_value = bilibili_results or []
    tools_map["verifier"].verify.return_value = verify_results  or {}
    tools_map["writer"].write.return_value    = write_result
    return tools_map


def _make_openai_response(finish_reason, content=None, tool_calls=None):
    """Build a mock OpenAI-format response (used by LiteLLM Router)."""
    msg = MagicMock()
    msg.content = content or ""
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage.prompt_tokens = 100
    resp.usage.completion_tokens = 50
    return resp


def _make_tool_call(tool_id, name, arguments):
    """Build a mock OpenAI-format tool call object."""
    tc = MagicMock()
    tc.id = tool_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments, ensure_ascii=False)
    return tc


# ---------------------------------------------------------------------------
# _trim_messages_safe
# ---------------------------------------------------------------------------

class TestTrimMessagesSafe:
    def test_short_conversation_unchanged(self):
        msgs = [{"role": "user", "content": "task"}] + [
            {"role": "assistant", "content": f"msg{i}"} for i in range(10)
        ]
        result = _trim_messages_safe(msgs, keep_last=60)
        assert result == msgs

    def test_trims_keeping_first_message(self):
        msgs = [{"role": "user", "content": "task"}] + [
            {"role": "assistant", "content": f"msg{i}"} for i in range(100)
        ]
        result = _trim_messages_safe(msgs, keep_last=20)
        assert result[0] == msgs[0]
        assert len(result) == 21  # first + 20 kept

    def test_skips_tool_role_at_boundary(self):
        """Cut point should advance past 'tool' messages to avoid orphaning them."""
        msgs = [{"role": "user", "content": "task"}]
        for i in range(80):
            msgs.append({"role": "assistant", "content": f"a{i}"})
        # Place a tool-call assistant + tool results right at the naive cut point
        msgs.append({"role": "assistant", "content": "calling tool", "tool_calls": [{"id": "1"}]})
        msgs.append({"role": "tool", "tool_call_id": "1", "content": "result1"})
        msgs.append({"role": "tool", "tool_call_id": "2", "content": "result2"})
        msgs.append({"role": "user", "content": "next turn"})
        for i in range(5):
            msgs.append({"role": "assistant", "content": f"b{i}"})

        result = _trim_messages_safe(msgs, keep_last=10)
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "task"
        # No message in result (except first) should be orphaned:
        # the first non-system message should NOT be role=tool
        assert result[1]["role"] != "tool"

    def test_all_tool_messages_fallback(self):
        """If every candidate is a tool message, fall back to naive cut."""
        msgs = [{"role": "user", "content": "task"}]
        for i in range(10):
            msgs.append({"role": "tool", "tool_call_id": str(i), "content": f"r{i}"})
        result = _trim_messages_safe(msgs, keep_last=5)
        assert result[0]["content"] == "task"
        assert len(result) == 6


# ---------------------------------------------------------------------------
# execute_tool
# ---------------------------------------------------------------------------

class TestExecuteTool:
    def test_youtube_search_dispatches_and_returns_json(self):
        tools_map = _make_tools_map(youtube_results=[{"title": "MV", "url": "https://yt.com/1"}])
        result = execute_tool("youtube_search", {"query": "田馥甄"}, tools_map)
        data = json.loads(result)
        assert data[0]["title"] == "MV"
        tools_map["youtube"].search.assert_called_once_with(query="田馥甄", max_results=20)

    def test_youtube_search_uses_max_results_param(self):
        tools_map = _make_tools_map()
        execute_tool("youtube_search", {"query": "Hebe", "max_results": 5}, tools_map)
        tools_map["youtube"].search.assert_called_once_with(query="Hebe", max_results=5)

    def test_google_search_dispatches(self):
        tools_map = _make_tools_map(google_results=[{"url": "https://g.com"}])
        result = execute_tool("google_search", {"query": "田馥甄 site:bilibili.com"}, tools_map)
        data = json.loads(result)
        assert data[0]["url"] == "https://g.com"
        tools_map["google"].search.assert_called_once_with(
            query="田馥甄 site:bilibili.com", num=10
        )

    def test_google_search_custom_num(self):
        tools_map = _make_tools_map()
        execute_tool("google_search", {"query": "Q", "num": 5}, tools_map)
        tools_map["google"].search.assert_called_once_with(query="Q", num=5)

    def test_bilibili_search_dispatches(self):
        tools_map = _make_tools_map(bilibili_results=[{"bvid": "BV1xx"}])
        result = execute_tool("bilibili_search", {"keyword": "田馥甄"}, tools_map)
        data = json.loads(result)
        assert data[0]["bvid"] == "BV1xx"
        tools_map["bilibili"].search.assert_called_once_with(keyword="田馥甄", page=1)

    def test_bilibili_search_custom_page(self):
        tools_map = _make_tools_map()
        execute_tool("bilibili_search", {"keyword": "Hebe", "page": 2}, tools_map)
        tools_map["bilibili"].search.assert_called_once_with(keyword="Hebe", page=2)

    def test_verify_urls_single_batch(self):
        urls = ["https://bilibili.com/1", "https://bilibili.com/2"]
        verify_data = {u: {"valid": True, "status": 200, "note": ""} for u in urls}
        tools_map = _make_tools_map(verify_results=verify_data)
        result = execute_tool("verify_urls", {"urls": urls}, tools_map)
        data = json.loads(result)
        assert all(data[u]["valid"] for u in urls)
        tools_map["verifier"].verify.assert_called_once_with(urls)

    def test_verify_urls_batches_by_50(self):
        urls = [f"https://example.com/{i}" for i in range(120)]
        tools_map = _make_tools_map(verify_results={})
        execute_tool("verify_urls", {"urls": urls}, tools_map)
        assert tools_map["verifier"].verify.call_count == 3
        first_call_urls = tools_map["verifier"].verify.call_args_list[0][0][0]
        assert len(first_call_urls) == 50

    def test_verify_urls_empty_list_returns_empty_dict(self):
        tools_map = _make_tools_map()
        result = execute_tool("verify_urls", {"urls": []}, tools_map)
        assert json.loads(result) == {}
        tools_map["verifier"].verify.assert_not_called()

    def test_write_file_dispatches(self):
        tools_map = _make_tools_map(write_result="OK: /output/MV.md")
        result = execute_tool(
            "write_file",
            {"relative_path": "专辑与MV/MV.md", "content": "# MV"},
            tools_map,
        )
        assert result == "OK: /output/MV.md"
        tools_map["writer"].write.assert_called_once_with(
            relative_path="专辑与MV/MV.md", content="# MV"
        )

    def test_unknown_tool_returns_error_string(self):
        tools_map = _make_tools_map()
        result = execute_tool("nonexistent_tool", {}, tools_map)
        assert result.startswith("ERROR: Unknown tool")
        assert "nonexistent_tool" in result

    def test_tool_exception_is_caught_and_returned_as_string(self):
        tools_map = _make_tools_map()
        tools_map["youtube"].search.side_effect = RuntimeError("API crash")
        result = execute_tool("youtube_search", {"query": "Q"}, tools_map)
        assert result.startswith("ERROR: RuntimeError")
        assert "API crash" in result

    def test_verify_urls_missing_key_defaults_empty(self):
        tools_map = _make_tools_map()
        result = execute_tool("verify_urls", {}, tools_map)
        assert json.loads(result) == {}

    def test_tracker_marks_duplicate_youtube(self):
        tracker = DuplicateTracker()
        tools_map = _make_tools_map(
            youtube_results=[{"title": "MV", "url": "https://www.youtube.com/watch?v=abc123"}]
        )
        result1 = execute_tool("youtube_search", {"query": "Q"}, tools_map, tracker=tracker)
        data1 = json.loads(result1)
        assert "_duplicate" not in data1[0]

        result2 = execute_tool("youtube_search", {"query": "Q"}, tools_map, tracker=tracker)
        data2 = json.loads(result2)
        assert data2[0].get("_duplicate") is True

    def test_tracker_marks_duplicate_bilibili(self):
        tracker = DuplicateTracker()
        tools_map = _make_tools_map(
            bilibili_results=[{"bvid": "BV1xx", "url": "https://www.bilibili.com/video/BV1xx"}]
        )
        execute_tool("bilibili_search", {"keyword": "Q"}, tools_map, tracker=tracker)
        result2 = execute_tool("bilibili_search", {"keyword": "Q"}, tools_map, tracker=tracker)
        data2 = json.loads(result2)
        assert data2[0].get("_duplicate") is True


# ---------------------------------------------------------------------------
# save_checkpoint / load_checkpoint
# ---------------------------------------------------------------------------

class TestCheckpoint:
    def setup_method(self):
        if CHECKPOINT_PATH.exists():
            CHECKPOINT_PATH.unlink()

    def teardown_method(self):
        if CHECKPOINT_PATH.exists():
            CHECKPOINT_PATH.unlink()

    def test_save_and_load_roundtrip(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        save_checkpoint(messages)
        loaded = load_checkpoint()
        assert loaded == messages

    def test_save_creates_file(self):
        save_checkpoint([{"role": "user", "content": "x"}])
        assert CHECKPOINT_PATH.exists()

    def test_save_writes_valid_json(self):
        messages = [{"role": "user", "content": "test"}]
        save_checkpoint(messages)
        raw = CHECKPOINT_PATH.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert parsed == messages

    def test_load_returns_none_when_no_file(self):
        assert not CHECKPOINT_PATH.exists()
        assert load_checkpoint() is None

    def test_load_returns_none_on_corrupt_json(self):
        CHECKPOINT_PATH.write_text("NOT JSON {{{{", encoding="utf-8")
        assert load_checkpoint() is None

    def test_save_handles_chinese_content(self):
        messages = [{"role": "user", "content": "田馥甄 Hebe 🎵"}]
        save_checkpoint(messages)
        loaded = load_checkpoint()
        assert loaded[0]["content"] == "田馥甄 Hebe 🎵"

    def test_save_overwrites_previous(self):
        save_checkpoint([{"role": "user", "content": "old"}])
        save_checkpoint([{"role": "user", "content": "new"}])
        loaded = load_checkpoint()
        assert loaded[0]["content"] == "new"

    def test_checkpoint_contains_tool_calls(self):
        """确保 OpenAI 格式 tool_calls 可正常序列化和恢复。"""
        messages = [
            {
                "role": "assistant",
                "content": "searching...",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "youtube_search",
                            "arguments": '{"query": "Q"}',
                        },
                    }
                ],
            }
        ]
        save_checkpoint(messages)
        loaded = load_checkpoint()
        assert loaded[0]["tool_calls"][0]["function"]["name"] == "youtube_search"


# ---------------------------------------------------------------------------
# run_agent 集成测试
# ---------------------------------------------------------------------------

class TestRunAgent:
    """run_agent 主循环集成测试——所有外部依赖均 mock。"""

    BASE_ENV = {
        "OPENROUTER_API_KEY": "fake-or",
        "YOUTUBE_API_KEY": "fake-yt",
        "SERPER_API_KEY": "fake-serper",
    }

    def setup_method(self):
        if CHECKPOINT_PATH.exists():
            CHECKPOINT_PATH.unlink()

    def teardown_method(self):
        if CHECKPOINT_PATH.exists():
            CHECKPOINT_PATH.unlink()

    @patch.dict(os.environ, {}, clear=True)
    @patch("agent.load_dotenv")
    def test_missing_api_keys_exits_1(self, mock_dotenv):
        with pytest.raises(SystemExit) as exc_info:
            agent_mod.run_agent()
        assert exc_info.value.code == 1

    @patch.dict(os.environ, BASE_ENV)
    @patch("agent.load_dotenv")
    @patch("agent.time.sleep")
    @patch("agent.FileWriter")
    @patch("agent.URLVerifier")
    @patch("agent.BilibiliSearchTool")
    @patch("agent.GoogleSearchTool")
    @patch("agent.YouTubeSearchTool")
    @patch("agent.build_router")
    def test_stop_exits_and_cleans_checkpoint(
        self, mock_build_router, mock_yt, mock_google, mock_bili,
        mock_verifier, mock_writer, mock_sleep, mock_dotenv
    ):
        """finish_reason='stop' 时 agent 正常结束，checkpoint 被删除。"""
        mock_router = mock_build_router.return_value
        mock_router.completion.return_value = _make_openai_response(
            "stop", content="All done."
        )

        agent_mod.run_agent(resume=False)

        assert not CHECKPOINT_PATH.exists()

    @patch.dict(os.environ, BASE_ENV)
    @patch("agent.load_dotenv")
    @patch("agent.time.sleep")
    @patch("agent.FileWriter")
    @patch("agent.URLVerifier")
    @patch("agent.BilibiliSearchTool")
    @patch("agent.GoogleSearchTool")
    @patch("agent.YouTubeSearchTool")
    @patch("agent.build_router")
    def test_tool_calls_executes_tool_and_appends_result(
        self, mock_build_router, mock_yt, mock_google, mock_bili,
        mock_verifier, mock_writer, mock_sleep, mock_dotenv
    ):
        """tool_calls 时应调用 execute_tool 并把结果追加到 messages。"""
        mock_router = mock_build_router.return_value

        snapshots: list[list] = []
        tool_call = _make_tool_call("call_1", "youtube_search", {"query": "Hebe"})
        responses = [
            _make_openai_response("tool_calls", content="", tool_calls=[tool_call]),
            _make_openai_response("stop", content="done"),
        ]

        def capture(**kwargs):
            snapshots.append([dict(m) for m in kwargs["messages"]])
            return responses.pop(0)

        mock_router.completion.side_effect = capture

        yt_instance = mock_yt.return_value
        yt_instance.search.return_value = [{"title": "MV", "url": "https://yt.com/1"}]

        agent_mod.run_agent(resume=False)

        assert mock_router.completion.call_count == 2

        second_snapshot = snapshots[1]
        tool_result_msg = second_snapshot[-1]
        assert tool_result_msg["role"] == "tool"
        assert tool_result_msg["tool_call_id"] == "call_1"

    @patch.dict(os.environ, BASE_ENV)
    @patch("agent.load_dotenv")
    @patch("agent.time.sleep")
    @patch("agent.FileWriter")
    @patch("agent.URLVerifier")
    @patch("agent.BilibiliSearchTool")
    @patch("agent.GoogleSearchTool")
    @patch("agent.YouTubeSearchTool")
    @patch("agent.build_router")
    def test_llm_exception_sleeps_and_retries(
        self, mock_build_router, mock_yt, mock_google, mock_bili,
        mock_verifier, mock_writer, mock_sleep, mock_dotenv
    ):
        """LLM 调用异常时应 sleep(10) 并继续循环。"""
        mock_router = mock_build_router.return_value
        mock_router.completion.side_effect = [
            Exception("rate limited"),
            _make_openai_response("stop", content="ok"),
        ]

        agent_mod.run_agent(resume=False)

        mock_sleep.assert_any_call(10)
        assert mock_router.completion.call_count == 2

    @patch.dict(os.environ, BASE_ENV)
    @patch("agent.load_dotenv")
    @patch("agent.time.sleep")
    @patch("agent.FileWriter")
    @patch("agent.URLVerifier")
    @patch("agent.BilibiliSearchTool")
    @patch("agent.GoogleSearchTool")
    @patch("agent.YouTubeSearchTool")
    @patch("agent.build_router")
    def test_max_iterations_respected(
        self, mock_build_router, mock_yt, mock_google, mock_bili,
        mock_verifier, mock_writer, mock_sleep, mock_dotenv
    ):
        """超过 MAX_ITERATIONS 时循环应停止。"""
        mock_router = mock_build_router.return_value
        mock_router.completion.return_value = _make_openai_response(
            "length", content="..."
        )

        with patch("agent.MAX_ITERATIONS", 3):
            agent_mod.run_agent(resume=False)

        assert mock_router.completion.call_count == 3

    @patch.dict(os.environ, BASE_ENV)
    @patch("agent.load_dotenv")
    @patch("agent.time.sleep")
    @patch("agent.FileWriter")
    @patch("agent.URLVerifier")
    @patch("agent.BilibiliSearchTool")
    @patch("agent.GoogleSearchTool")
    @patch("agent.YouTubeSearchTool")
    @patch("agent.build_router")
    def test_resume_loads_checkpoint(
        self, mock_build_router, mock_yt, mock_google, mock_bili,
        mock_verifier, mock_writer, mock_sleep, mock_dotenv
    ):
        """resume=True 时应从 checkpoint 恢复 messages 而非新建。"""
        saved_messages = [
            {"role": "user", "content": "saved task"},
            {"role": "assistant", "content": "partial"},
        ]
        save_checkpoint(saved_messages)

        mock_router = mock_build_router.return_value
        mock_router.completion.return_value = _make_openai_response(
            "stop", content="done"
        )

        agent_mod.run_agent(resume=True)

        first_call_kwargs = mock_router.completion.call_args_list[0][1]
        msgs = first_call_kwargs["messages"]
        # msgs[0] is system prompt, msgs[1:] are restored from checkpoint
        assert msgs[1]["content"] == "saved task"

    @patch.dict(os.environ, BASE_ENV)
    @patch("agent.load_dotenv")
    @patch("agent.time.sleep")
    @patch("agent.FileWriter")
    @patch("agent.URLVerifier")
    @patch("agent.BilibiliSearchTool")
    @patch("agent.GoogleSearchTool")
    @patch("agent.YouTubeSearchTool")
    @patch("agent.build_router")
    def test_resume_false_starts_fresh(
        self, mock_build_router, mock_yt, mock_google, mock_bili,
        mock_verifier, mock_writer, mock_sleep, mock_dotenv
    ):
        """resume=False 时即使有 checkpoint，也从初始任务重新开始。"""
        save_checkpoint([{"role": "user", "content": "old checkpoint"}])

        mock_router = mock_build_router.return_value
        mock_router.completion.return_value = _make_openai_response(
            "stop", content="done"
        )

        agent_mod.run_agent(resume=False)

        first_call_kwargs = mock_router.completion.call_args_list[0][1]
        msgs = first_call_kwargs["messages"]
        from prompts import INITIAL_TASK
        # msgs[0] is system prompt, msgs[1] is the initial task
        assert msgs[1]["content"] == INITIAL_TASK

    @patch.dict(os.environ, BASE_ENV)
    @patch("agent.load_dotenv")
    @patch("agent.time.sleep")
    @patch("agent.FileWriter")
    @patch("agent.URLVerifier")
    @patch("agent.BilibiliSearchTool")
    @patch("agent.GoogleSearchTool")
    @patch("agent.YouTubeSearchTool")
    @patch("agent.build_router")
    def test_checkpoint_serializable_after_tool_calls(
        self, mock_build_router, mock_yt, mock_google, mock_bili,
        mock_verifier, mock_writer, mock_sleep, mock_dotenv
    ):
        """tool_calls 产生的 assistant entry 必须可 JSON 序列化到 checkpoint。"""
        mock_router = mock_build_router.return_value
        tool_call = _make_tool_call("call_1", "youtube_search", {"query": "Q"})
        responses = [
            _make_openai_response("tool_calls", content="", tool_calls=[tool_call]),
            _make_openai_response("stop", content="done"),
        ]
        mock_router.completion.side_effect = responses

        yt_instance = mock_yt.return_value
        yt_instance.search.return_value = []

        agent_mod.run_agent(resume=False)
