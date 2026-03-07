"""Tests for agent/output.py"""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.output import run_output, _to_content_item, _sort_key


class TestToContentItem:
    def test_basic_youtube(self):
        item = {
            "title": "Test Video",
            "url": "https://www.youtube.com/watch?v=ABC123",
            "source": "youtube",
            "verified": True,
            "view_count": 100,
            "channel": "TestChannel",
            "published_at": "2020-01-01",
            "duration": "4:30",
            "category": "personalMV",
            "classify_method": "rule",
        }
        result = _to_content_item(item)
        assert result["title"] == "Test Video"
        assert result["url"] == "https://www.youtube.com/watch?v=ABC123"
        assert result["source"] == "youtube"
        assert result["verified"] is True
        assert result["view_count"] == 100
        # Internal fields should NOT be present
        assert "category" not in result
        assert "classify_method" not in result

    def test_bilibili(self):
        item = {
            "title": "B站视频",
            "url": "https://www.bilibili.com/video/BV123",
            "source": "bilibili",
            "verified": None,
            "play_count": 500,
            "bvid": "BV123",
            "author": "UP主",
        }
        result = _to_content_item(item)
        assert result["verified"] is False  # None -> False
        assert result["bvid"] == "BV123"
        assert result["author"] == "UP主"


class TestSortKey:
    def test_official_first(self):
        official = {"channel": "華研國際", "view_count": 100}
        non_official = {"channel": "RandomFan", "view_count": 1000}
        assert _sort_key(official) < _sort_key(non_official)

    def test_higher_views_first(self):
        high = {"channel": "Fan1", "view_count": 1000}
        low = {"channel": "Fan2", "view_count": 100}
        assert _sort_key(high) < _sort_key(low)


class TestRunOutput:
    def test_full_pipeline(self):
        classified = {
            "phase": "classify",
            "created_at": "2026-03-07T00:00:00",
            "total_items": 3,
            "category_stats": {"personalMV": 1, "concerts": 1, "exclude": 1},
            "method_stats": {"rule": 3},
            "results": [
                {
                    "title": "MV Test",
                    "url": "https://www.youtube.com/watch?v=MV001",
                    "source": "youtube",
                    "verified": True,
                    "channel": "華研國際",
                    "view_count": 100,
                    "category": "personalMV",
                    "classify_method": "rule",
                },
                {
                    "title": "Concert Test",
                    "url": "https://www.youtube.com/watch?v=CON001",
                    "source": "youtube",
                    "verified": True,
                    "view_count": 50,
                    "category": "concerts",
                    "classify_method": "rule",
                },
                {
                    "title": "Excluded",
                    "url": "https://www.youtube.com/watch?v=EXC001",
                    "source": "youtube",
                    "verified": True,
                    "category": "exclude",
                    "classify_method": "rule",
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write classified data
            classified_path = os.path.join(tmpdir, "classified.json")
            with open(classified_path, "w") as f:
                json.dump(classified, f)

            # Patch PROCESSED_DIR
            import agent.output as output_mod
            original_dir = output_mod.PROCESSED_DIR
            output_mod.PROCESSED_DIR = tmpdir

            try:
                paths = run_output(classified_path)

                # Check file_2.json (personalMV)
                with open(os.path.join(tmpdir, "file_2.json")) as f:
                    data = json.load(f)
                assert data["file_id"] == 2
                assert data["total_results"] == 1
                assert data["results"][0]["title"] == "MV Test"
                # Verify internal fields stripped
                assert "category" not in data["results"][0]

                # Check file_4.json (concerts)
                with open(os.path.join(tmpdir, "file_4.json")) as f:
                    data = json.load(f)
                assert data["file_id"] == 4
                assert data["total_results"] == 1

            finally:
                output_mod.PROCESSED_DIR = original_dir
