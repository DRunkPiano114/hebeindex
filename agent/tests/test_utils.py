"""Tests for agent/utils.py"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.utils import (
    parse_duration_to_seconds,
    normalize_title,
    extract_youtube_id,
    extract_bilibili_bvid,
    title_contains_any,
    title_contains_all,
)


class TestParseDuration:
    def test_mm_ss(self):
        assert parse_duration_to_seconds("4:35") == 275

    def test_m_ss(self):
        assert parse_duration_to_seconds("3:05") == 185

    def test_long_mm_ss(self):
        assert parse_duration_to_seconds("141:40") == 8500

    def test_h_mm_ss(self):
        assert parse_duration_to_seconds("1:30:00") == 5400

    def test_h_mm_ss_with_seconds(self):
        assert parse_duration_to_seconds("2:15:30") == 8130

    def test_empty(self):
        assert parse_duration_to_seconds("") == 0
        assert parse_duration_to_seconds(None) == 0

    def test_single_number(self):
        assert parse_duration_to_seconds("300") == 300

    def test_invalid(self):
        assert parse_duration_to_seconds("abc") == 0


class TestNormalizeTitle:
    def test_basic(self):
        assert normalize_title("Hello World!") == "hello world"

    def test_chinese(self):
        result = normalize_title("田馥甄 [你就不要想起我] Official MV")
        assert "田馥甄" in result
        assert "official" in result

    def test_extra_spaces(self):
        assert normalize_title("  hello   world  ") == "hello world"


class TestExtractYouTubeId:
    def test_standard_url(self):
        assert extract_youtube_id("https://www.youtube.com/watch?v=GsKbnsUN2RE") == "GsKbnsUN2RE"

    def test_short_url(self):
        assert extract_youtube_id("https://youtu.be/GsKbnsUN2RE") == "GsKbnsUN2RE"

    def test_with_params(self):
        assert extract_youtube_id("https://www.youtube.com/watch?v=ABC12345678&t=30") == "ABC12345678"

    def test_empty(self):
        assert extract_youtube_id("") is None
        assert extract_youtube_id(None) is None

    def test_invalid(self):
        assert extract_youtube_id("https://bilibili.com/video/BV123") is None


class TestExtractBilibiliBvid:
    def test_standard(self):
        assert extract_bilibili_bvid("https://www.bilibili.com/video/BV1xx411c7YKz") == "BV1xx411c7YK"

    def test_empty(self):
        assert extract_bilibili_bvid("") is None
        assert extract_bilibili_bvid(None) is None


class TestTitleContains:
    def test_contains_any(self):
        assert title_contains_any("田馥甄 Official MV", ["MV", "concert"])
        assert not title_contains_any("田馥甄 interview", ["MV", "concert"])

    def test_contains_all(self):
        assert title_contains_all("田馥甄 Official MV", ["田馥甄", "MV"])
        assert not title_contains_all("田馥甄 Official MV", ["田馥甄", "concert"])
