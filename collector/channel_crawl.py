"""
channel_crawl.py — YouTube channel crawling and coverage gap detection.

Lists all uploads from official channels directly (not just search) and
cross-references the artist YAML discography against found videos.

Usage:
    uv run python channel_crawl.py --artist artists/hebe.yaml
    uv run python channel_crawl.py --artist artists/hebe.yaml --coverage
    uv run python channel_crawl.py --artist artists/hebe.yaml --coverage --json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from artist_profile import ArtistProfile, load_profile
from config import YOUTUBE_RATE_LIMIT

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("channel_crawl")

BASE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# YouTubeChannelCrawler
# ---------------------------------------------------------------------------

class YouTubeChannelCrawler:
    """
    Lists uploads from YouTube channels using the Data API v3.

    Uses playlistItems.list on the uploads playlist (derived by replacing
    the leading "UC" of a channel ID with "UU") to get all uploads.
    Paginates through all results (YouTube returns max 50 per page).
    """

    def __init__(self, api_keys: list[str]):
        if not api_keys:
            raise ValueError("At least one YouTube API key is required")
        self._keys: list[str] = api_keys
        self._idx: int = 0
        self._client = build("youtube", "v3", developerKey=self._keys[0])
        self._last_call: float = 0.0
        logger.info("YouTubeChannelCrawler: %d key(s) loaded", len(api_keys))

    def _rotate_key(self) -> bool:
        """Switch to the next API key. Returns False when all keys are exhausted."""
        self._idx += 1
        if self._idx >= len(self._keys):
            logger.error("All YouTube API keys exhausted for today")
            return False
        self._client = build("youtube", "v3", developerKey=self._keys[self._idx])
        logger.warning(
            "YouTube quota exceeded -> rotated to key #%d of %d",
            self._idx + 1, len(self._keys),
        )
        return True

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < YOUTUBE_RATE_LIMIT:
            time.sleep(YOUTUBE_RATE_LIMIT - elapsed)
        self._last_call = time.time()

    @staticmethod
    def _uploads_playlist_id(channel_id: str) -> str:
        """Derive the uploads playlist ID from a channel ID (UC... -> UU...)."""
        if channel_id.startswith("UC"):
            return "UU" + channel_id[2:]
        return channel_id

    def crawl_channel(self, channel_id: str, max_pages: int = 0) -> list[dict]:
        """
        Fetch all uploads from a YouTube channel.

        Args:
            channel_id: YouTube channel ID (starts with UC).
            max_pages: Maximum number of pages to fetch. 0 = unlimited.

        Returns:
            List of video dicts with: title, url, video_id, channel,
            description, published_at, verified=True, source="channel_crawl".
        """
        playlist_id = self._uploads_playlist_id(channel_id)
        all_items: list[dict] = []
        page_token: str | None = None
        page_count = 0

        logger.info("Crawling channel %s (playlist %s)", channel_id, playlist_id)

        while True:
            self._rate_limit()
            try:
                request = self._client.playlistItems().list(
                    playlistId=playlist_id,
                    part="snippet,contentDetails",
                    maxResults=50,
                    pageToken=page_token,
                )
                response = request.execute()
            except HttpError as e:
                if e.resp.status == 403 and "quotaExceeded" in str(e):
                    if self._rotate_key():
                        continue
                    logger.error("All keys exhausted, stopping crawl")
                    break
                logger.error("YouTube API error: %s", e)
                break

            items = response.get("items", [])
            for item in items:
                snippet = item.get("snippet", {})
                content = item.get("contentDetails", {})
                video_id = content.get("videoId", "")
                if not video_id:
                    continue

                all_items.append({
                    "title": snippet.get("title", ""),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "video_id": video_id,
                    "channel": snippet.get("channelTitle", ""),
                    "description": (snippet.get("description", "") or "")[:300].replace("\n", " "),
                    "published_at": (snippet.get("publishedAt", "") or "")[:10],
                    "verified": True,
                    "source": "channel_crawl",
                })

            page_count += 1
            logger.info(
                "  Page %d: %d items (total so far: %d)",
                page_count, len(items), len(all_items),
            )

            page_token = response.get("nextPageToken")
            if not page_token:
                break
            if max_pages and page_count >= max_pages:
                logger.info("  Reached max_pages=%d, stopping", max_pages)
                break

        logger.info(
            "Channel %s: %d total uploads fetched", channel_id, len(all_items)
        )
        return all_items

    def crawl_all_channels(
        self, profile: ArtistProfile, max_pages: int = 0
    ) -> list[dict]:
        """
        Crawl all YouTube channels defined in the artist profile.

        Returns combined list of all uploads, deduplicated by video ID.
        """
        youtube_channels = [
            ch for ch in profile.artist.channels if ch.platform == "youtube"
        ]

        if not youtube_channels:
            logger.warning("No YouTube channels defined in artist profile")
            return []

        seen_ids: set[str] = set()
        all_results: list[dict] = []

        for ch in youtube_channels:
            logger.info("Crawling channel: %s (%s)", ch.name, ch.id)
            uploads = self.crawl_channel(ch.id, max_pages=max_pages)

            for item in uploads:
                vid = item.get("video_id", "")
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    all_results.append(item)
                elif vid:
                    logger.debug("  Skipping duplicate video: %s", vid)

        logger.info(
            "All channels: %d unique uploads from %d channels",
            len(all_results), len(youtube_channels),
        )
        return all_results


def dedup_against_existing(
    crawled: list[dict], processed_dir: Path
) -> tuple[list[dict], list[dict]]:
    """
    Split crawled results into new and already-known videos.

    Reads all processed JSON files from processed_dir and extracts YouTube
    video IDs. Returns (new_videos, existing_videos).
    """
    existing_ids: set[str] = set()

    if processed_dir.exists():
        for f in processed_dir.glob("file_*.json"):
            try:
                data = json.loads(f.read_text("utf-8"))
                for r in data.get("results", []):
                    url = r.get("url", "")
                    vid = _extract_video_id(url)
                    if vid:
                        existing_ids.add(vid)
            except Exception as e:
                logger.warning("Error reading %s: %s", f, e)

    new_videos = []
    already_known = []
    for item in crawled:
        vid = item.get("video_id", "")
        if vid in existing_ids:
            already_known.append(item)
        else:
            new_videos.append(item)

    logger.info(
        "Dedup: %d new, %d already known (from %d existing IDs)",
        len(new_videos), len(already_known), len(existing_ids),
    )
    return new_videos, already_known


def _extract_video_id(url: str) -> str:
    """Extract YouTube video ID from URL."""
    if "v=" in url:
        return url.split("v=")[-1].split("&")[0]
    if "youtu.be/" in url:
        return url.split("youtu.be/")[-1].split("?")[0]
    return ""


# ---------------------------------------------------------------------------
# Coverage Gap Detection
# ---------------------------------------------------------------------------

class CoverageChecker:
    """
    Cross-references artist YAML discography against found videos
    to detect missing content.
    """

    def __init__(self, profile: ArtistProfile):
        self.profile = profile

    def check_coverage(self, videos: list[dict]) -> dict:
        """
        Analyze coverage of discography against a list of video dicts.

        Args:
            videos: List of video dicts (each with "title" and "url").

        Returns:
            Structured report with per-album and per-single coverage data.
        """
        # Build a searchable index from video titles
        title_index = self._build_title_index(videos)

        report: dict = {
            "generated_at": datetime.now().isoformat(),
            "total_videos": len(videos),
            "albums": [],
            "ost_singles": [],
            "summary": {},
        }

        # Check solo album track coverage
        total_tracks = 0
        total_found = 0
        for album in self.profile.discography.solo_albums:
            album_report = self._check_album(album, title_index)
            report["albums"].append(album_report)
            total_tracks += album_report["total_tracks"]
            total_found += album_report["found_count"]

        # Check OST singles
        ost_found = 0
        for ost in self.profile.discography.ost_singles:
            ost_report = self._check_single(ost.name, title_index)
            ost_report["source"] = ost.source
            ost_report["year"] = ost.year
            report["ost_singles"].append(ost_report)
            if ost_report["found"]:
                ost_found += 1

        report["summary"] = {
            "album_tracks_total": total_tracks,
            "album_tracks_found": total_found,
            "album_tracks_missing": total_tracks - total_found,
            "album_coverage_pct": round(total_found / total_tracks * 100, 1) if total_tracks else 0,
            "ost_total": len(self.profile.discography.ost_singles),
            "ost_found": ost_found,
            "ost_missing": len(self.profile.discography.ost_singles) - ost_found,
            "ost_coverage_pct": round(
                ost_found / len(self.profile.discography.ost_singles) * 100, 1
            ) if self.profile.discography.ost_singles else 0,
        }

        return report

    def _build_title_index(self, videos: list[dict]) -> list[str]:
        """Build a lowercase list of all video titles for searching."""
        titles = []
        for v in videos:
            title = v.get("title", "").lower()
            if title:
                titles.append(title)
        return titles

    def _check_album(self, album, title_index: list[str]) -> dict:
        """Check which tracks from an album have matching videos."""
        found_tracks = []
        missing_tracks = []

        for track in album.tracks:
            if self._find_track(track, title_index):
                found_tracks.append(track)
            else:
                missing_tracks.append(track)

        return {
            "album_name": album.name,
            "year": album.year,
            "total_tracks": len(album.tracks),
            "found_count": len(found_tracks),
            "missing_count": len(missing_tracks),
            "found_tracks": found_tracks,
            "missing_tracks": missing_tracks,
        }

    def _check_single(self, name: str, title_index: list[str]) -> dict:
        """Check if a single has a matching video."""
        found = self._find_track(name, title_index)
        return {
            "name": name,
            "found": found,
        }

    def _find_track(self, track_name: str, title_index: list[str]) -> bool:
        """Check if a track name appears in any video title."""
        track_lower = track_name.lower()
        for title in title_index:
            if track_lower in title:
                return True
        return False


def format_coverage_report(report: dict) -> str:
    """Format a coverage report as a human-readable string."""
    lines: list[str] = []
    summary = report["summary"]

    lines.append("=" * 60)
    lines.append("COVERAGE GAP REPORT")
    lines.append("=" * 60)
    lines.append(f"Total videos analyzed: {report['total_videos']}")
    lines.append("")

    # Album coverage
    lines.append("-" * 40)
    lines.append("ALBUM TRACK COVERAGE")
    lines.append("-" * 40)
    for album in report["albums"]:
        status = "OK" if album["missing_count"] == 0 else "GAPS"
        lines.append(
            f"  {album['album_name']} ({album['year']}): "
            f"{album['found_count']}/{album['total_tracks']} tracks found [{status}]"
        )
        if album["missing_tracks"]:
            for track in album["missing_tracks"]:
                lines.append(f"    MISSING: {track}")
    lines.append("")
    lines.append(
        f"Album total: {summary['album_tracks_found']}/{summary['album_tracks_total']} "
        f"tracks ({summary['album_coverage_pct']}%)"
    )
    lines.append("")

    # OST coverage
    lines.append("-" * 40)
    lines.append("OST / SINGLES COVERAGE")
    lines.append("-" * 40)
    missing_osts = [s for s in report["ost_singles"] if not s["found"]]
    found_osts = [s for s in report["ost_singles"] if s["found"]]

    if missing_osts:
        for s in missing_osts:
            src = f" (from {s['source']})" if s.get("source") else ""
            lines.append(f"  MISSING: {s['name']}{src} [{s.get('year', '')}]")
    lines.append("")
    lines.append(
        f"OST total: {summary['ost_found']}/{summary['ost_total']} "
        f"singles ({summary['ost_coverage_pct']}%)"
    )

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def load_all_videos(processed_dir: Path) -> list[dict]:
    """Load all video results from processed JSON files."""
    all_videos: list[dict] = []
    if not processed_dir.exists():
        logger.warning("Processed directory does not exist: %s", processed_dir)
        return all_videos

    for f in sorted(processed_dir.glob("file_*.json")):
        try:
            data = json.loads(f.read_text("utf-8"))
            all_videos.extend(data.get("results", []))
        except Exception as e:
            logger.warning("Error reading %s: %s", f, e)

    logger.info("Loaded %d videos from %s", len(all_videos), processed_dir)
    return all_videos


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _get_youtube_keys() -> list[str]:
    """Collect YouTube API keys from environment."""
    return [
        k for k in [
            os.getenv("YOUTUBE_API_KEY"),
            os.getenv("YOUTUBE_API_KEY_2"),
            os.getenv("YOUTUBE_API_KEY_3"),
            os.getenv("YOUTUBE_API_KEY_4"),
            os.getenv("YOUTUBE_API_KEY_5"),
            os.getenv("YOUTUBE_API_KEY_6"),
        ] if k
    ]


def _resolve_data_dir(profile: ArtistProfile) -> Path:
    """Resolve data directory for an artist based on slugified name."""
    slug = re.sub(r"[^a-z0-9]+", "-", profile.artist.names.english.lower()).strip("-")
    data_dir = BASE_DIR / "data" / slug
    return data_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTube channel crawl and coverage gap detection"
    )
    parser.add_argument(
        "--artist",
        type=str,
        default=None,
        help="Path to artist YAML (default: auto-detect from artists/)",
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run coverage gap detection instead of channel crawl",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output coverage report as JSON",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Max pages to fetch per channel (0 = unlimited)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path for crawl results (default: data/{slug}/channel_crawl.json)",
    )
    args = parser.parse_args()

    load_dotenv()

    # Load artist profile
    profile = load_profile(args.artist)
    data_dir = _resolve_data_dir(profile)
    processed_dir = data_dir / "processed"

    logger.info(
        "Artist: %s (%s)", profile.artist.names.primary, profile.artist.names.english
    )
    logger.info("Data dir: %s", data_dir)

    if args.coverage:
        # Coverage gap detection mode
        all_videos = load_all_videos(processed_dir)
        if not all_videos:
            logger.warning("No processed videos found. Run the pipeline first.")
            sys.exit(1)

        checker = CoverageChecker(profile)
        report = checker.check_coverage(all_videos)

        if args.json_output:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(format_coverage_report(report))
    else:
        # Channel crawl mode
        youtube_keys = _get_youtube_keys()
        if not youtube_keys:
            logger.error("No YOUTUBE_API_KEY found in environment")
            sys.exit(1)

        crawler = YouTubeChannelCrawler(youtube_keys)
        all_uploads = crawler.crawl_all_channels(profile, max_pages=args.max_pages)

        if not all_uploads:
            logger.warning("No uploads found from any channel")
            sys.exit(0)

        # Dedup against existing processed data
        new_videos, existing = dedup_against_existing(all_uploads, processed_dir)

        # Save results
        output_path = args.output or str(data_dir / "channel_crawl.json")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        output_data = {
            "crawled_at": datetime.now().isoformat(),
            "artist": profile.artist.names.primary,
            "channels_crawled": [
                {"id": ch.id, "name": ch.name}
                for ch in profile.artist.channels
                if ch.platform == "youtube"
            ],
            "total_uploads": len(all_uploads),
            "new_videos": len(new_videos),
            "already_known": len(existing),
            "results": new_videos,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info("Results saved to %s", output_path)
        logger.info(
            "Summary: %d total uploads, %d new, %d already in processed/",
            len(all_uploads), len(new_videos), len(existing),
        )


if __name__ == "__main__":
    main()
