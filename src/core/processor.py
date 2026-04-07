"""
Core processing logic shared by CLI and GUI frontends.

Neither the CLI parser nor the GUI widget imports each other: both call
``process_keywords()`` from this module.  This keeps the business logic in one
place and makes it trivial to add further frontends (e.g., a web API) later.

To add Vimeo support:
    1. Create ``src/vimeo/search_service.py`` with the same ``search()`` API
       as :class:`~src.youtube.search_service.YouTubeSearchService`.
    2. Accept a ``platform`` parameter in :func:`process_keywords` and
       instantiate the appropriate service.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable, Optional

from src.config.constants import (
    ALL_KEYWORDS_TXT_FILENAME,
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_MAX_RESULTS,
    DEFAULT_MIN_DURATION,
    DEFAULT_OUTPUT_DIR,
    LOG_FILENAME,
    SUMMARY_CSV_FILENAME,
)
from src.filters.validators import sanitize_filename, seconds_to_human
from src.output.writer import (
    append_txt,
    ensure_output_dir,
    save_csv,
    save_txt,
)
from src.youtube.downloader import VideoDownloader
from src.youtube.search_service import VideoInfo, YouTubeSearchService

logger = logging.getLogger(__name__)


def setup_logging(output_dir: str | Path, verbose: bool = False) -> None:
    """Configure the root logger to write to both console and a log file.

    Safe to call multiple times; duplicate handlers are avoided.

    Args:
        output_dir: Directory where the log file will be written.
        verbose: When True, sets the console handler to DEBUG level.
    """
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s – %(message)s")

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # File handler
    log_path = Path(output_dir) / LOG_FILENAME
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as exc:
        logger.warning("Could not create log file at %s: %s", log_path, exc)


def process_keywords(
    keywords: list[str],
    max_results: int = DEFAULT_MAX_RESULTS,
    min_duration_minutes: float = DEFAULT_MIN_DURATION,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    create_csv: bool = True,
    create_combined_txt: bool = True,
    download_videos: bool = False,
    download_dir: str = DEFAULT_DOWNLOAD_DIR,
    published_within_days: Optional[int] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    cancel_flag: Optional[threading.Event] = None,
) -> dict[str, list[str]]:
    """Search YouTube for each keyword and write results to disk.

    This function is the single entry-point for all processing work, shared
    between the CLI and the GUI.  It is designed to run inside a background
    thread when called from the GUI.

    Args:
        keywords: List of search terms.
        max_results: Maximum number of valid URLs to collect per keyword.
        min_duration_minutes: Minimum video duration in minutes.
            ``0`` means no filter.
        output_dir: Folder where output files will be written.
        create_csv: When True, a CSV summary file is written/appended.
        create_combined_txt: When True, all URLs are also appended to a
            combined ``all_keywords.txt`` file.
        download_videos: When True, each matching video is downloaded into a
            sub-folder of *download_dir* named after the keyword.
        download_dir: Root folder for downloaded video files.  A sub-folder
            is created per keyword (e.g., ``downloads/fashion_street/``).
        published_within_days: When set, only videos uploaded within the
            last N days are included in search results.  ``None`` means no
            date filter.
        log_callback: Optional function ``(message: str) -> None`` called
            for every log/progress message.  Used by the GUI to update its
            log widget in real time.
        cancel_flag: Optional :class:`threading.Event`.  When set, processing
            stops after the current keyword finishes.

    Returns:
        Dict mapping each keyword to the list of collected video URLs.
    """
    out_dir = ensure_output_dir(output_dir)
    setup_logging(out_dir)

    min_duration_seconds = min_duration_minutes * 60.0
    service = YouTubeSearchService()

    results: dict[str, list[str]] = {}
    csv_rows: list[dict] = []

    def _log(msg: str) -> None:
        logger.info(msg)
        if log_callback:
            log_callback(msg)

    date_note = (
        f", published within last {published_within_days} days"
        if published_within_days
        else ""
    )
    _log(
        f"Starting search for {len(keywords)} keyword(s) → output: {out_dir}"
        + date_note
    )

    for idx, keyword in enumerate(keywords, start=1):
        if cancel_flag and cancel_flag.is_set():
            _log("Processing cancelled by user.")
            break

        _log(f"\n[{idx}/{len(keywords)}] Searching: '{keyword}'")

        urls: list[str] = []
        seen_urls: set[str] = set()
        video_infos: list[VideoInfo] = []

        try:
            for video in service.search(
                keyword=keyword,
                max_results=max_results,
                min_duration_seconds=min_duration_seconds,
                published_within_days=published_within_days,
                cancel_flag=cancel_flag,
                progress_callback=_log,
            ):
                if cancel_flag and cancel_flag.is_set():
                    break

                if video.url in seen_urls:
                    continue
                seen_urls.add(video.url)

                urls.append(video.url)
                video_infos.append(video)
                _log(
                    f"  [{len(urls)}/{max_results}] {video.title} "
                    f"({seconds_to_human(video.duration_seconds)}) – {video.channel}"
                )

                if create_csv:
                    csv_rows.append(
                        {
                            "keyword": keyword,
                            "title": video.title,
                            "url": video.url,
                            "duration_seconds": int(video.duration_seconds),
                            "duration_human": seconds_to_human(video.duration_seconds),
                            "channel": video.channel,
                        }
                    )

        except Exception as exc:
            _log(f"  ERROR processing keyword '{keyword}': {exc}")
            logger.exception("Unhandled error for keyword '%s'", keyword)
            # Continue with next keyword – do not crash the whole run.

        results[keyword] = urls
        _log(f"  Collected {len(urls)} URL(s) for '{keyword}'")

        if urls:
            safe_name = sanitize_filename(keyword)
            txt_path = out_dir / f"{safe_name}.txt"
            try:
                save_txt(txt_path, urls)
                _log(f"  Saved: {txt_path}")
            except OSError as exc:
                _log(f"  ERROR saving {txt_path}: {exc}")

        # ── Download phase for this keyword ──────────────────────────────────
        if download_videos and video_infos:
            safe_name = sanitize_filename(keyword)
            kw_dl_dir = ensure_output_dir(Path(download_dir) / safe_name)
            downloader = VideoDownloader(kw_dl_dir, log_callback=_log)

            _log(
                f"  Downloading {len(video_infos)} video(s) → {kw_dl_dir}"
            )
            dl_ok = dl_fail = 0
            for video in video_infos:
                if cancel_flag and cancel_flag.is_set():
                    _log("  Download cancelled by user.")
                    break
                if downloader.download(video):
                    dl_ok += 1
                else:
                    dl_fail += 1

            _log(
                f"  Download results for '{keyword}': "
                f"{dl_ok} succeeded, {dl_fail} failed"
            )

        if cancel_flag and cancel_flag.is_set():
            _log("Processing cancelled by user.")
            break

    # ── Combined outputs ────────────────────────────────────────────────────
    if create_combined_txt:
        all_urls = [url for keyword_urls in results.values() for url in keyword_urls]
        if all_urls:
            combined_path = out_dir / ALL_KEYWORDS_TXT_FILENAME
            try:
                append_txt(combined_path, all_urls)
                _log(f"\nCombined TXT saved: {combined_path}")
            except OSError as exc:
                _log(f"ERROR saving combined TXT: {exc}")

    if create_csv and csv_rows:
        csv_path = out_dir / SUMMARY_CSV_FILENAME
        try:
            save_csv(csv_path, csv_rows)
            _log(f"CSV summary saved: {csv_path}")
        except OSError as exc:
            _log(f"ERROR saving CSV: {exc}")

    total = sum(len(v) for v in results.values())
    _log(f"\nDone. Total URLs collected: {total}")

    return results
