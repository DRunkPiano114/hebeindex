"""
test_review.py — Tests for confidence scoring (reclassify.py) and review mode (review.py).

Coverage:
- ConfidenceScorer: all signal methods, overall scoring, edge cases
- review.py: state management, item loading, display formatting, review loop
"""

import json
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest

# Add collector directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from reclassify import (
    ConfidenceScorer,
    RuleClassifier,
    STRONG_RULE_REASONS,
    MEDIUM_RULE_REASONS,
    DURATION_RANGES,
    load_artist_data,
)
from review import (
    load_items,
    load_review_state,
    save_review_state,
    apply_review_results,
    run_review,
    display_item,
    display_summary,
    _format_views,
    _truncate,
    _confidence_bar,
    _item_key,
    REVIEW_STATE_FILENAME,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def artist_data():
    """Minimal artist data for testing."""
    return {
        "artist": {
            "names": {
                "primary": "田馥甄",
                "english": "Hebe Tien",
                "aliases": ["Hebe", "馥甄"],
            },
            "official_channels": ["華研國際", "HIM International Music"],
            "labels": ["華研國際"],
        },
        "group": {
            "name": "S.H.E",
            "aliases": ["SHE"],
            "members": ["Selina/任家萱", "Hebe/田馥甄", "Ella/陳嘉樺"],
            "member_names": ["任家萱", "Selina", "陳嘉樺", "Ella"],
        },
        "discography": {
            "solo_albums": [
                {"name": "To Hebe", "year": 2010, "tracks": ["寂寞寂寞就好", "LOVE!", "你就不要想起我"]},
            ],
            "ost_singles": [
                {"name": "小幸運", "source": "我的少女時代", "year": 2015},
            ],
            "variety_show_singles": [],
            "concerts": [
                {"name": "如果plus", "years": "2016-2017", "aliases": ["如果PLUS"]},
            ],
            "she_concerts": [],
            "variety_shows": [
                {"name": "夢想的聲音", "network": "浙江卫视"},
            ],
            "collaborators": [
                {"name": "五月天", "aliases": ["Mayday"], "songs": ["知足"]},
            ],
            "she_mvs": ["戀人未滿", "Super Star"],
            "western_artist_blacklist": ["taylor swift"],
            "other_chinese_artist_blacklist": [],
            "wrong_context_patterns": [],
        },
        "categories": [
            {"id": 2, "key": "personal_mv", "label": "個人MV"},
            {"id": 4, "key": "concerts", "label": "演唱會"},
        ],
        "classification": {"priority": ["personal_mv"]},
    }


@pytest.fixture
def classifier(artist_data):
    return RuleClassifier(artist_data)


@pytest.fixture
def scorer(classifier):
    return ConfidenceScorer(classifier)


@pytest.fixture
def sample_item():
    """A typical classified item."""
    return {
        "title": "HEBE TIEN 田馥甄 [你就不要想起我] Official MV HD",
        "url": "https://www.youtube.com/watch?v=GsKbnsUN2RE",
        "channel": "華研國際",
        "source": "youtube",
        "duration": "5:18",
        "view_count": 100_000_000,
        "verified": True,
        "category": "personal_mv",
        "classification_reason": "rule1_official_mv",
    }


@pytest.fixture
def low_confidence_item():
    """An item with weak signals."""
    return {
        "title": "Some random video mentioning Hebe",
        "url": "https://www.youtube.com/watch?v=FAKE123",
        "channel": "RandomUser",
        "source": "youtube",
        "duration": "15:30",
        "view_count": 500,
        "verified": True,
        "category": "personal_mv",
        "classification_reason": "llm_unclear",
    }


@pytest.fixture
def processed_dir(tmp_path):
    """Create a temporary processed directory with test data."""
    pdir = tmp_path / "processed"
    pdir.mkdir()

    # file_2.json with items at varying confidence levels
    data = {
        "file_id": 2,
        "output_path": "MV/个人MV.md",
        "title": "Test MV list",
        "description": "Test",
        "processed_at": "2026-01-01T00:00:00",
        "total_results": 3,
        "results": [
            {
                "title": "High confidence MV",
                "url": "https://youtube.com/watch?v=HIGH",
                "channel": "華研國際",
                "source": "youtube",
                "duration": "4:00",
                "view_count": 50_000_000,
                "verified": True,
                "category": "personal_mv",
                "classification_reason": "rule1_official_mv",
                "confidence": 0.95,
                "confidence_signals": {"rule_strength": 1.0, "source_reliability": 1.0},
            },
            {
                "title": "Medium confidence MV",
                "url": "https://youtube.com/watch?v=MED",
                "channel": "SomeChannel",
                "source": "youtube",
                "duration": "4:30",
                "view_count": 5000,
                "verified": True,
                "category": "personal_mv",
                "classification_reason": "llm_mv",
                "confidence": 0.55,
                "confidence_signals": {"rule_strength": 0.5, "source_reliability": 0.5},
            },
            {
                "title": "Low confidence MV",
                "url": "https://youtube.com/watch?v=LOW",
                "channel": "Unknown",
                "source": "youtube",
                "duration": "12:00",
                "view_count": 100,
                "verified": False,
                "category": "personal_mv",
                "classification_reason": "llm_maybe",
                "confidence": 0.3,
                "confidence_signals": {"rule_strength": 0.5, "source_reliability": 0.3},
            },
        ],
    }
    with open(pdir / "file_2.json", "w") as f:
        json.dump(data, f)

    return pdir


# ──────────────────────────────────────────────────────────────────────
# ConfidenceScorer tests
# ──────────────────────────────────────────────────────────────────────

class TestConfidenceScorer:
    """Tests for the multi-signal confidence scoring system."""

    def test_strong_rule_returns_high_rule_strength(self, scorer):
        name, val = scorer.signal_rule_strength("rule1_official_mv")
        assert name == "rule_strength"
        assert val == 1.0

    def test_medium_rule_returns_medium_rule_strength(self, scorer):
        name, val = scorer.signal_rule_strength("rule1_known_track_broad")
        assert name == "rule_strength"
        assert val == 0.7

    def test_llm_reason_returns_lower_rule_strength(self, scorer):
        name, val = scorer.signal_rule_strength("llm_some_reason")
        assert name == "rule_strength"
        assert val == 0.5

    def test_no_match_returns_zero_rule_strength(self, scorer):
        name, val = scorer.signal_rule_strength("no_rule_match")
        assert name == "rule_strength"
        assert val == 0.0

    def test_unknown_rule_returns_medium(self, scorer):
        name, val = scorer.signal_rule_strength("some_unknown_rule")
        assert name == "rule_strength"
        assert val == 0.6

    def test_official_channel_high_reliability(self, scorer):
        item = {"channel": "華研國際", "source": "youtube", "verified": True}
        name, val = scorer.signal_source_reliability(item)
        assert name == "source_reliability"
        assert val == 1.0

    def test_topic_channel_high_reliability(self, scorer):
        item = {"channel": "Hebe Tien - Topic", "source": "youtube", "verified": True}
        name, val = scorer.signal_source_reliability(item)
        assert val == 0.85

    def test_unverified_low_reliability(self, scorer):
        item = {"channel": "Random", "source": "youtube", "verified": False}
        name, val = scorer.signal_source_reliability(item)
        assert val == 0.3

    def test_label_channel_high_reliability(self, scorer):
        item = {"channel": "華研國際", "source": "youtube", "verified": True}
        name, val = scorer.signal_source_reliability(item)
        assert val == 1.0

    def test_duration_ideal_range(self, scorer):
        item = {"duration": "4:00"}  # 240 seconds, ideal for MV
        name, val = scorer.signal_duration_fit(item, "personal_mv")
        assert val == 1.0

    def test_duration_acceptable_range(self, scorer):
        item = {"duration": "7:30"}  # 450 seconds, acceptable for MV
        name, val = scorer.signal_duration_fit(item, "personal_mv")
        assert 0.6 <= val <= 1.0

    def test_duration_outside_range(self, scorer):
        item = {"duration": "1:30:00"}  # 90 min, too long for MV
        name, val = scorer.signal_duration_fit(item, "personal_mv")
        assert val == 0.2

    def test_duration_missing(self, scorer):
        item = {}
        name, val = scorer.signal_duration_fit(item, "personal_mv")
        assert val == 0.5  # neutral

    def test_duration_unknown_category(self, scorer):
        item = {"duration": "4:00"}
        name, val = scorer.signal_duration_fit(item, "unknown_cat")
        assert val == 0.5

    def test_high_views_high_score(self, scorer):
        item = {"view_count": 10_000_000}
        name, val = scorer.signal_view_count(item)
        assert val == 1.0

    def test_medium_views(self, scorer):
        item = {"view_count": 50_000}
        name, val = scorer.signal_view_count(item)
        assert val == 0.7

    def test_zero_views(self, scorer):
        item = {"view_count": 0}
        name, val = scorer.signal_view_count(item)
        assert val == 0.4

    def test_no_views_field(self, scorer):
        item = {}
        name, val = scorer.signal_view_count(item)
        assert val == 0.4

    def test_bilibili_play_count(self, scorer):
        item = {"play_count": 500_000}
        name, val = scorer.signal_view_count(item)
        assert val == 0.85

    def test_title_match_official_mv(self, scorer):
        item = {"title": "田馥甄 Official MV"}
        name, val = scorer.signal_title_keyword_match(item, "personal_mv")
        assert val == 1.0

    def test_title_match_mv_keyword(self, scorer):
        item = {"title": "Some song MV"}
        name, val = scorer.signal_title_keyword_match(item, "personal_mv")
        assert val == 0.8

    def test_title_match_known_track(self, scorer):
        item = {"title": "寂寞寂寞就好 audio"}
        name, val = scorer.signal_title_keyword_match(item, "personal_mv")
        assert val == 0.6

    def test_title_match_weak(self, scorer):
        item = {"title": "random video title"}
        name, val = scorer.signal_title_keyword_match(item, "personal_mv")
        assert val == 0.3

    def test_title_match_concert(self, scorer):
        item = {"title": "田馥甄 演唱会"}
        name, val = scorer.signal_title_keyword_match(item, "concerts")
        assert val == 1.0

    def test_title_match_interview(self, scorer):
        item = {"title": "田馥甄 专访"}
        name, val = scorer.signal_title_keyword_match(item, "interviews")
        assert val == 1.0

    def test_overall_score_high_confidence(self, scorer, sample_item):
        confidence, signals = scorer.score(sample_item, "personal_mv", "rule1_official_mv")
        assert confidence >= 0.8
        assert "rule_strength" in signals
        assert "source_reliability" in signals
        assert "duration_fit" in signals
        assert "view_count" in signals
        assert "title_match" in signals

    def test_overall_score_low_confidence(self, scorer, low_confidence_item):
        confidence, signals = scorer.score(
            low_confidence_item, "personal_mv", "llm_unclear"
        )
        assert confidence < 0.7
        assert len(signals) == 5

    def test_overall_score_discard(self, scorer):
        item = {"title": "taylor swift concert"}
        confidence, signals = scorer.score(item, "discard", "rule0_western_blacklist")
        assert confidence == 1.0
        assert signals == {"rule_strength": 1.0}

    def test_score_bounded_0_to_1(self, scorer):
        """Confidence should always be between 0.0 and 1.0."""
        items = [
            {"title": "", "channel": "", "source": "", "duration": "", "view_count": 0},
            {"title": "田馥甄 Official MV", "channel": "華研國際", "source": "youtube",
             "duration": "4:00", "view_count": 100_000_000, "verified": True},
        ]
        for item in items:
            for cat in ["personal_mv", "concerts", "variety", "interviews"]:
                for reason in ["rule1_official_mv", "llm_test", "no_rule_match"]:
                    conf, _ = scorer.score(item, cat, reason)
                    assert 0.0 <= conf <= 1.0, f"Out of bounds: {conf}"


class TestConfidenceReasonsCompleteness:
    """Ensure all rule reasons are categorized as strong or medium."""

    def test_all_strong_reasons_are_valid(self):
        for reason in STRONG_RULE_REASONS:
            assert reason.startswith("rule"), f"Strong reason should start with 'rule': {reason}"

    def test_all_medium_reasons_are_valid(self):
        for reason in MEDIUM_RULE_REASONS:
            assert reason.startswith("rule"), f"Medium reason should start with 'rule': {reason}"

    def test_no_overlap(self):
        overlap = STRONG_RULE_REASONS & MEDIUM_RULE_REASONS
        assert not overlap, f"Reasons in both strong and medium: {overlap}"


class TestDurationRanges:
    """Test that duration ranges are sensible."""

    def test_ranges_have_correct_order(self):
        for cat, (lo, ideal_lo, ideal_hi, hi) in DURATION_RANGES.items():
            assert lo <= ideal_lo <= ideal_hi <= hi, f"Bad range for {cat}: {lo}, {ideal_lo}, {ideal_hi}, {hi}"

    def test_all_main_categories_have_ranges(self):
        expected = {"personal_mv", "group_mv", "ost_singles", "collabs", "concerts", "variety", "interviews"}
        assert expected == set(DURATION_RANGES.keys())


# ──────────────────────────────────────────────────────────────────────
# Review module tests
# ──────────────────────────────────────────────────────────────────────

class TestReviewHelpers:
    """Test display helper functions."""

    def test_format_views_millions(self):
        assert _format_views(5_500_000) == "5.5M"

    def test_format_views_thousands(self):
        assert _format_views(42_000) == "42.0K"

    def test_format_views_small(self):
        assert _format_views(500) == "500"

    def test_format_views_none(self):
        assert _format_views(None) == "N/A"

    def test_format_views_zero(self):
        assert _format_views(0) == "N/A"

    def test_truncate_short(self):
        assert _truncate("hello", 10) == "hello"

    def test_truncate_long(self):
        result = _truncate("a" * 100, 20)
        assert len(result) == 20
        assert result.endswith("...")

    def test_confidence_bar(self):
        bar = _confidence_bar(0.75, width=10)
        assert "0.750" in bar
        assert "#" in bar
        assert "-" in bar

    def test_item_key(self):
        item = {"url": "https://youtube.com/watch?v=ABC"}
        assert _item_key(item) == "https://youtube.com/watch?v=ABC"

    def test_item_key_missing_url(self):
        item = {"title": "test"}
        assert _item_key(item) == ""


class TestReviewStateManagement:
    """Test review state persistence."""

    def test_load_empty_state(self, tmp_path):
        state = load_review_state(tmp_path)
        assert state == {"reviewed": {}, "session_start": None}

    def test_save_and_load_state(self, tmp_path):
        state = {
            "reviewed": {"https://example.com/1": "approve", "https://example.com/2": "reject"},
            "session_start": "2026-01-01T00:00:00",
        }
        save_review_state(tmp_path, state)
        loaded = load_review_state(tmp_path)
        assert loaded == state

    def test_state_file_location(self, tmp_path):
        state = {"reviewed": {}, "session_start": "2026-01-01T00:00:00"}
        save_review_state(tmp_path, state)
        assert (tmp_path / REVIEW_STATE_FILENAME).exists()


class TestLoadItems:
    """Test loading and filtering items for review."""

    def test_load_below_threshold(self, processed_dir):
        items = load_items(processed_dir, threshold=0.7)
        # Should get 2 items: medium (0.55) and low (0.3)
        assert len(items) == 2

    def test_load_sorted_by_confidence(self, processed_dir):
        items = load_items(processed_dir, threshold=0.7)
        confidences = [item.get("confidence", 0) for item in items]
        assert confidences == sorted(confidences)

    def test_load_with_strict_threshold(self, processed_dir):
        items = load_items(processed_dir, threshold=0.4)
        # Only the 0.3 item
        assert len(items) == 1

    def test_load_with_high_threshold(self, processed_dir):
        items = load_items(processed_dir, threshold=1.0)
        # All items (0.95, 0.55, 0.3) are below 1.0
        assert len(items) == 3

    def test_load_with_category_filter(self, processed_dir):
        items = load_items(processed_dir, threshold=0.7, category_filter="personal_mv")
        assert len(items) == 2

    def test_load_with_wrong_category_filter(self, processed_dir):
        items = load_items(processed_dir, threshold=0.7, category_filter="concerts")
        assert len(items) == 0

    def test_load_missing_directory(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        items = load_items(empty_dir, threshold=0.7)
        assert len(items) == 0


class TestDisplayItem:
    """Test display functions (ensure they don't crash)."""

    def test_display_item_no_crash(self, capsys, sample_item):
        """display_item should print without error."""
        sample_item["confidence"] = 0.85
        sample_item["confidence_signals"] = {"rule_strength": 1.0, "source_reliability": 1.0}
        display_item(sample_item, 0, 10)
        captured = capsys.readouterr()
        assert "Item 1 of 10" in captured.out
        assert "0.850" in captured.out

    def test_display_item_missing_fields(self, capsys):
        """display_item handles missing fields gracefully."""
        item = {"url": "http://example.com", "confidence": 0.5}
        display_item(item, 0, 1)
        captured = capsys.readouterr()
        assert "N/A" in captured.out

    def test_display_summary(self, capsys):
        actions = Counter(approve=3, reject=2, skip=1)
        display_summary(actions, 10)
        captured = capsys.readouterr()
        assert "3" in captured.out
        assert "2" in captured.out
        assert "1" in captured.out
        assert "Remaining" in captured.out


class TestRunReview:
    """Test the interactive review loop with mocked input."""

    def test_approve_all(self, processed_dir):
        inputs = iter(["a", "a"])
        actions = run_review(
            processed_dir, threshold=0.7,
            input_fn=lambda _: next(inputs),
        )
        assert actions["approve"] == 2

    def test_reject_item(self, processed_dir):
        inputs = iter(["r", "s"])
        actions = run_review(
            processed_dir, threshold=0.7,
            input_fn=lambda _: next(inputs),
        )
        assert actions["reject"] == 1
        assert actions["skip"] == 1

    def test_quit_early(self, processed_dir):
        inputs = iter(["a", "q"])
        actions = run_review(
            processed_dir, threshold=0.7,
            input_fn=lambda _: next(inputs),
        )
        assert actions["approve"] == 1
        assert sum(actions.values()) == 1

    def test_invalid_then_valid(self, processed_dir):
        inputs = iter(["x", "z", "a", "s"])
        actions = run_review(
            processed_dir, threshold=0.7,
            input_fn=lambda _: next(inputs),
        )
        assert actions["approve"] == 1

    def test_no_items_below_threshold(self, processed_dir):
        actions = run_review(
            processed_dir, threshold=0.1,
            input_fn=lambda _: "a",
        )
        assert sum(actions.values()) == 0

    def test_resume_skips_reviewed(self, processed_dir):
        # First session: approve first item
        inputs1 = iter(["a", "q"])
        run_review(
            processed_dir, threshold=0.7,
            input_fn=lambda _: next(inputs1),
        )
        # Resume session: should only have 1 item left
        inputs2 = iter(["a"])
        actions = run_review(
            processed_dir, threshold=0.7,
            resume=True,
            input_fn=lambda _: next(inputs2),
        )
        assert actions["approve"] == 1

    def test_eof_treated_as_quit(self, processed_dir):
        def raise_eof(_):
            raise EOFError
        actions = run_review(
            processed_dir, threshold=0.7,
            input_fn=raise_eof,
        )
        assert sum(actions.values()) == 0


class TestApplyReviewResults:
    """Test that review decisions are written back to files."""

    def test_approve_bumps_confidence(self, processed_dir):
        state = {
            "reviewed": {"https://youtube.com/watch?v=MED": "approve"},
            "session_start": "2026-01-01T00:00:00",
        }
        apply_review_results(processed_dir, state)

        with open(processed_dir / "file_2.json") as f:
            data = json.load(f)

        med_item = next(r for r in data["results"] if r["url"] == "https://youtube.com/watch?v=MED")
        assert med_item["confidence"] == 1.0

    def test_reject_removes_from_file(self, processed_dir):
        state = {
            "reviewed": {"https://youtube.com/watch?v=LOW": "reject"},
            "session_start": "2026-01-01T00:00:00",
        }
        apply_review_results(processed_dir, state)

        with open(processed_dir / "file_2.json") as f:
            data = json.load(f)
        urls = [r["url"] for r in data["results"]]
        assert "https://youtube.com/watch?v=LOW" not in urls
        assert data["total_results"] == 2

    def test_reject_creates_discarded(self, processed_dir):
        state = {
            "reviewed": {"https://youtube.com/watch?v=LOW": "reject"},
            "session_start": "2026-01-01T00:00:00",
        }
        apply_review_results(processed_dir, state)

        discarded_path = processed_dir / "discarded.json"
        assert discarded_path.exists()
        with open(discarded_path) as f:
            discarded = json.load(f)
        assert discarded["total"] == 1
        assert discarded["items"][0]["category"] == "discard"

    def test_skip_does_nothing(self, processed_dir):
        state = {
            "reviewed": {"https://youtube.com/watch?v=MED": "skip"},
            "session_start": "2026-01-01T00:00:00",
        }
        # Read original
        with open(processed_dir / "file_2.json") as f:
            original = json.load(f)

        apply_review_results(processed_dir, state)

        with open(processed_dir / "file_2.json") as f:
            after = json.load(f)
        assert len(after["results"]) == len(original["results"])

    def test_empty_state_no_op(self, processed_dir):
        state = {"reviewed": {}, "session_start": None}
        apply_review_results(processed_dir, state)
        # Should not crash or modify files

    def test_reject_appends_to_existing_discarded(self, processed_dir):
        # Create existing discarded.json
        existing = {"total": 1, "items": [{"title": "Already discarded", "url": "http://old"}]}
        with open(processed_dir / "discarded.json", "w") as f:
            json.dump(existing, f)

        state = {
            "reviewed": {"https://youtube.com/watch?v=LOW": "reject"},
            "session_start": "2026-01-01T00:00:00",
        }
        apply_review_results(processed_dir, state)

        with open(processed_dir / "discarded.json") as f:
            discarded = json.load(f)
        assert discarded["total"] == 2
