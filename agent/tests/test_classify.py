"""Tests for agent/classify.py"""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.classify import _apply_exclusion, _apply_rules, _load_config, run_classify


class TestExclusionFilter:
    def setup_method(self):
        self.artist, _ = _load_config()

    def test_excludes_covers(self):
        items = [
            {"title": "田馥甄 你就不要想起我 翻唱 cover", "source": "youtube"},
            {"title": "田馥甄 Official MV", "source": "youtube"},
        ]
        kept, excluded = _apply_exclusion(items, self.artist)
        assert len(excluded) == 1
        assert len(kept) == 1
        assert "翻唱" in excluded[0]["title"]

    def test_excludes_tutorials(self):
        items = [
            {"title": "田馥甄 寂寞寂寞就好 吉他教学 tutorial", "source": "youtube"},
        ]
        kept, excluded = _apply_exclusion(items, self.artist)
        assert len(excluded) == 1

    def test_excludes_karaoke(self):
        items = [
            {"title": "田馥甄 卡拉OK 寂寞寂寞就好", "source": "youtube"},
        ]
        kept, excluded = _apply_exclusion(items, self.artist)
        assert len(excluded) == 1

    def test_keeps_normal(self):
        items = [
            {"title": "田馥甄 Official MV 寂寞寂寞就好", "source": "youtube"},
        ]
        kept, excluded = _apply_exclusion(items, self.artist)
        assert len(kept) == 1
        assert len(excluded) == 0


class TestWaterfallRules:
    def setup_method(self):
        self.artist, self.categories = _load_config()

    def test_she_mv(self):
        items = [
            {"title": "S.H.E [Super Star] Official MV", "channel": "華研國際", "source": "youtube", "duration_seconds": 245},
        ]
        classified, unmatched = _apply_rules(items, self.categories, self.artist)
        assert len(classified) == 1
        assert classified[0]["category"] == "sheMV"

    def test_personal_mv(self):
        items = [
            {"title": "田馥甄 [寂寞寂寞就好] Official MV", "channel": "華研國際", "source": "youtube", "duration_seconds": 280},
        ]
        classified, unmatched = _apply_rules(items, self.categories, self.artist)
        assert len(classified) == 1
        assert classified[0]["category"] == "personalMV"

    def test_concert_keywords(self):
        items = [
            {"title": "田馥甄 如果演唱会 2015 全场", "channel": "SomeChannel", "source": "youtube", "duration_seconds": 9000},
        ]
        classified, unmatched = _apply_rules(items, self.categories, self.artist)
        assert len(classified) == 1
        assert classified[0]["category"] == "concerts"

    def test_concert_long_duration(self):
        items = [
            {"title": "田馥甄 Live 2020", "channel": "SomeChannel", "source": "youtube", "duration_seconds": 3600},
        ]
        classified, unmatched = _apply_rules(items, self.categories, self.artist)
        assert len(classified) == 1
        assert classified[0]["category"] == "concerts"

    def test_interview(self):
        items = [
            {"title": "田馥甄 专访 2020 无人知晓", "channel": "ETtoday", "source": "youtube", "duration_seconds": 900},
        ]
        classified, unmatched = _apply_rules(items, self.categories, self.artist)
        assert len(classified) == 1
        assert classified[0]["category"] == "interviews"

    def test_variety(self):
        items = [
            {"title": "田馥甄 梦想的声音 演员", "channel": "浙江卫视", "source": "youtube", "duration_seconds": 500},
        ]
        classified, unmatched = _apply_rules(items, self.categories, self.artist)
        assert len(classified) == 1
        assert classified[0]["category"] == "variety"

    def test_collab_keyword(self):
        items = [
            {"title": "田馥甄 林宥嘉 给小孩 合唱", "channel": "SomeChannel", "source": "youtube", "duration_seconds": 270},
        ]
        classified, unmatched = _apply_rules(items, self.categories, self.artist)
        assert len(classified) == 1
        assert classified[0]["category"] == "collabs"

    def test_singles_ost(self):
        items = [
            {"title": "田馥甄 小幸运 我的少女时代 OST", "channel": "華研國際", "source": "youtube", "duration_seconds": 282},
        ]
        classified, unmatched = _apply_rules(items, self.categories, self.artist)
        assert len(classified) == 1
        # Could match personalMV (Official + MV) or singles (OST) - depends on title
        # This one has OST but also has Official channel, no MV keyword -> singles
        assert classified[0]["category"] == "singles"

    def test_priority_she_before_personal(self):
        """S.H.E MV should be classified as sheMV, not personalMV."""
        items = [
            {"title": "S.H.E [SHERO] Official MV", "channel": "華研國際", "source": "youtube", "duration_seconds": 240},
        ]
        classified, unmatched = _apply_rules(items, self.categories, self.artist)
        assert len(classified) == 1
        assert classified[0]["category"] == "sheMV"
