"""
Video downloader backed by yt-dlp.

Handles downloading individual videos into a target directory, tracks
already-downloaded video IDs in a JSON sidecar file to avoid duplicate
downloads, and reports per-video success/failure without halting the batch.

The :class:`VideoDownloader` is intentionally stateless with respect to the
search/filter pipeline: it only cares about a ``VideoInfo`` object and a
download directory.  This keeps it easy to reuse for future sources (e.g.,
Vimeo) as long as they produce the same ``VideoInfo`` dataclass.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

from src.config.constants import DOWNLOAD_HISTORY_FILENAME
from src.transport.session import SessionConfig
from src.youtube.search_service import VideoInfo

logger = logging.getLogger(__name__)


class VideoDownloader:
    """Download YouTube videos via yt-dlp into a directory.

    Tracks completed downloads in a ``.download_history.json`` sidecar file
    inside the target directory so that re-running the same keyword never
    re-downloads a video that is already present.

    Args:
        download_dir: Directory where videos are saved.
        log_callback: Optional ``(message: str) -> None`` called for every
            progress message.  Uses the same interface as
            :func:`~src.core.processor.process_keywords`.
        session: Optional :class:`~src.transport.session.SessionConfig`
            carrying cookies and proxy settings.
    """

    def __init__(
        self,
        download_dir: Path,
        log_callback: Optional[Callable[[str], None]] = None,
        session: Optional[SessionConfig] = None,
    ) -> None:
        self._dir = Path(download_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._log_callback = log_callback
        self._session = session or SessionConfig()
        self._history_path = self._dir / DOWNLOAD_HISTORY_FILENAME
        self._history: set[str] = self._load_history()

    # ── History helpers ──────────────────────────────────────────────────────

    def _load_history(self) -> set[str]:
        """Load the set of already-downloaded video IDs from disk."""
        if not self._history_path.exists():
            return set()
        try:
            data = json.loads(self._history_path.read_text(encoding="utf-8"))
            return set(data.get("downloaded_ids", []))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Could not load download history from %s: %s", self._history_path, exc
            )
            return set()

    def _save_history(self) -> None:
        """Persist the current history to disk."""
        try:
            self._history_path.write_text(
                json.dumps({"downloaded_ids": sorted(self._history)}, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(
                "Could not save download history to %s: %s", self._history_path, exc
            )

    def is_downloaded(self, video_id: str) -> bool:
        """Return True if *video_id* is already recorded in the history."""
        return video_id in self._history

    def _mark_downloaded(self, video_id: str) -> None:
        self._history.add(video_id)
        self._save_history()

    # ── Public API ───────────────────────────────────────────────────────────

    def download(self, video: VideoInfo) -> bool:
        """Download a single video to :attr:`_dir`.

        Skips the download silently when the video ID is already present in
        the history (duplicate guard).  Any yt-dlp or I/O error is caught and
        logged without raising, so one failed video never stops the batch.

        Args:
            video: A :class:`~src.youtube.search_service.VideoInfo` instance
                describing the video to download.

        Returns:
            ``True`` when the video is available on disk after the call
            (either freshly downloaded or already present), ``False`` on error.
        """
        if not video.video_id:
            self._log(f"  Skipping download – no video_id for {video.url!r}")
            return False

        if self.is_downloaded(video.video_id):
            self._log(f"  Already downloaded: {video.title!r} ({video.video_id})")
            return True

        ydl_opts: dict = {
            # Save as <title> [<id>].<ext> so the file is human-readable and unique.
            "outtmpl": str(self._dir / "%(title)s [%(id)s].%(ext)s"),
            # Prefer MP4 with best quality; fall back gracefully.
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
            # Continue batch on individual errors; yt-dlp still returns non-zero.
            "ignoreerrors": True,
            "noprogress": True,
        }
        ydl_opts.update(self._session.as_ydl_opts())

        self._log(f"  Downloading: {video.title!r} → {self._dir.name}/")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ret = ydl.download([video.url])

            if ret == 0:
                self._mark_downloaded(video.video_id)
                self._log(f"  ✓ Downloaded: {video.title!r}")
                return True
            else:
                self._log(
                    f"  ✗ Download failed (yt-dlp returned {ret}): {video.title!r}"
                )
                return False

        except yt_dlp.utils.DownloadError as exc:
            self._log(f"  ✗ DownloadError for {video.title!r}: {exc}")
            logger.error("DownloadError for %s: %s", video.url, exc)
            return False
        except Exception as exc:  # pragma: no cover – unexpected runtime errors
            self._log(f"  ✗ Unexpected error downloading {video.title!r}: {exc}")
            logger.exception("Unexpected download error for %s", video.url)
            return False

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        logger.info(msg)
        if self._log_callback:
            self._log_callback(msg)
