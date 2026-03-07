"""
tools.py — Search tools and URL verifier.
Copied from collector/tools.py for folder independence.
"""

import os
import re
import time
import json
import logging
from datetime import datetime
from typing import Optional

import httpx
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from agent.config import (
    YOUTUBE_RATE_LIMIT,
    GOOGLE_RATE_LIMIT,
    BILIBILI_RATE_LIMIT,
    VERIFY_TIMEOUT,
    VERIFY_MAX_RETRIES,
    YOUTUBE_MAX_RESULTS,
    BILIBILI_PAGE_SIZE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# YouTube Data API v3
# ---------------------------------------------------------------------------

class YouTubeSearchTool:
    """
    Searches YouTube via the official Data API v3.
    Results are authoritative — if the API returns a video, it exists and is public.

    Accepts a list of API keys; when a key's daily quota is exhausted (HTTP 403
    quotaExceeded), automatically rotates to the next key and retries.
    """

    def __init__(self, api_keys: list[str]):
        if not api_keys:
            raise ValueError("At least one YouTube API key is required")
        self._keys: list[str] = api_keys
        self._idx: int = 0
        self._client = build("youtube", "v3", developerKey=self._keys[0])
        self._last_call: float = 0.0
        logger.info(f"YouTubeSearchTool: {len(api_keys)} key(s) loaded")

    def _rotate_key(self) -> bool:
        """Switch to the next API key. Returns False when all keys are exhausted."""
        self._idx += 1
        if self._idx >= len(self._keys):
            logger.error("All YouTube API keys exhausted for today")
            return False
        self._client = build("youtube", "v3", developerKey=self._keys[self._idx])
        logger.warning(
            f"YouTube quota exceeded → rotated to key #{self._idx + 1} of {len(self._keys)}"
        )
        return True

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < YOUTUBE_RATE_LIMIT:
            time.sleep(YOUTUBE_RATE_LIMIT - elapsed)
        self._last_call = time.time()

    def _fetch_video_details(self, video_ids: list[str]) -> list[dict]:
        """Batch-fetch video details (snippet, statistics, duration) by ID list."""
        self._rate_limit()
        try:
            videos_resp = (
                self._client.videos()
                .list(
                    part="snippet,statistics,contentDetails",
                    id=",".join(video_ids),
                )
                .execute()
            )
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                if self._rotate_key():
                    return self._fetch_video_details(video_ids)
                return []
            logger.error(f"YouTube videos.list error: {e}")
            return []

        results = []
        for item in videos_resp.get("items", []):
            snippet = item["snippet"]
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})
            results.append(
                {
                    "title": snippet["title"],
                    "url": f"https://www.youtube.com/watch?v={item['id']}",
                    "channel": snippet["channelTitle"],
                    "description": snippet.get("description", "")[:300].replace("\n", " "),
                    "published_at": snippet["publishedAt"][:10],
                    "view_count": int(stats.get("viewCount", 0)),
                    "duration": _parse_duration(content.get("duration", "")),
                    "verified": True,
                }
            )
        return results

    def search(self, query: str, max_results: int = YOUTUBE_MAX_RESULTS) -> list[dict]:
        """
        Returns a list of verified YouTube video dicts:
          title, url, channel, description, published_at, view_count, verified=True
        """
        self._rate_limit()
        try:
            search_resp = (
                self._client.search()
                .list(
                    q=query,
                    part="id,snippet",
                    maxResults=min(max_results, 50),
                    type="video",
                    order="relevance",
                )
                .execute()
            )
        except HttpError as e:
            if e.resp.status == 403 and "quotaExceeded" in str(e):
                if self._rotate_key():
                    return self.search(query, max_results)
                return []
            logger.error(f"YouTube search error for '{query}': {e}")
            return []

        video_ids = [
            item["id"]["videoId"]
            for item in search_resp.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            return []

        results = self._fetch_video_details(video_ids)
        logger.info(f"YouTube '{query}' → {len(results)} results")
        return results

    def search_channel_videos(
        self, channel_id: str, max_results: int = 50
    ) -> list[dict]:
        """Fetch videos from a specific channel (useful for official channels)."""
        self._rate_limit()
        try:
            resp = (
                self._client.search()
                .list(
                    channelId=channel_id,
                    part="id,snippet",
                    maxResults=min(max_results, 50),
                    type="video",
                    order="date",
                )
                .execute()
            )
            video_ids = [
                item["id"]["videoId"]
                for item in resp.get("items", [])
                if item.get("id", {}).get("videoId")
            ]
            if not video_ids:
                return []
            return self._fetch_video_details(video_ids)
        except HttpError as e:
            logger.error(f"Channel search error: {e}")
            return []


def _parse_duration(iso: str) -> str:
    """Convert ISO 8601 duration (PT4M35S) to readable format (4:35)."""
    if not iso:
        return ""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not match:
        return iso
    h, m, s = (int(x or 0) for x in match.groups())
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ---------------------------------------------------------------------------
# Google Search via Serper.dev
# ---------------------------------------------------------------------------

class GoogleSearchTool:
    """
    Wraps Serper.dev's Google Search JSON API.
    Best for finding Bilibili pages, news articles, interviews.
    """

    ENDPOINT = "https://google.serper.dev/search"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._last_call: float = 0.0

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < GOOGLE_RATE_LIMIT:
            time.sleep(GOOGLE_RATE_LIMIT - elapsed)
        self._last_call = time.time()

    def search(self, query: str, num: int = 10) -> list[dict]:
        """
        Returns list of Google results:
          title, url, snippet, date, verified=None (needs verify_urls)
        """
        self._rate_limit()
        payload = {"q": query, "num": min(num, 10), "hl": "zh-tw", "gl": "tw"}
        headers = {"X-API-KEY": self._api_key, "Content-Type": "application/json"}

        try:
            resp = httpx.post(
                self.ENDPOINT, json=payload, headers=headers, timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Google search error for '{query}': {e}")
            return []

        results = []
        for item in data.get("organic", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "date": item.get("date", ""),
                    "verified": None,
                }
            )

        logger.info(f"Google '{query}' → {len(results)} results")
        return results


# ---------------------------------------------------------------------------
# Bilibili Search (unofficial public API, no key required)
# ---------------------------------------------------------------------------

class BilibiliSearchTool:
    """
    Uses Bilibili's public search API (no authentication required).
    Returns video results with BV IDs, play counts, etc.
    """

    SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com",
        "Origin": "https://www.bilibili.com",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    def __init__(self):
        self._last_call: float = 0.0
        self._session = httpx.Client(headers=self.HEADERS, timeout=15, follow_redirects=True)
        self._init_cookies()

    def _init_cookies(self) -> None:
        """Hit Bilibili homepage + SPI endpoint to acquire session cookies (buvid3/buvid4)."""
        try:
            self._session.get("https://www.bilibili.com")

            spi_resp = self._session.get(
                "https://api.bilibili.com/x/frontend/finger/spi"
            )
            if spi_resp.status_code == 200:
                spi_data = spi_resp.json()
                if spi_data.get("code") == 0 and spi_data.get("data"):
                    b3 = spi_data["data"].get("b_3", "")
                    b4 = spi_data["data"].get("b_4", "")
                    if b3:
                        self._session.cookies.set("buvid3", b3, domain=".bilibili.com")
                    if b4:
                        self._session.cookies.set("buvid4", b4, domain=".bilibili.com")

            logger.info("Bilibili cookies initialized: %s",
                        list(self._session.cookies.keys()))
        except Exception as e:
            logger.warning("Failed to init Bilibili cookies: %s", e)

    def __del__(self):
        try:
            self._session.close()
        except Exception:
            pass

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < BILIBILI_RATE_LIMIT:
            time.sleep(BILIBILI_RATE_LIMIT - elapsed)
        self._last_call = time.time()

    @staticmethod
    def _clean(text: str) -> str:
        """Strip Bilibili search highlight tags."""
        return re.sub(r"<[^>]+>", "", text).strip()

    def search(self, keyword: str, page: int = 1) -> list[dict]:
        """
        Returns list of Bilibili video dicts:
          title, url, bvid, play_count, author, description, published_at, duration, verified=None
        """
        return self._do_search(keyword, page, retry=True)

    def _do_search(self, keyword: str, page: int, retry: bool = True) -> list[dict]:
        self._rate_limit()
        params = {
            "keyword": keyword,
            "search_type": "video",
            "page": page,
            "pagesize": BILIBILI_PAGE_SIZE,
            "order": "totalrank",
        }

        try:
            resp = self._session.get(self.SEARCH_URL, params=params)
        except Exception as e:
            logger.error(f"Bilibili search error for '{keyword}': {e}")
            return []

        if resp.status_code == 412 and retry:
            logger.warning("Bilibili 412 Precondition Failed, refreshing cookies...")
            self._init_cookies()
            time.sleep(3)
            return self._do_search(keyword, page, retry=False)

        if resp.status_code != 200:
            logger.warning("Bilibili HTTP %d for '%s'", resp.status_code, keyword)
            return []

        try:
            data = resp.json()
        except Exception as e:
            logger.error("Bilibili JSON parse error for '%s': %s", keyword, e)
            return []

        if data.get("code") == -352 and retry:
            logger.warning("Bilibili risk control (-352), refreshing session...")
            self._init_cookies()
            time.sleep(3)
            return self._do_search(keyword, page, retry=False)

        if data.get("code") != 0:
            logger.warning(f"Bilibili returned code {data.get('code')}: {data.get('message')}")
            return []

        results = []
        for item in data.get("data", {}).get("result", []):
            bvid = item.get("bvid", "")
            if not bvid:
                continue

            pubdate = item.get("pubdate", 0)
            published_str = (
                datetime.fromtimestamp(pubdate).strftime("%Y-%m-%d")
                if pubdate
                else ""
            )

            results.append(
                {
                    "title": self._clean(item.get("title", "")),
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "bvid": bvid,
                    "play_count": item.get("play", 0),
                    "author": item.get("author", ""),
                    "description": self._clean(item.get("description", ""))[:250],
                    "published_at": published_str,
                    "duration": item.get("duration", ""),
                    "verified": None,
                }
            )

        logger.info(f"Bilibili '{keyword}' p{page} → {len(results)} results")
        return results


# ---------------------------------------------------------------------------
# URL Verifier
# ---------------------------------------------------------------------------

class URLVerifier:
    """
    Verifies accessibility of URLs via HTTP.

    Strategy:
    - YouTube URLs: already verified by the Data API; mark as True immediately.
    - Bilibili & others: HTTP HEAD → fallback to GET Range if 405.
    - Retry once on transient failures.
    """

    BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    BILIBILI_HEADERS = {
        **BROWSER_HEADERS,
        "Referer": "https://www.bilibili.com",
    }

    VALID_STATUS = {200, 206, 301, 302, 303, 307, 308}

    def verify(self, urls: list[str]) -> dict[str, dict]:
        """
        Returns {url: {"valid": bool, "status": int, "note": str}}
        """
        results: dict[str, dict] = {}

        for url in urls:
            if not url or not url.startswith("http"):
                results[url] = {"valid": False, "status": 0, "note": "invalid URL format"}
                continue

            # YouTube: trusted from API
            if "youtube.com/watch" in url or "youtu.be/" in url:
                results[url] = {"valid": True, "status": 200, "note": "YouTube API verified"}
                continue

            # All others: HTTP check
            headers = self.BILIBILI_HEADERS if "bilibili.com" in url else self.BROWSER_HEADERS
            results[url] = self._check(url, headers)

        valid_count = sum(1 for v in results.values() if v["valid"])
        logger.info(f"Verified {len(urls)} URLs → {valid_count} valid")
        return results

    def _check(self, url: str, headers: dict, attempt: int = 0) -> dict:
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=VERIFY_TIMEOUT,
                headers=headers,
            ) as client:
                resp = client.head(url)

                if resp.status_code == 405:
                    # Server doesn't allow HEAD — try minimal GET
                    resp = client.get(
                        url,
                        headers={**headers, "Range": "bytes=0-1023"},
                    )

                valid = resp.status_code in self.VALID_STATUS
                return {
                    "valid": valid,
                    "status": resp.status_code,
                    "note": "" if valid else f"HTTP {resp.status_code}",
                }

        except httpx.TimeoutException:
            if attempt < VERIFY_MAX_RETRIES:
                time.sleep(1)
                return self._check(url, headers, attempt + 1)
            return {"valid": False, "status": 0, "note": "timeout"}

        except Exception as e:
            return {"valid": False, "status": 0, "note": str(e)[:80]}
