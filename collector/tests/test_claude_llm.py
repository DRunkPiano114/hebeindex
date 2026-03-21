"""
test_claude_llm.py — Tests for claude_llm.py.

Covers:
- _extract_text_from_list: all message/content block formats
- claude_call: dict response, list response, non-JSON fallback, CLI errors,
  timeout, verbose mode delegation, command construction
- classify_batch: success, invalid response, exception handling
- format_markdown: success, fence stripping
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from claude_llm import (
    _extract_text_from_list,
    claude_call,
    classify_batch,
    format_markdown,
)


# ---------------------------------------------------------------------------
# _extract_text_from_list
# ---------------------------------------------------------------------------

class TestExtractTextFromList:
    """Test extracting text from various list formats the CLI might return."""

    def test_list_of_strings(self):
        assert _extract_text_from_list(["hello", "world"]) == "hello\nworld"

    def test_message_with_content_blocks(self):
        data = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Generated YAML content"},
                ],
            }
        ]
        assert _extract_text_from_list(data) == "Generated YAML content"

    def test_message_with_string_content(self):
        data = [{"role": "assistant", "content": "plain string content"}]
        assert _extract_text_from_list(data) == "plain string content"

    def test_direct_content_blocks(self):
        data = [
            {"type": "text", "text": "block one"},
            {"type": "text", "text": "block two"},
        ]
        assert _extract_text_from_list(data) == "block one\nblock two"

    def test_object_with_result_field(self):
        data = [{"result": "the result text"}]
        assert _extract_text_from_list(data) == "the result text"

    def test_mixed_content_types(self):
        data = [
            {"type": "thinking", "thinking": "internal thoughts"},
            {"type": "text", "text": "visible output"},
        ]
        assert _extract_text_from_list(data) == "visible output"

    def test_empty_list_returns_json(self):
        result = _extract_text_from_list([])
        assert result == "[]"

    def test_no_extractable_text_returns_json(self):
        data = [{"type": "tool_use", "name": "search"}]
        result = _extract_text_from_list(data)
        assert result == json.dumps(data)

    def test_multiple_messages_concatenated(self):
        data = [
            {"content": [{"type": "text", "text": "part1"}]},
            {"content": [{"type": "text", "text": "part2"}]},
        ]
        assert _extract_text_from_list(data) == "part1\npart2"

    def test_nested_empty_content(self):
        data = [{"content": []}]
        # No text blocks → falls through to json.dumps
        assert _extract_text_from_list(data) == json.dumps(data)

    def test_content_block_missing_text_key(self):
        data = [{"content": [{"type": "text"}]}]
        assert _extract_text_from_list(data) == ""

    def test_non_text_blocks_skipped(self):
        data = [
            {
                "content": [
                    {"type": "tool_use", "name": "search"},
                    {"type": "text", "text": "actual text"},
                    {"type": "tool_result", "content": "result"},
                ]
            }
        ]
        assert _extract_text_from_list(data) == "actual text"


# ---------------------------------------------------------------------------
# claude_call — command construction
# ---------------------------------------------------------------------------

class TestClaudeCallCommand:
    """Test that claude_call builds the correct CLI command."""

    def _make_result(self, stdout="", stderr="", returncode=0):
        r = MagicMock()
        r.stdout = stdout
        r.stderr = stderr
        r.returncode = returncode
        return r

    @patch("claude_llm.subprocess.run")
    def test_basic_command(self, mock_run):
        mock_run.return_value = self._make_result(
            stdout=json.dumps({"result": "ok"})
        )
        claude_call("hello", model="sonnet")
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "hello" in cmd
        assert "--model" in cmd
        assert "sonnet" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd

    @patch("claude_llm.subprocess.run")
    def test_needs_tools_adds_skip_permissions(self, mock_run):
        mock_run.return_value = self._make_result(
            stdout=json.dumps({"result": "ok"})
        )
        claude_call("hello", needs_tools=True)
        cmd = mock_run.call_args[0][0]
        assert "--dangerously-skip-permissions" in cmd
        assert "--tools" not in cmd

    @patch("claude_llm.subprocess.run")
    def test_no_tools_disables_tools(self, mock_run):
        mock_run.return_value = self._make_result(
            stdout=json.dumps({"result": "ok"})
        )
        claude_call("hello", needs_tools=False)
        cmd = mock_run.call_args[0][0]
        assert "--tools" in cmd
        assert "--dangerously-skip-permissions" not in cmd

    @patch("claude_llm.subprocess.run")
    def test_system_prompt_added(self, mock_run):
        mock_run.return_value = self._make_result(
            stdout=json.dumps({"result": "ok"})
        )
        claude_call("hello", system_prompt="be helpful")
        cmd = mock_run.call_args[0][0]
        idx = cmd.index("--system-prompt")
        assert cmd[idx + 1] == "be helpful"

    @patch("claude_llm.subprocess.run")
    def test_json_schema_added(self, mock_run):
        mock_run.return_value = self._make_result(
            stdout=json.dumps({"result": "[]"})
        )
        schema = {"type": "array"}
        claude_call("hello", json_schema=schema)
        cmd = mock_run.call_args[0][0]
        idx = cmd.index("--json-schema")
        assert json.loads(cmd[idx + 1]) == schema

    @patch("claude_llm.subprocess.run")
    def test_timeout_passed(self, mock_run):
        mock_run.return_value = self._make_result(
            stdout=json.dumps({"result": "ok"})
        )
        claude_call("hello", timeout=300)
        assert mock_run.call_args[1]["timeout"] == 300


# ---------------------------------------------------------------------------
# claude_call — response parsing
# ---------------------------------------------------------------------------

class TestClaudeCallResponseParsing:
    """Test claude_call parses various response formats correctly."""

    def _make_result(self, stdout="", stderr="", returncode=0):
        r = MagicMock()
        r.stdout = stdout
        r.stderr = stderr
        r.returncode = returncode
        return r

    @patch("claude_llm.subprocess.run")
    def test_dict_response_with_result(self, mock_run):
        response = {"result": "hello world", "usage": {"input_tokens": 10, "output_tokens": 5}}
        mock_run.return_value = self._make_result(stdout=json.dumps(response))
        assert claude_call("test") == "hello world"

    @patch("claude_llm.subprocess.run")
    def test_dict_response_without_result_key(self, mock_run):
        """When dict has no 'result' key, falls back to raw stdout."""
        raw = json.dumps({"some_other_key": "value"})
        mock_run.return_value = self._make_result(stdout=raw)
        result = claude_call("test")
        assert result == raw

    @patch("claude_llm.subprocess.run")
    def test_list_response_message_format(self, mock_run):
        """List response with message content blocks is parsed correctly."""
        response = [
            {"content": [{"type": "text", "text": "generated content"}]}
        ]
        mock_run.return_value = self._make_result(stdout=json.dumps(response))
        assert claude_call("test") == "generated content"

    @patch("claude_llm.subprocess.run")
    def test_list_response_direct_blocks(self, mock_run):
        response = [
            {"type": "text", "text": "block1"},
            {"type": "text", "text": "block2"},
        ]
        mock_run.return_value = self._make_result(stdout=json.dumps(response))
        assert claude_call("test") == "block1\nblock2"

    @patch("claude_llm.subprocess.run")
    def test_non_json_fallback(self, mock_run):
        """Non-JSON output is returned as stripped text."""
        mock_run.return_value = self._make_result(stdout="  plain text output  ")
        assert claude_call("test") == "plain text output"

    @patch("claude_llm.subprocess.run")
    def test_non_zero_exit_raises(self, mock_run):
        mock_run.return_value = self._make_result(
            stdout="", stderr="model not found", returncode=1
        )
        with pytest.raises(RuntimeError, match="model not found"):
            claude_call("test")

    @patch("claude_llm.subprocess.run")
    def test_timeout_raises(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=10)
        with pytest.raises(subprocess.TimeoutExpired):
            claude_call("test", timeout=10)

    @patch("claude_llm._stream_claude")
    def test_verbose_delegates_to_stream(self, mock_stream):
        mock_stream.return_value = "streamed result"
        result = claude_call("test", verbose=True)
        assert result == "streamed result"
        mock_stream.assert_called_once()

    @patch("claude_llm._stream_claude")
    def test_module_verbose_flag(self, mock_stream):
        """VERBOSE module flag triggers stream mode."""
        import claude_llm
        original = claude_llm.VERBOSE
        try:
            claude_llm.VERBOSE = True
            mock_stream.return_value = "streamed"
            result = claude_call("test")
            assert result == "streamed"
        finally:
            claude_llm.VERBOSE = original

    @patch("claude_llm.subprocess.run")
    def test_json_string_scalar(self, mock_run):
        """JSON that parses to a bare string (not dict/list)."""
        mock_run.return_value = self._make_result(stdout='"just a string"')
        result = claude_call("test")
        assert result == "just a string"

    @patch("claude_llm.subprocess.run")
    def test_json_number_scalar(self, mock_run):
        """JSON that parses to a number."""
        mock_run.return_value = self._make_result(stdout="42")
        result = claude_call("test")
        assert result == "42"

    @patch("claude_llm.subprocess.run")
    def test_empty_stdout(self, mock_run):
        """Empty stdout with successful exit code."""
        mock_run.return_value = self._make_result(stdout="")
        result = claude_call("test")
        assert result == ""

    @patch("claude_llm.subprocess.run")
    def test_stderr_truncated_in_error(self, mock_run):
        """Long stderr is truncated to 500 chars in error message."""
        long_err = "x" * 1000
        mock_run.return_value = self._make_result(
            stdout="", stderr=long_err, returncode=1
        )
        with pytest.raises(RuntimeError) as exc_info:
            claude_call("test")
        assert len(str(exc_info.value)) <= 600  # 500 + prefix


# ---------------------------------------------------------------------------
# classify_batch
# ---------------------------------------------------------------------------

class TestClassifyBatch:
    """Test batch classification via Claude CLI."""

    @patch("claude_llm.claude_call")
    def test_successful_classification(self, mock_call):
        results = [
            {"index": 0, "category": "personal_mv", "reason": "official MV"},
            {"index": 1, "category": "concerts", "reason": "concert footage"},
        ]
        mock_call.return_value = json.dumps(results)

        items = [
            {"title": "MV Video", "description": "official", "duration": "4:00",
             "channel": "Official"},
            {"title": "Concert", "description": "live", "duration": "1:30:00",
             "channel": "Fan"},
        ]
        categories = ["personal_mv", "concerts"]
        result = classify_batch(
            items, categories, "Test Artist",
            system_prompt="Classify videos",
        )
        assert len(result) == 2
        assert result[0]["category"] == "personal_mv"
        assert result[1]["category"] == "concerts"

    @patch("claude_llm.claude_call")
    def test_empty_items(self, mock_call):
        mock_call.return_value = "[]"
        result = classify_batch([], ["mv"], "Artist", system_prompt="test")
        assert result == []

    @patch("claude_llm.claude_call")
    def test_non_list_response_returns_empty(self, mock_call):
        mock_call.return_value = json.dumps({"error": "unexpected"})
        result = classify_batch(
            [{"title": "t", "description": "", "duration": ""}],
            ["mv"], "Artist", system_prompt="test",
        )
        assert result == []

    @patch("claude_llm.claude_call")
    def test_exception_returns_empty(self, mock_call):
        mock_call.side_effect = RuntimeError("CLI error")
        result = classify_batch(
            [{"title": "t"}], ["mv"], "Artist", system_prompt="test",
        )
        assert result == []

    @patch("claude_llm.claude_call")
    def test_items_with_missing_fields(self, mock_call):
        """Items with missing optional fields don't crash."""
        mock_call.return_value = json.dumps([
            {"index": 0, "category": "mv", "reason": "test"},
        ])
        items = [{"title": "only title"}]
        result = classify_batch(items, ["mv"], "Artist", system_prompt="test")
        assert len(result) == 1

    @patch("claude_llm.claude_call")
    def test_discard_category_included(self, mock_call):
        """'discard' is always added to the category enum."""
        mock_call.return_value = "[]"
        classify_batch(
            [{"title": "t"}], ["mv", "concerts"], "Artist",
            system_prompt="test",
        )
        # The json_schema kwarg is already a dict (not a JSON string)
        schema = mock_call.call_args[1]["json_schema"]
        category_enum = schema["items"]["properties"]["category"]["enum"]
        assert "discard" in category_enum
        assert "mv" in category_enum
        assert "concerts" in category_enum

    @patch("claude_llm.claude_call")
    def test_already_parsed_list_response(self, mock_call):
        """If claude_call returns a list directly (already parsed), handle it."""
        results = [{"index": 0, "category": "mv", "reason": "ok"}]
        mock_call.return_value = results  # list, not string
        result = classify_batch(
            [{"title": "t"}], ["mv"], "Artist", system_prompt="test",
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# format_markdown
# ---------------------------------------------------------------------------

class TestFormatMarkdown:
    """Test markdown formatting via Claude CLI."""

    @patch("claude_llm.claude_call")
    def test_returns_formatted_text(self, mock_call):
        mock_call.return_value = "# Title\n\n- Item 1\n- Item 2"
        data = {
            "title": "Test",
            "description": "Test desc",
            "total_results": 2,
            "results": [{"title": "r1"}, {"title": "r2"}],
        }
        result = format_markdown(data, system_prompt="format nicely")
        assert "# Title" in result
        assert "Item 1" in result

    @patch("claude_llm.claude_call")
    def test_strips_markdown_fences(self, mock_call):
        mock_call.return_value = "```markdown\n# Title\n```"
        data = {
            "title": "Test",
            "description": "desc",
            "total_results": 1,
            "results": [{"title": "r1"}],
        }
        result = format_markdown(data, system_prompt="test")
        assert not result.startswith("```")
        assert "# Title" in result

    @patch("claude_llm.claude_call")
    def test_no_fences_passthrough(self, mock_call):
        mock_call.return_value = "# Clean output"
        data = {
            "title": "T",
            "description": "D",
            "total_results": 0,
            "results": [],
        }
        result = format_markdown(data, system_prompt="test")
        assert result == "# Clean output"


# ---------------------------------------------------------------------------
# _stream_claude (basic structure tests — no actual subprocess)
# ---------------------------------------------------------------------------

class TestStreamClaude:
    """Test the stream-json processing logic."""

    @patch("claude_llm.subprocess.Popen")
    def test_extracts_result_from_stream(self, mock_popen):
        """Verify result event is extracted from stream output."""
        proc = MagicMock()
        proc.returncode = 0
        proc.wait.return_value = None
        lines = [
            json.dumps({"type": "system", "model": "sonnet"}) + "\n",
            json.dumps({"type": "result", "result": "final answer", "usage": {}}) + "\n",
        ]
        proc.stdout = iter(lines)
        mock_popen.return_value = proc

        from claude_llm import _stream_claude
        result = _stream_claude(["claude", "-p", "test"], timeout=60)
        assert result == "final answer"

    @patch("claude_llm.subprocess.Popen")
    def test_non_zero_exit_raises(self, mock_popen):
        proc = MagicMock()
        proc.returncode = 1
        proc.wait.return_value = None
        proc.stdout = iter([])
        mock_popen.return_value = proc

        from claude_llm import _stream_claude
        with pytest.raises(RuntimeError, match="claude CLI error"):
            _stream_claude(["claude", "-p", "test"], timeout=60)

    @patch("claude_llm.subprocess.Popen")
    def test_timeout_kills_process(self, mock_popen):
        import subprocess
        proc = MagicMock()
        proc.stdout = iter([])
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=1)
        proc.communicate.return_value = ("", "")
        mock_popen.return_value = proc

        from claude_llm import _stream_claude
        with pytest.raises(subprocess.TimeoutExpired):
            _stream_claude(["claude", "-p", "test"], timeout=1)
        proc.kill.assert_called_once()

    @patch("claude_llm.subprocess.Popen")
    def test_invalid_json_lines_skipped(self, mock_popen):
        proc = MagicMock()
        proc.returncode = 0
        proc.wait.return_value = None
        lines = [
            "not json\n",
            "\n",
            json.dumps({"type": "result", "result": "ok"}) + "\n",
        ]
        proc.stdout = iter(lines)
        mock_popen.return_value = proc

        from claude_llm import _stream_claude
        result = _stream_claude(["claude", "-p", "test"], timeout=60)
        assert result == "ok"

    @patch("claude_llm.subprocess.Popen")
    def test_empty_output_returns_empty(self, mock_popen):
        proc = MagicMock()
        proc.returncode = 0
        proc.wait.return_value = None
        proc.stdout = iter([])
        mock_popen.return_value = proc

        from claude_llm import _stream_claude
        result = _stream_claude(["claude", "-p", "test"], timeout=60)
        assert result == ""

    @patch("claude_llm.subprocess.Popen")
    def test_includes_partial_messages_flag(self, mock_popen):
        proc = MagicMock()
        proc.returncode = 0
        proc.wait.return_value = None
        proc.stdout = iter([])
        mock_popen.return_value = proc

        from claude_llm import _stream_claude
        _stream_claude(["claude", "-p", "test"], timeout=60)
        cmd = mock_popen.call_args[0][0]
        assert "--include-partial-messages" in cmd
