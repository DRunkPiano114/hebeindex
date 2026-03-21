"""
test_channel_crawl.py — Tests for channel_crawl.py.

Covers:
- YouTubeChannelCrawler: uploads playlist ID derivation, pagination, key rotation,
  rate limiting, deduplication across channels
- CoverageChecker: album track matching, OST matching, report formatting
- dedup_against_existing: new vs known video splitting
- _extract_video_id: URL parsing
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from googleapiclient.errors import HttpError

sys.path.insert(0, str(Path(__file__).parent.parent))

from channel_crawl import (
    YouTubeChannelCrawler,
    CoverageChecker,
    dedup_against_existing,
    format_coverage_report,
    load_all_videos,
    _extract_video_id,
)
from artist_profile import (
    ArtistProfile,
    ArtistInfo,
    ArtistNames,
    Channel,
    GroupInfo,
    Discography,
    Album,
    OSTSingle,
    Concert,
    VarietyShow,
    Collaborator,
    Category,
    ClassificationConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_profile(channels=None, albums=None, ost_singles=None) -> ArtistProfile:
    """Build a minimal ArtistProfile for testing."""
    if channels is None:
        channels = [
            Channel(platform="youtube", id="UCtest123456789", name="Test Channel"),
        ]
    if albums is None:
        albums = [
            Album(name="Test Album", year=2020, tracks=["Song A", "Song B", "Song C"]),
        ]
    if ost_singles is None:
        ost_singles = [
            OSTSingle(name="OST Track", source="Movie X", year=2021),
        ]

    return ArtistProfile(
        artist=ArtistInfo(
            names=ArtistNames(primary="Test Artist", english="Test Artist", aliases=[]),
            official_channels=["Test Channel"],
            labels=["Test Label"],
            channels=channels,
        ),
        group=GroupInfo(
            name="Test Group", aliases=[], members=[], member_names=[],
        ),
        discography=Discography(
            solo_albums=albums,
            ost_singles=ost_singles,
            concerts=[],
            variety_shows=[],
            collaborators=[],
        ),
        categories=[
            Category(id=2, key="personal_mv", label="MV"),
        ],
        classification=ClassificationConfig(priority=["personal_mv"]),
    )


def _make_playlist_response(items, next_page_token=None):
    """Build a mock YouTube playlistItems.list response."""
    return {
        "items": items,
        "nextPageToken": next_page_token,
    }


def _make_playlist_item(video_id, title="Test Video", channel="Test Channel",
                        description="desc", published_at="2023-01-15T00:00:00Z"):
    """Build a single playlistItems item."""
    return {
        "snippet": {
            "title": title,
            "channelTitle": channel,
            "description": description,
            "publishedAt": published_at,
        },
        "contentDetails": {
            "videoId": video_id,
        },
    }


# ---------------------------------------------------------------------------
# YouTubeChannelCrawler._uploads_playlist_id
# ---------------------------------------------------------------------------

class TestUploadsPlaylistId:
    def test_uc_to_uu(self):
        assert YouTubeChannelCrawler._uploads_playlist_id("UCtest123") == "UUtest123"

    def test_preserves_rest_of_id(self):
        channel_id = "UC9LgZOBRp1eDY353sM3t9-A"
        expected = "UU9LgZOBRp1eDY353sM3t9-A"
        assert YouTubeChannelCrawler._uploads_playlist_id(channel_id) == expected

    def test_non_uc_prefix_unchanged(self):
        # If somehow not starting with UC, return as-is
        assert YouTubeChannelCrawler._uploads_playlist_id("PLtest123") == "PLtest123"


# ---------------------------------------------------------------------------
# YouTubeChannelCrawler.crawl_channel
# ---------------------------------------------------------------------------

class TestCrawlChannel:
    @patch("channel_crawl.build")
    def test_single_page_returns_videos(self, mock_build):
        """Single page of results is returned correctly."""
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        items = [
            _make_playlist_item("vid1", title="Video One"),
            _make_playlist_item("vid2", title="Video Two"),
        ]
        mock_list = MagicMock()
        mock_list.execute.return_value = _make_playlist_response(items)
        mock_client.playlistItems.return_value.list.return_value = mock_list

        crawler = YouTubeChannelCrawler(["fake-key"])
        results = crawler.crawl_channel("UCtest123")

        assert len(results) == 2
        assert results[0]["video_id"] == "vid1"
        assert results[0]["title"] == "Video One"
        assert results[0]["url"] == "https://www.youtube.com/watch?v=vid1"
        assert results[0]["verified"] is True
        assert results[0]["source"] == "channel_crawl"
        assert results[1]["video_id"] == "vid2"

    @patch("channel_crawl.build")
    def test_pagination_fetches_all_pages(self, mock_build):
        """Multiple pages are fetched via nextPageToken."""
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        page1 = _make_playlist_response(
            [_make_playlist_item("vid1")],
            next_page_token="TOKEN_PAGE2",
        )
        page2 = _make_playlist_response(
            [_make_playlist_item("vid2")],
            next_page_token=None,
        )
        mock_list = MagicMock()
        mock_list.execute.side_effect = [page1, page2]
        mock_client.playlistItems.return_value.list.return_value = mock_list

        crawler = YouTubeChannelCrawler(["fake-key"])
        results = crawler.crawl_channel("UCtest123")

        assert len(results) == 2
        assert results[0]["video_id"] == "vid1"
        assert results[1]["video_id"] == "vid2"

    @patch("channel_crawl.build")
    def test_max_pages_limits_pagination(self, mock_build):
        """max_pages parameter stops crawling after N pages."""
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        page1 = _make_playlist_response(
            [_make_playlist_item("vid1")],
            next_page_token="TOKEN_PAGE2",
        )
        mock_list = MagicMock()
        mock_list.execute.return_value = page1
        mock_client.playlistItems.return_value.list.return_value = mock_list

        crawler = YouTubeChannelCrawler(["fake-key"])
        results = crawler.crawl_channel("UCtest123", max_pages=1)

        assert len(results) == 1
        # Only one execute() call despite having a nextPageToken
        assert mock_list.execute.call_count == 1

    @patch("channel_crawl.build")
    def test_empty_channel_returns_empty_list(self, mock_build):
        """Channel with no uploads returns []."""
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        mock_list = MagicMock()
        mock_list.execute.return_value = _make_playlist_response([])
        mock_client.playlistItems.return_value.list.return_value = mock_list

        crawler = YouTubeChannelCrawler(["fake-key"])
        results = crawler.crawl_channel("UCempty")

        assert results == []

    @patch("channel_crawl.build")
    def test_items_without_video_id_skipped(self, mock_build):
        """Items missing videoId in contentDetails are skipped."""
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        items = [
            _make_playlist_item("vid1"),
            {"snippet": {"title": "No ID"}, "contentDetails": {}},
        ]
        mock_list = MagicMock()
        mock_list.execute.return_value = _make_playlist_response(items)
        mock_client.playlistItems.return_value.list.return_value = mock_list

        crawler = YouTubeChannelCrawler(["fake-key"])
        results = crawler.crawl_channel("UCtest")

        assert len(results) == 1
        assert results[0]["video_id"] == "vid1"

    @patch("channel_crawl.build")
    def test_description_truncated_to_300(self, mock_build):
        """Long descriptions are truncated to 300 chars."""
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        long_desc = "A" * 500
        items = [_make_playlist_item("vid1", description=long_desc)]
        mock_list = MagicMock()
        mock_list.execute.return_value = _make_playlist_response(items)
        mock_client.playlistItems.return_value.list.return_value = mock_list

        crawler = YouTubeChannelCrawler(["fake-key"])
        results = crawler.crawl_channel("UCtest")

        assert len(results[0]["description"]) <= 300

    @patch("channel_crawl.build")
    def test_published_at_truncated_to_date(self, mock_build):
        """publishedAt is truncated to YYYY-MM-DD."""
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        items = [_make_playlist_item("vid1", published_at="2023-06-15T12:30:00Z")]
        mock_list = MagicMock()
        mock_list.execute.return_value = _make_playlist_response(items)
        mock_client.playlistItems.return_value.list.return_value = mock_list

        crawler = YouTubeChannelCrawler(["fake-key"])
        results = crawler.crawl_channel("UCtest")

        assert results[0]["published_at"] == "2023-06-15"


# ---------------------------------------------------------------------------
# YouTubeChannelCrawler — key rotation
# ---------------------------------------------------------------------------

class TestKeyRotation:
    @patch("channel_crawl.build")
    def test_quota_exceeded_rotates_key(self, mock_build):
        """403 quotaExceeded triggers key rotation and retry."""
        mock_client1 = MagicMock()
        mock_client2 = MagicMock()

        # First client raises quota error, second succeeds
        error_resp = MagicMock()
        error_resp.status = 403
        quota_error = HttpError(error_resp, b"quotaExceeded")

        mock_list1 = MagicMock()
        mock_list1.execute.side_effect = quota_error
        mock_client1.playlistItems.return_value.list.return_value = mock_list1

        items = [_make_playlist_item("vid1")]
        mock_list2 = MagicMock()
        mock_list2.execute.return_value = _make_playlist_response(items)
        mock_client2.playlistItems.return_value.list.return_value = mock_list2

        mock_build.side_effect = [mock_client1, mock_client2]

        crawler = YouTubeChannelCrawler(["key1", "key2"])
        results = crawler.crawl_channel("UCtest")

        assert len(results) == 1
        assert mock_build.call_count == 2

    @patch("channel_crawl.build")
    def test_all_keys_exhausted_returns_partial(self, mock_build):
        """When all keys are exhausted, return whatever was collected so far."""
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        error_resp = MagicMock()
        error_resp.status = 403
        quota_error = HttpError(error_resp, b"quotaExceeded")

        mock_list = MagicMock()
        mock_list.execute.side_effect = quota_error
        mock_client.playlistItems.return_value.list.return_value = mock_list

        crawler = YouTubeChannelCrawler(["only-key"])
        results = crawler.crawl_channel("UCtest")

        assert results == []

    @patch("channel_crawl.build")
    def test_non_quota_error_stops_crawl(self, mock_build):
        """Non-quota HttpError stops crawling (no rotation)."""
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        error_resp = MagicMock()
        error_resp.status = 404
        http_error = HttpError(error_resp, b"playlist not found")

        mock_list = MagicMock()
        mock_list.execute.side_effect = http_error
        mock_client.playlistItems.return_value.list.return_value = mock_list

        crawler = YouTubeChannelCrawler(["key1", "key2"])
        results = crawler.crawl_channel("UCtest")

        assert results == []
        # Should NOT rotate — only 1 build() call (initial)
        assert mock_build.call_count == 1


# ---------------------------------------------------------------------------
# YouTubeChannelCrawler.crawl_all_channels
# ---------------------------------------------------------------------------

class TestCrawlAllChannels:
    @patch("channel_crawl.build")
    def test_deduplicates_across_channels(self, mock_build):
        """Videos appearing in multiple channels are deduplicated."""
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        # Both channels return the same video
        items = [_make_playlist_item("shared_vid", title="Shared Video")]
        mock_list = MagicMock()
        mock_list.execute.return_value = _make_playlist_response(items)
        mock_client.playlistItems.return_value.list.return_value = mock_list

        profile = _make_profile(channels=[
            Channel(platform="youtube", id="UCchan1", name="Channel 1"),
            Channel(platform="youtube", id="UCchan2", name="Channel 2"),
        ])

        crawler = YouTubeChannelCrawler(["fake-key"])
        results = crawler.crawl_all_channels(profile)

        # Only one copy despite two channels having the same video
        assert len(results) == 1
        assert results[0]["video_id"] == "shared_vid"

    @patch("channel_crawl.build")
    def test_no_youtube_channels_returns_empty(self, mock_build):
        """Profile with no YouTube channels returns []."""
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        profile = _make_profile(channels=[
            Channel(platform="bilibili", id="12345", name="Bilibili Channel"),
        ])

        crawler = YouTubeChannelCrawler(["fake-key"])
        results = crawler.crawl_all_channels(profile)

        assert results == []

    @patch("channel_crawl.build")
    def test_empty_channels_list_returns_empty(self, mock_build):
        """Profile with empty channels list returns []."""
        mock_client = MagicMock()
        mock_build.return_value = mock_client

        profile = _make_profile(channels=[])

        crawler = YouTubeChannelCrawler(["fake-key"])
        results = crawler.crawl_all_channels(profile)

        assert results == []


# ---------------------------------------------------------------------------
# _extract_video_id
# ---------------------------------------------------------------------------

class TestExtractVideoId:
    def test_standard_youtube_url(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=abc123") == "abc123"

    def test_youtube_url_with_extra_params(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=abc123&t=60") == "abc123"

    def test_youtu_be_short_url(self):
        assert _extract_video_id("https://youtu.be/abc123") == "abc123"

    def test_youtu_be_with_params(self):
        assert _extract_video_id("https://youtu.be/abc123?t=30") == "abc123"

    def test_non_youtube_url(self):
        assert _extract_video_id("https://bilibili.com/video/BV123") == ""

    def test_empty_string(self):
        assert _extract_video_id("") == ""


# ---------------------------------------------------------------------------
# dedup_against_existing
# ---------------------------------------------------------------------------

class TestDedupAgainstExisting:
    def test_new_videos_identified(self, tmp_path):
        """Videos not in processed dir are returned as new."""
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()

        existing_data = {
            "results": [
                {"url": "https://www.youtube.com/watch?v=existing1"},
                {"url": "https://www.youtube.com/watch?v=existing2"},
            ]
        }
        (processed_dir / "file_2.json").write_text(
            json.dumps(existing_data), encoding="utf-8"
        )

        crawled = [
            {"video_id": "existing1", "title": "Old"},
            {"video_id": "new1", "title": "New"},
        ]

        new, known = dedup_against_existing(crawled, processed_dir)

        assert len(new) == 1
        assert new[0]["video_id"] == "new1"
        assert len(known) == 1
        assert known[0]["video_id"] == "existing1"

    def test_empty_processed_dir_all_new(self, tmp_path):
        """When processed dir is empty, all crawled videos are new."""
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()

        crawled = [
            {"video_id": "vid1", "title": "Video 1"},
            {"video_id": "vid2", "title": "Video 2"},
        ]

        new, known = dedup_against_existing(crawled, processed_dir)

        assert len(new) == 2
        assert len(known) == 0

    def test_nonexistent_processed_dir(self, tmp_path):
        """Non-existent processed dir treats all as new."""
        processed_dir = tmp_path / "nonexistent"

        crawled = [{"video_id": "vid1", "title": "Video 1"}]

        new, known = dedup_against_existing(crawled, processed_dir)

        assert len(new) == 1
        assert len(known) == 0

    def test_all_already_known(self, tmp_path):
        """All crawled videos already exist in processed."""
        processed_dir = tmp_path / "processed"
        processed_dir.mkdir()

        existing_data = {
            "results": [
                {"url": "https://www.youtube.com/watch?v=vid1"},
            ]
        }
        (processed_dir / "file_2.json").write_text(
            json.dumps(existing_data), encoding="utf-8"
        )

        crawled = [{"video_id": "vid1", "title": "Video 1"}]

        new, known = dedup_against_existing(crawled, processed_dir)

        assert len(new) == 0
        assert len(known) == 1


# ---------------------------------------------------------------------------
# CoverageChecker
# ---------------------------------------------------------------------------

class TestCoverageChecker:
    def test_all_tracks_found(self):
        """When all tracks match, coverage is 100%."""
        profile = _make_profile(
            albums=[Album(name="Album A", year=2020, tracks=["Song A", "Song B"])],
            ost_singles=[OSTSingle(name="OST One", source="Film X", year=2021)],
        )
        videos = [
            {"title": "Test Artist - Song A MV Official"},
            {"title": "Test Artist Song B Official MV"},
            {"title": "OST One - Official Video"},
        ]

        checker = CoverageChecker(profile)
        report = checker.check_coverage(videos)

        assert report["summary"]["album_tracks_total"] == 2
        assert report["summary"]["album_tracks_found"] == 2
        assert report["summary"]["album_tracks_missing"] == 0
        assert report["summary"]["album_coverage_pct"] == 100.0
        assert report["summary"]["ost_found"] == 1
        assert report["summary"]["ost_missing"] == 0

    def test_missing_tracks_reported(self):
        """Missing tracks are listed in the report."""
        profile = _make_profile(
            albums=[Album(name="Album A", year=2020, tracks=["Song A", "Song B", "Song C"])],
            ost_singles=[],
        )
        videos = [
            {"title": "Test Artist - Song A MV"},
        ]

        checker = CoverageChecker(profile)
        report = checker.check_coverage(videos)

        album = report["albums"][0]
        assert album["found_count"] == 1
        assert album["missing_count"] == 2
        assert "Song B" in album["missing_tracks"]
        assert "Song C" in album["missing_tracks"]
        assert "Song A" in album["found_tracks"]

    def test_case_insensitive_matching(self):
        """Track matching is case-insensitive."""
        profile = _make_profile(
            albums=[Album(name="Album", year=2020, tracks=["LOVE!"])],
            ost_singles=[],
        )
        videos = [
            {"title": "artist love! official mv"},
        ]

        checker = CoverageChecker(profile)
        report = checker.check_coverage(videos)

        assert report["albums"][0]["found_count"] == 1

    def test_empty_videos_all_missing(self):
        """With no videos, everything is missing."""
        profile = _make_profile(
            albums=[Album(name="A", year=2020, tracks=["X", "Y"])],
            ost_singles=[OSTSingle(name="Z", source="", year=2020)],
        )

        checker = CoverageChecker(profile)
        report = checker.check_coverage([])

        assert report["summary"]["album_tracks_found"] == 0
        assert report["summary"]["album_tracks_missing"] == 2
        assert report["summary"]["ost_found"] == 0
        assert report["summary"]["ost_missing"] == 1

    def test_multiple_albums(self):
        """Coverage spans multiple albums correctly."""
        profile = _make_profile(
            albums=[
                Album(name="Album 1", year=2018, tracks=["T1", "T2"]),
                Album(name="Album 2", year=2020, tracks=["T3"]),
            ],
            ost_singles=[],
        )
        videos = [
            {"title": "T1 Official"},
            {"title": "T3 Live"},
        ]

        checker = CoverageChecker(profile)
        report = checker.check_coverage(videos)

        assert report["summary"]["album_tracks_total"] == 3
        assert report["summary"]["album_tracks_found"] == 2
        assert report["summary"]["album_tracks_missing"] == 1

        assert report["albums"][0]["found_count"] == 1  # Album 1: T1
        assert report["albums"][0]["missing_tracks"] == ["T2"]
        assert report["albums"][1]["found_count"] == 1  # Album 2: T3

    def test_ost_with_source_info(self):
        """OST report includes source and year."""
        profile = _make_profile(
            albums=[],
            ost_singles=[
                OSTSingle(name="Theme Song", source="Drama A", year=2022),
            ],
        )
        videos = []

        checker = CoverageChecker(profile)
        report = checker.check_coverage(videos)

        ost = report["ost_singles"][0]
        assert ost["name"] == "Theme Song"
        assert ost["source"] == "Drama A"
        assert ost["year"] == 2022
        assert ost["found"] is False

    def test_no_albums_no_osts(self):
        """Empty discography produces zero counts."""
        profile = _make_profile(albums=[], ost_singles=[])

        checker = CoverageChecker(profile)
        report = checker.check_coverage([])

        assert report["summary"]["album_tracks_total"] == 0
        assert report["summary"]["album_coverage_pct"] == 0
        assert report["summary"]["ost_total"] == 0
        assert report["summary"]["ost_coverage_pct"] == 0


# ---------------------------------------------------------------------------
# format_coverage_report
# ---------------------------------------------------------------------------

class TestFormatCoverageReport:
    def test_report_contains_key_sections(self):
        """Report text includes album and OST sections."""
        report = {
            "generated_at": "2024-01-01T00:00:00",
            "total_videos": 100,
            "albums": [
                {
                    "album_name": "Test Album",
                    "year": 2020,
                    "total_tracks": 3,
                    "found_count": 2,
                    "missing_count": 1,
                    "found_tracks": ["Song A", "Song B"],
                    "missing_tracks": ["Song C"],
                },
            ],
            "ost_singles": [
                {"name": "OST One", "found": True, "source": "Film", "year": 2021},
                {"name": "OST Two", "found": False, "source": "Drama", "year": 2022},
            ],
            "summary": {
                "album_tracks_total": 3,
                "album_tracks_found": 2,
                "album_tracks_missing": 1,
                "album_coverage_pct": 66.7,
                "ost_total": 2,
                "ost_found": 1,
                "ost_missing": 1,
                "ost_coverage_pct": 50.0,
            },
        }

        text = format_coverage_report(report)

        assert "COVERAGE GAP REPORT" in text
        assert "ALBUM TRACK COVERAGE" in text
        assert "Test Album (2020)" in text
        assert "2/3 tracks found" in text
        assert "MISSING: Song C" in text
        assert "OST / SINGLES COVERAGE" in text
        assert "MISSING: OST Two" in text
        assert "66.7%" in text


# ---------------------------------------------------------------------------
# load_all_videos
# ---------------------------------------------------------------------------

class TestLoadAllVideos:
    def test_loads_from_multiple_files(self, tmp_path):
        """Loads results from all file_*.json in directory."""
        processed = tmp_path / "processed"
        processed.mkdir()

        data1 = {"results": [{"title": "V1", "url": "u1"}]}
        data2 = {"results": [{"title": "V2", "url": "u2"}, {"title": "V3", "url": "u3"}]}

        (processed / "file_2.json").write_text(json.dumps(data1), encoding="utf-8")
        (processed / "file_3.json").write_text(json.dumps(data2), encoding="utf-8")

        videos = load_all_videos(processed)

        assert len(videos) == 3

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        videos = load_all_videos(tmp_path / "nope")
        assert videos == []

    def test_empty_dir_returns_empty(self, tmp_path):
        processed = tmp_path / "processed"
        processed.mkdir()
        videos = load_all_videos(processed)
        assert videos == []

    def test_ignores_non_matching_files(self, tmp_path):
        """Files not matching file_*.json pattern are ignored."""
        processed = tmp_path / "processed"
        processed.mkdir()

        (processed / "file_2.json").write_text(
            json.dumps({"results": [{"title": "V1"}]}), encoding="utf-8"
        )
        (processed / "other.json").write_text(
            json.dumps({"results": [{"title": "V2"}]}), encoding="utf-8"
        )

        videos = load_all_videos(processed)
        assert len(videos) == 1


# ---------------------------------------------------------------------------
# Artist profile — channels field
# ---------------------------------------------------------------------------

class TestArtistProfileChannels:
    def test_channels_field_optional(self):
        """Profile without channels field should still parse."""
        profile = ArtistProfile(
            artist=ArtistInfo(
                names=ArtistNames(primary="Test", english="Test", aliases=[]),
                official_channels=[],
                labels=[],
            ),
            group=GroupInfo(name="G", aliases=[], members=[], member_names=[]),
            discography=Discography(
                solo_albums=[], ost_singles=[], concerts=[],
                variety_shows=[], collaborators=[],
            ),
            categories=[],
            classification=ClassificationConfig(priority=[]),
        )
        assert profile.artist.channels == []

    def test_channels_field_with_data(self):
        """Profile with channels parses correctly."""
        profile = _make_profile(channels=[
            Channel(platform="youtube", id="UCtest", name="My Channel"),
            Channel(platform="bilibili", id="12345", name="B Channel"),
        ])
        assert len(profile.artist.channels) == 2
        assert profile.artist.channels[0].platform == "youtube"
        assert profile.artist.channels[0].id == "UCtest"
        assert profile.artist.channels[1].platform == "bilibili"


# ---------------------------------------------------------------------------
# YouTubeChannelCrawler — constructor
# ---------------------------------------------------------------------------

class TestCrawlerConstructor:
    @patch("channel_crawl.build")
    def test_requires_at_least_one_key(self, mock_build):
        with pytest.raises(ValueError, match="At least one YouTube API key"):
            YouTubeChannelCrawler([])

    @patch("channel_crawl.build")
    def test_accepts_single_key(self, mock_build):
        mock_build.return_value = MagicMock()
        crawler = YouTubeChannelCrawler(["key1"])
        mock_build.assert_called_once_with("youtube", "v3", developerKey="key1")

    @patch("channel_crawl.build")
    def test_accepts_multiple_keys(self, mock_build):
        mock_build.return_value = MagicMock()
        crawler = YouTubeChannelCrawler(["key1", "key2", "key3"])
        # Only first key used at init
        mock_build.assert_called_once_with("youtube", "v3", developerKey="key1")
