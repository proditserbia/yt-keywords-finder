"""
YouTube search service backed by yt-dlp.

This module is the only place in the codebase that talks to YouTube.  Swapping
it out (or adding a parallel Vimeo service) requires changes only here and in
``src/core/processor.py`` where the service is instantiated.
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Generator, Optional

import yt_dlp

from src.config.constants import SEARCH_MAX_FETCH, SEARCH_OVERFETCH_MULTIPLIER
from src.filters.validators import is_valid_duration

logger = logging.getLogger(__name__)


@dataclass
class VideoInfo:
    """Metadata for a single YouTube video."""

    url: str
    title: str
    duration_seconds: float
    channel: str
    video_id: str = field(default="")


class YouTubeSearchService:
    """Search YouTube for videos matching a keyword using yt-dlp.

    Designed to be platform-agnostic: the same instance can be used from both
    the CLI and the GUI without modification.

    This service can be replaced by a ``VimeoSearchService`` (or any other
    platform) as long as the replacement exposes the same ``search()`` method
    signature.
    """

    def search(
        self,
        keyword: str,
        max_results: int,
        min_duration_seconds: float = 0.0,
        published_within_days: Optional[int] = None,
        cancel_flag: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Generator[VideoInfo, None, None]:
        """Yield up to *max_results* public YouTube videos matching *keyword*.

        Videos shorter than *min_duration_seconds* are silently skipped.
        Live streams (duration == 0 or None) are also excluded.

        Args:
            keyword: Search term to query YouTube with.
            max_results: Maximum number of valid results to yield.
            min_duration_seconds: Minimum video duration in seconds (0 = no filter).
            published_within_days: When set, only videos uploaded within the last
                N days are included.  Uses the ``timestamp`` field returned by the
                flat search extraction; entries without a timestamp pass through.
            cancel_flag: Optional :class:`threading.Event`.  When set, the
                generator stops early so GUI/CLI runs can be cancelled.
            progress_callback: Optional callable ``(message: str) -> None``
                called with human-readable status updates during the search.

        Yields:
            :class:`VideoInfo` instances for each qualifying video.
        """
        if max_results <= 0:
            return

        # Request more results than needed to compensate for filtered-out videos
        fetch_count = min(max_results * SEARCH_OVERFETCH_MULTIPLIER, SEARCH_MAX_FETCH)

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,   # fast metadata-only extraction
            "ignoreerrors": True,   # skip unavailable/private videos
        }

        search_url = f"ytsearch{fetch_count}:{keyword}"

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(search_url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            logger.error("yt-dlp error while searching '%s': %s", keyword, exc)
            return
        except Exception as exc:  # pragma: no cover – network errors in prod
            logger.error("Unexpected error while searching '%s': %s", keyword, exc)
            return

        if not result or "entries" not in result:
            logger.warning("No results returned for keyword: '%s'", keyword)
            return

        collected = 0
        seen_ids: set[str] = set()

        for entry in result["entries"] or []:
            # Respect cancellation
            if cancel_flag and cancel_flag.is_set():
                logger.info("Search cancelled by user after %d results.", collected)
                return

            if collected >= max_results:
                return

            if not entry:
                continue

            video_id = entry.get("id") or entry.get("url", "")
            if not video_id:
                continue

            # Duplicate guard
            if video_id in seen_ids:
                continue
            seen_ids.add(video_id)

            # Date filter – uses the Unix timestamp returned by flat extraction.
            # If the field is absent, the video passes through (best-effort filter).
            if published_within_days is not None and published_within_days > 0:
                timestamp: Optional[float] = entry.get("timestamp")
                if timestamp is not None:
                    cutoff = (
                        datetime.now(tz=timezone.utc) - timedelta(days=published_within_days)
                    ).timestamp()
                    if timestamp < cutoff:
                        logger.debug(
                            "Skipped '%s' (timestamp %s before %d-day cutoff)",
                            entry.get("title", ""),
                            timestamp,
                            published_within_days,
                        )
                        continue

            # Build canonical video URL
            url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
            if not url.startswith("http"):
                url = f"https://www.youtube.com/watch?v={video_id}"

            title: str = entry.get("title") or "Unknown Title"
            duration: Optional[float] = entry.get("duration")
            channel: str = (
                entry.get("channel")
                or entry.get("uploader")
                or entry.get("uploader_id")
                or "Unknown Channel"
            )

            # Skip live streams and entries without duration metadata
            if not is_valid_duration(duration, min_duration_seconds):
                logger.debug(
                    "Skipped '%s' (duration=%s, min=%s)", title, duration, min_duration_seconds
                )
                if progress_callback:
                    progress_callback(
                        f"  Skipped: {title!r} (duration {duration}s < {min_duration_seconds}s)"
                    )
                continue

            collected += 1
            logger.debug("Accepted [%d/%d] %s", collected, max_results, title)

            yield VideoInfo(
                url=url,
                title=title,
                duration_seconds=float(duration),
                channel=channel,
                video_id=video_id,
            )
