"""Tests for agent/dedup.py"""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.dedup import run_dedup, _strong_key_dedup, _fuzzy_dedup


FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class TestStrongKeyDedup:
    def test_removes_exact_youtube_duplicates(self):
        items = [
            {"title": "Video A", "url": "https://www.youtube.com/watch?v=ABC123", "source": "youtube", "video_id": "ABC123", "view_count": 100},
            {"title": "Video A copy", "url": "https://www.youtube.com/watch?v=ABC123", "source": "youtube", "video_id": "ABC123", "view_count": 200},
        ]
        result = _strong_key_dedup(items)
        assert len(result) == 1
        # Higher view count wins
        assert result[0]["view_count"] == 200

    def test_removes_exact_bilibili_duplicates(self):
        items = [
            {"title": "B站视频", "url": "https://www.bilibili.com/video/BV1234567890", "source": "bilibili", "bvid": "BV1234567890", "play_count": 100},
            {"title": "B站视频2", "url": "https://www.bilibili.com/video/BV1234567890", "source": "bilibili", "bvid": "BV1234567890", "play_count": 50},
        ]
        result = _strong_key_dedup(items)
        assert len(result) == 1

    def test_keeps_cross_platform(self):
        items = [
            {"title": "Same Video", "url": "https://www.youtube.com/watch?v=ABC123", "source": "youtube", "video_id": "ABC123"},
            {"title": "Same Video", "url": "https://www.bilibili.com/video/BV1234567890", "source": "bilibili", "bvid": "BV1234567890"},
        ]
        result = _strong_key_dedup(items)
        assert len(result) == 2  # Cross-platform kept

    def test_preserves_aliases(self):
        items = [
            {"title": "Official", "url": "https://www.youtube.com/watch?v=ABC123", "source": "youtube", "video_id": "ABC123", "channel": "華研國際", "view_count": 100},
            {"title": "Repost", "url": "https://www.youtube.com/watch?v=ABC123", "source": "youtube", "video_id": "ABC123", "channel": "Fan", "view_count": 50},
        ]
        result = _strong_key_dedup(items)
        assert len(result) == 1
        assert "aliases" in result[0]
        assert len(result[0]["aliases"]) >= 1


class TestFuzzyDedup:
    def test_merges_similar_titles_same_duration(self):
        items = [
            {"title": "田馥甄 寂寞寂寞就好 Official MV HD", "source": "youtube", "duration_seconds": 280, "view_count": 100},
            {"title": "田馥甄 寂寞寂寞就好 Official MV", "source": "youtube", "duration_seconds": 282, "view_count": 50},
        ]
        result = _fuzzy_dedup(items)
        assert len(result) == 1

    def test_keeps_different_titles(self):
        items = [
            {"title": "田馥甄 寂寞寂寞就好 MV", "source": "youtube", "duration_seconds": 280},
            {"title": "田馥甄 魔鬼中的天使 MV", "source": "youtube", "duration_seconds": 254},
        ]
        result = _fuzzy_dedup(items)
        assert len(result) == 2

    def test_keeps_different_durations(self):
        items = [
            {"title": "田馥甄 寂寞寂寞就好", "source": "youtube", "duration_seconds": 280},
            {"title": "田馥甄 寂寞寂寞就好 Live", "source": "youtube", "duration_seconds": 350},
        ]
        result = _fuzzy_dedup(items)
        assert len(result) == 2

    def test_cross_platform_kept(self):
        items = [
            {"title": "田馥甄 寂寞寂寞就好 MV", "source": "youtube", "duration_seconds": 280},
            {"title": "田馥甄 寂寞寂寞就好 MV", "source": "bilibili", "duration_seconds": 280},
        ]
        result = _fuzzy_dedup(items)
        assert len(result) == 2


class TestRunDedup:
    def test_full_pipeline(self):
        lake_path = os.path.join(FIXTURES_DIR, "sample_lake.json")
        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch DATA_DIR
            import agent.dedup as dedup_mod
            original_dir = dedup_mod.DATA_DIR
            dedup_mod.DATA_DIR = tmpdir

            try:
                output_path = run_dedup(lake_path)
                assert os.path.exists(output_path)

                with open(output_path) as f:
                    data = json.load(f)

                # Should have removed the YouTube duplicate (same video_id)
                assert data["output_count"] < data["input_count"]
            finally:
                dedup_mod.DATA_DIR = original_dir
