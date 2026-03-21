"""
test_tools.py — collector/tools.py 的单元测试

覆盖范围：
- _parse_duration：ISO 8601 时长格式转换
- URLVerifier.verify：YouTube 快速通道、无效 URL、HTTP 检查（mock）
- URLVerifier._check：超时重试、405 fallback GET、普通成功/失败
- FileWriter.write：文件写入、自动创建目录
- BilibiliSearchTool._clean：HTML 标签剥离
- BilibiliSearchTool.search：成功响应、API 错误码、网络异常
- GoogleSearchTool.search：成功响应、HTTP 异常
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import httpx
import pytest

# 把 collector 目录加入 sys.path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import (
    _parse_duration,
    URLVerifier,
    FileWriter,
    BilibiliSearchTool,
    GoogleSearchTool,
)


# ---------------------------------------------------------------------------
# _parse_duration
# ---------------------------------------------------------------------------

class TestParseDuration:
    def test_empty_string(self):
        assert _parse_duration("") == ""

    def test_none_like_empty(self):
        # 边界：传入空串
        assert _parse_duration("") == ""

    def test_minutes_and_seconds(self):
        assert _parse_duration("PT4M35S") == "4:35"

    def test_seconds_only(self):
        assert _parse_duration("PT45S") == "0:45"

    def test_minutes_only(self):
        assert _parse_duration("PT3M") == "3:00"

    def test_hours_minutes_seconds(self):
        assert _parse_duration("PT1H23M45S") == "1:23:45"

    def test_hours_only(self):
        assert _parse_duration("PT2H") == "2:00:00"

    def test_hours_and_seconds_no_minutes(self):
        assert _parse_duration("PT1H5S") == "1:00:05"

    def test_invalid_format_returns_as_is(self):
        result = _parse_duration("INVALID")
        # 匹配失败时返回原始字符串
        assert result == "INVALID"

    def test_zero_seconds_padding(self):
        assert _parse_duration("PT10M9S") == "10:09"

    def test_large_values(self):
        assert _parse_duration("PT2H59M59S") == "2:59:59"


# ---------------------------------------------------------------------------
# URLVerifier
# ---------------------------------------------------------------------------

class TestURLVerifierYouTubeFastPath:
    """YouTube URL 应直接标记为 verified，不发 HTTP 请求。"""

    def setup_method(self):
        self.verifier = URLVerifier()

    def test_youtube_watch_url(self):
        url = "https://www.youtube.com/watch?v=abc123"
        result = self.verifier.verify([url])
        assert result[url]["valid"] is True
        assert result[url]["status"] == 200
        assert "YouTube" in result[url]["note"]

    def test_youtu_be_short_url(self):
        url = "https://youtu.be/abc123"
        result = self.verifier.verify([url])
        assert result[url]["valid"] is True

    def test_empty_url(self):
        result = self.verifier.verify([""])
        assert result[""]["valid"] is False
        assert result[""]["status"] == 0

    def test_non_http_url(self):
        url = "ftp://example.com/file"
        result = self.verifier.verify([url])
        assert result[url]["valid"] is False

    def test_multiple_mixed_urls(self):
        yt = "https://www.youtube.com/watch?v=xyz"
        invalid = "not-a-url"
        result = self.verifier.verify([yt, invalid])
        assert result[yt]["valid"] is True
        assert result[invalid]["valid"] is False

    def test_empty_list(self):
        result = self.verifier.verify([])
        assert result == {}


class TestURLVerifierHTTPCheck:
    """HTTP 检查路径（非 YouTube URL）。"""

    def setup_method(self):
        self.verifier = URLVerifier()

    def _make_response(self, status_code: int) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        return resp

    @patch("tools.httpx.Client")
    def test_bilibili_200_is_valid(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.head.return_value = self._make_response(200)
        mock_client_cls.return_value = mock_client

        url = "https://www.bilibili.com/video/BV1xx411c7mu"
        result = self.verifier.verify([url])
        assert result[url]["valid"] is True
        assert result[url]["status"] == 200

    @patch("tools.httpx.Client")
    def test_404_is_invalid(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.head.return_value = self._make_response(404)
        mock_client_cls.return_value = mock_client

        url = "https://example.com/missing"
        result = self.verifier.verify([url])
        assert result[url]["valid"] is False
        assert "404" in result[url]["note"]

    @patch("tools.httpx.Client")
    def test_405_falls_back_to_get(self, mock_client_cls):
        """HEAD 返回 405 时，应 fallback 用 GET 重试。"""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.head.return_value = self._make_response(405)
        mock_client.get.return_value = self._make_response(200)
        mock_client_cls.return_value = mock_client

        url = "https://example.com/page"
        result = self.verifier.verify([url])
        assert result[url]["valid"] is True
        mock_client.get.assert_called_once()

    @patch("tools.httpx.Client")
    def test_redirect_3xx_is_valid(self, mock_client_cls):
        for status in (301, 302, 307, 308):
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.head.return_value = self._make_response(status)
            mock_client_cls.return_value = mock_client

            url = f"https://example.com/redirect-{status}"
            result = self.verifier.verify([url])
            assert result[url]["valid"] is True, f"Expected {status} to be valid"

    @patch("tools.time.sleep")
    @patch("tools.httpx.Client")
    def test_timeout_retries_once(self, mock_client_cls, mock_sleep):
        """超时时最多重试 VERIFY_MAX_RETRIES 次。"""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.head.side_effect = httpx.TimeoutException("timed out")
        mock_client_cls.return_value = mock_client

        url = "https://slow.example.com"
        result = self.verifier.verify([url])
        assert result[url]["valid"] is False
        assert result[url]["note"] == "timeout"
        # VERIFY_MAX_RETRIES=1 → 重试1次，共2次调用
        assert mock_client.head.call_count == 2

    @patch("tools.httpx.Client")
    def test_generic_exception_returns_error_note(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.head.side_effect = Exception("connection refused")
        mock_client_cls.return_value = mock_client

        url = "https://down.example.com"
        result = self.verifier.verify([url])
        assert result[url]["valid"] is False
        assert "connection refused" in result[url]["note"]

    @patch("tools.httpx.Client")
    def test_batch_chunking_50(self, mock_client_cls):
        """verify() 内部只对非 YouTube URL 调用 _check，本测试直接从公开接口验证计数。"""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.head.return_value = self._make_response(200)
        mock_client_cls.return_value = mock_client

        urls = [f"https://example.com/{i}" for i in range(5)]
        result = self.verifier.verify(urls)
        assert len(result) == 5
        for url in urls:
            assert result[url]["valid"] is True


# ---------------------------------------------------------------------------
# FileWriter
# ---------------------------------------------------------------------------

class TestFileWriter:
    def test_write_creates_file(self, tmp_path):
        writer = FileWriter(str(tmp_path))
        result = writer.write("test.md", "# Hello")
        target = tmp_path / "test.md"
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "# Hello"
        assert "OK:" in result

    def test_write_nested_path_creates_dirs(self, tmp_path):
        writer = FileWriter(str(tmp_path))
        writer.write("subdir/deep/file.md", "content")
        assert (tmp_path / "subdir" / "deep" / "file.md").exists()

    def test_write_utf8_chinese(self, tmp_path):
        writer = FileWriter(str(tmp_path))
        content = "田馥甄 Hebe Tien 🎵"
        writer.write("中文.md", content)
        assert (tmp_path / "中文.md").read_text(encoding="utf-8") == content

    def test_write_overwrites_existing(self, tmp_path):
        writer = FileWriter(str(tmp_path))
        writer.write("file.md", "old content")
        writer.write("file.md", "new content")
        assert (tmp_path / "file.md").read_text(encoding="utf-8") == "new content"

    def test_constructor_creates_output_subdirs(self, tmp_path):
        """FileWriter 构造函数应预创建指定的 subdirs。"""
        subdirs = ["mv", "concerts", "shows"]
        writer = FileWriter(str(tmp_path), subdirs=subdirs)
        for sub in subdirs:
            assert (tmp_path / sub).is_dir(), f"Expected subdir '{sub}' to exist"

    def test_write_returns_full_path_in_message(self, tmp_path):
        writer = FileWriter(str(tmp_path))
        result = writer.write("readme.md", "# README")
        assert str(tmp_path) in result


# ---------------------------------------------------------------------------
# BilibiliSearchTool._clean
# ---------------------------------------------------------------------------

class TestBilibiliClean:
    def setup_method(self):
        self.tool = BilibiliSearchTool.__new__(BilibiliSearchTool)

    def test_strips_em_tags(self):
        assert self.tool._clean("<em>田馥甄</em>") == "田馥甄"

    def test_strips_multiple_tags(self):
        assert self.tool._clean("<em>A</em> <b>B</b>") == "A B"

    def test_no_tags_unchanged(self):
        assert self.tool._clean("田馥甄 Hebe") == "田馥甄 Hebe"

    def test_strips_leading_trailing_whitespace(self):
        assert self.tool._clean("  hello  ") == "hello"

    def test_empty_string(self):
        assert self.tool._clean("") == ""

    def test_nested_tags(self):
        assert self.tool._clean("<span><em>Hebe</em></span>") == "Hebe"


# ---------------------------------------------------------------------------
# BilibiliSearchTool.search (mocked HTTP)
# ---------------------------------------------------------------------------

class TestBilibiliSearch:
    def setup_method(self):
        self.tool = BilibiliSearchTool()

    def _mock_response(self, data: dict, status_code: int = 200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = data
        resp.raise_for_status = MagicMock()
        return resp

    def _success_payload(self, items: list) -> dict:
        return {"code": 0, "data": {"result": items}}

    def _make_item(self, bvid="BV1xx411c7mu", title="<em>田馥甄</em> MV",
                   pubdate=1609459200, play=100000, author="官方", desc="简介"):
        return {
            "bvid": bvid,
            "title": title,
            "pubdate": pubdate,
            "play": play,
            "author": author,
            "description": desc,
            "duration": "4:35",
        }

    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_successful_search_returns_list(self, mock_rl):
        item = self._make_item()
        self.tool._session.get = MagicMock(
            return_value=self._mock_response(self._success_payload([item]))
        )
        results = self.tool.search("田馥甄")
        assert len(results) == 1
        assert results[0]["bvid"] == "BV1xx411c7mu"
        assert results[0]["url"] == "https://www.bilibili.com/video/BV1xx411c7mu"
        assert results[0]["verified"] is None

    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_html_tags_stripped_from_title(self, mock_rl):
        item = self._make_item(title="<em>田馥甄</em> 小幸运")
        self.tool._session.get = MagicMock(
            return_value=self._mock_response(self._success_payload([item]))
        )
        results = self.tool.search("田馥甄")
        assert results[0]["title"] == "田馥甄 小幸运"

    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_pubdate_converted_to_date_string(self, mock_rl):
        item = self._make_item(pubdate=1609459200)  # 2021-01-01 UTC+8
        self.tool._session.get = MagicMock(
            return_value=self._mock_response(self._success_payload([item]))
        )
        results = self.tool.search("田馥甄")
        # 只检查格式 YYYY-MM-DD，不强制具体日期（时区差异）
        assert len(results[0]["published_at"]) == 10
        assert results[0]["published_at"][4] == "-"

    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_zero_pubdate_gives_empty_string(self, mock_rl):
        item = self._make_item(pubdate=0)
        self.tool._session.get = MagicMock(
            return_value=self._mock_response(self._success_payload([item]))
        )
        results = self.tool.search("田馥甄")
        assert results[0]["published_at"] == ""

    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_items_without_bvid_are_skipped(self, mock_rl):
        items = [
            self._make_item(bvid="BV1good"),
            {"title": "no bvid", "pubdate": 0, "play": 0, "author": "", "description": ""},
        ]
        self.tool._session.get = MagicMock(
            return_value=self._mock_response(self._success_payload(items))
        )
        results = self.tool.search("田馥甄")
        assert len(results) == 1
        assert results[0]["bvid"] == "BV1good"

    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_api_error_code_returns_empty(self, mock_rl):
        payload = {"code": -403, "message": "access denied", "data": {}}
        self.tool._session.get = MagicMock(
            return_value=self._mock_response(payload)
        )
        results = self.tool.search("田馥甄")
        assert results == []

    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_network_exception_returns_empty(self, mock_rl):
        self.tool._session.get = MagicMock(side_effect=Exception("network error"))
        results = self.tool.search("田馥甄")
        assert results == []

    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_description_truncated_to_250(self, mock_rl):
        long_desc = "A" * 300
        item = self._make_item(desc=long_desc)
        self.tool._session.get = MagicMock(
            return_value=self._mock_response(self._success_payload([item]))
        )
        results = self.tool.search("田馥甄")
        assert len(results[0]["description"]) <= 250


# ---------------------------------------------------------------------------
# Bilibili 412 / SPI cookie tests
# ---------------------------------------------------------------------------

class TestBilibili412AndSPI:
    """Tests for HTTP 412 retry logic and SPI cookie initialization."""

    def setup_method(self):
        self.tool = BilibiliSearchTool()

    def _make_http_response(self, status_code: int, json_data: dict | None = None):
        resp = MagicMock()
        resp.status_code = status_code
        if json_data is not None:
            resp.json.return_value = json_data
        return resp

    def _success_payload(self, items: list) -> dict:
        return {"code": 0, "data": {"result": items}}

    def _make_item(self, bvid="BV1xx411c7mu"):
        return {
            "bvid": bvid, "title": "test", "pubdate": 1609459200,
            "play": 100, "author": "author", "description": "desc",
            "duration": "3:00",
        }

    @patch("tools.time.sleep")
    @patch.object(BilibiliSearchTool, "_init_cookies")
    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_412_triggers_cookie_refresh_and_retry(self, mock_rl, mock_init, mock_sleep):
        """412 on first call should refresh cookies and retry once."""
        success_data = self._success_payload([self._make_item()])
        self.tool._session.get = MagicMock(side_effect=[
            self._make_http_response(412),
            self._make_http_response(200, success_data),
        ])
        results = self.tool.search("田馥甄")
        assert len(results) == 1
        mock_init.assert_called_once()

    @patch("tools.time.sleep")
    @patch.object(BilibiliSearchTool, "_init_cookies")
    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_412_on_retry_returns_empty(self, mock_rl, mock_init, mock_sleep):
        """412 with retry=False should return [] without infinite loop."""
        self.tool._session.get = MagicMock(
            return_value=self._make_http_response(412)
        )
        results = self.tool._do_search("田馥甄", page=1, retry=False)
        assert results == []
        mock_init.assert_not_called()

    @patch("tools.time.sleep")
    @patch.object(BilibiliSearchTool, "_init_cookies")
    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_412_then_success_returns_results(self, mock_rl, mock_init, mock_sleep):
        """End-to-end: 412 -> refresh -> success with video data."""
        item = self._make_item(bvid="BV1abc")
        success_data = self._success_payload([item])
        self.tool._session.get = MagicMock(side_effect=[
            self._make_http_response(412),
            self._make_http_response(200, success_data),
        ])
        results = self.tool.search("田馥甄")
        assert len(results) == 1
        assert results[0]["bvid"] == "BV1abc"
        mock_sleep.assert_called_with(3)

    @patch("tools.time.sleep")
    @patch.object(BilibiliSearchTool, "_init_cookies")
    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_neg352_still_triggers_retry(self, mock_rl, mock_init, mock_sleep):
        """Existing -352 code path should still work after refactor."""
        neg352_data = {"code": -352, "message": "risk control"}
        success_data = self._success_payload([self._make_item()])
        self.tool._session.get = MagicMock(side_effect=[
            self._make_http_response(200, neg352_data),
            self._make_http_response(200, success_data),
        ])
        results = self.tool.search("田馥甄")
        assert len(results) == 1
        mock_init.assert_called_once()

    @patch.object(BilibiliSearchTool, "_rate_limit")
    def test_non_200_non_412_returns_empty(self, mock_rl):
        """HTTP 403 should return [] without retry."""
        self.tool._session.get = MagicMock(
            return_value=self._make_http_response(403)
        )
        results = self.tool.search("田馥甄")
        assert results == []

    def test_init_cookies_calls_spi_endpoint(self):
        """SPI endpoint should be called and buvid3/buvid4 set on session."""
        spi_data = {
            "code": 0,
            "data": {"b_3": "buvid3-value", "b_4": "buvid4-value"},
        }
        homepage_resp = MagicMock()
        homepage_resp.status_code = 200
        spi_resp = MagicMock()
        spi_resp.status_code = 200
        spi_resp.json.return_value = spi_data

        self.tool._session.get = MagicMock(side_effect=[homepage_resp, spi_resp])
        self.tool._init_cookies()

        assert self.tool._session.cookies.get("buvid3", domain=".bilibili.com") == "buvid3-value"
        assert self.tool._session.cookies.get("buvid4", domain=".bilibili.com") == "buvid4-value"

    def test_init_cookies_handles_spi_failure(self):
        """SPI returning error code should not crash."""
        homepage_resp = MagicMock()
        homepage_resp.status_code = 200
        spi_resp = MagicMock()
        spi_resp.status_code = 500

        self.tool._session.get = MagicMock(side_effect=[homepage_resp, spi_resp])
        self.tool._init_cookies()
        # Should not raise; cookies may not have buvid3/buvid4 but that's OK


# ---------------------------------------------------------------------------
# GoogleSearchTool.search (mocked HTTP)
# ---------------------------------------------------------------------------

class TestGoogleSearch:
    def setup_method(self):
        self.tool = GoogleSearchTool("fake-serper-key")

    def _mock_response(self, data: dict, status: int = 200):
        resp = MagicMock()
        resp.json.return_value = data
        resp.status_code = status
        resp.raise_for_status = MagicMock()
        if status >= 400:
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error", request=MagicMock(), response=resp
            )
        return resp

    @patch("tools.httpx.post")
    @patch.object(GoogleSearchTool, "_rate_limit")
    def test_successful_search(self, mock_rl, mock_post):
        payload = {
            "organic": [
                {"title": "田馥甄官网", "link": "https://hebe.com", "snippet": "...", "date": "2024-01-01"},
                {"title": "田馥甄 Bilibili", "link": "https://bilibili.com/hebe", "snippet": "...", "date": ""},
            ]
        }
        mock_post.return_value = self._mock_response(payload)

        results = self.tool.search("田馥甄")
        assert len(results) == 2
        assert results[0]["title"] == "田馥甄官网"
        assert results[0]["url"] == "https://hebe.com"
        assert results[0]["verified"] is None

    @patch("tools.httpx.post")
    @patch.object(GoogleSearchTool, "_rate_limit")
    def test_empty_organic_returns_empty_list(self, mock_rl, mock_post):
        mock_post.return_value = self._mock_response({"organic": []})
        results = self.tool.search("no results")
        assert results == []

    @patch("tools.httpx.post")
    @patch.object(GoogleSearchTool, "_rate_limit")
    def test_missing_organic_key_returns_empty(self, mock_rl, mock_post):
        mock_post.return_value = self._mock_response({})
        results = self.tool.search("田馥甄")
        assert results == []

    @patch("tools.httpx.post")
    @patch.object(GoogleSearchTool, "_rate_limit")
    def test_http_error_returns_empty(self, mock_rl, mock_post):
        mock_post.side_effect = Exception("API unreachable")
        results = self.tool.search("田馥甄")
        assert results == []

    @patch("tools.httpx.post")
    @patch.object(GoogleSearchTool, "_rate_limit")
    def test_num_capped_at_10(self, mock_rl, mock_post):
        mock_post.return_value = self._mock_response({"organic": []})
        self.tool.search("田馥甄", num=50)
        call_kwargs = mock_post.call_args
        sent_payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        assert sent_payload["num"] <= 10

    @patch("tools.httpx.post")
    @patch.object(GoogleSearchTool, "_rate_limit")
    def test_sends_correct_headers(self, mock_rl, mock_post):
        mock_post.return_value = self._mock_response({"organic": []})
        self.tool.search("田馥甄")
        headers = mock_post.call_args[1]["headers"]
        assert headers["X-API-KEY"] == "fake-serper-key"
        assert headers["Content-Type"] == "application/json"
