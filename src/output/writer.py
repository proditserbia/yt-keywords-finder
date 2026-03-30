"""
Output writers for TXT and CSV result files.

Each function is independent and raises on genuine I/O errors so callers
(the core processor) can log and continue processing other keywords.
"""

import csv
import logging
import os
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


def ensure_output_dir(output_dir: str | Path) -> Path:
    """Create *output_dir* (and any parents) if it does not already exist.

    Args:
        output_dir: Path to the desired output directory.

    Returns:
        A resolved :class:`pathlib.Path` object pointing to the directory.
    """
    path = Path(output_dir).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_txt(filepath: str | Path, urls: Sequence[str]) -> None:
    """Write one URL per line to *filepath*.

    Existing content is overwritten.

    Args:
        filepath: Destination file path.
        urls: Ordered sequence of video URL strings.
    """
    path = Path(filepath)
    with path.open("w", encoding="utf-8") as fh:
        for url in urls:
            fh.write(url + "\n")
    logger.info("Saved %d URL(s) to %s", len(urls), path)


def append_txt(filepath: str | Path, urls: Sequence[str]) -> None:
    """Append URLs to *filepath*, creating the file if necessary.

    Args:
        filepath: Destination file path.
        urls: Ordered sequence of video URL strings.
    """
    path = Path(filepath)
    with path.open("a", encoding="utf-8") as fh:
        for url in urls:
            fh.write(url + "\n")
    logger.debug("Appended %d URL(s) to %s", len(urls), path)


CSV_FIELDNAMES = ["keyword", "title", "url", "duration_seconds", "duration_human", "channel"]


def save_csv(filepath: str | Path, rows: list[dict], mode: str = "a") -> None:
    """Write *rows* to a CSV file at *filepath*.

    When *mode* is ``'a'`` (append, the default) a header is written only when
    the file does not yet exist.  Pass ``mode='w'`` to always (over)write with
    a fresh header.

    Args:
        filepath: Destination CSV file path.
        rows: List of dicts with keys matching :data:`CSV_FIELDNAMES`.
        mode: File open mode – ``'a'`` to append, ``'w'`` to overwrite.
    """
    path = Path(filepath)
    write_header = mode == "w" or not path.exists()

    with path.open(mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=CSV_FIELDNAMES,
            extrasaction="ignore",
        )
        if write_header:
            writer.writeheader()
        writer.writerows(rows)

    logger.info("Saved %d row(s) to CSV %s", len(rows), path)
