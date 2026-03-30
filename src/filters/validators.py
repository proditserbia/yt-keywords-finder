"""
Validation and filtering helpers used by the core processor.

All functions here are pure (no side effects) so they are easy to unit-test
and reuse across both CLI and GUI frontends.
"""

import re
from typing import Optional

from src.config.constants import MAX_FILENAME_LENGTH


def is_valid_duration(
    duration_seconds: Optional[float],
    min_duration_seconds: float,
) -> bool:
    """Return True when *duration_seconds* meets the minimum threshold.

    Videos with unknown duration (None) are always excluded so that live
    streams or unavailable metadata do not slip through.

    Args:
        duration_seconds: Actual video duration in seconds, or None.
        min_duration_seconds: Required minimum duration in seconds.

    Returns:
        True if the video should be included, False otherwise.
    """
    if duration_seconds is None:
        return False
    return float(duration_seconds) >= min_duration_seconds


def sanitize_filename(name: str) -> str:
    """Convert *name* into a string that is safe to use as a file/folder name.

    Characters that are illegal on Windows, macOS, or Linux are replaced with
    underscores.  Leading/trailing dots and spaces (problematic on Windows) are
    stripped.  The result is capped at ``MAX_FILENAME_LENGTH`` characters to
    stay within common filesystem limits.

    Args:
        name: Raw string to sanitize (e.g., a keyword entered by the user).

    Returns:
        A filesystem-safe filename string.  Falls back to ``'unnamed'`` when
        the sanitized result is empty.
    """
    # Replace characters that are forbidden in filenames on most operating systems
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    # Strip leading/trailing whitespace and dots
    sanitized = sanitized.strip(". ")
    # Collapse multiple consecutive underscores for readability
    sanitized = re.sub(r"_+", "_", sanitized)
    # Enforce length limit
    sanitized = sanitized[:MAX_FILENAME_LENGTH]
    return sanitized or "unnamed"


def seconds_to_human(seconds: float) -> str:
    """Convert a duration in seconds to a human-readable ``HH:MM:SS`` string.

    Args:
        seconds: Duration in seconds (may be a float).

    Returns:
        Formatted string, e.g. ``'1:23:45'`` or ``'5:30'``.
    """
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_keywords(raw: str) -> list[str]:
    """Split a raw multi-line or comma-separated string into individual keywords.

    Blank lines and surrounding whitespace are stripped.  Duplicate keywords
    (case-insensitive) are removed while preserving insertion order.

    Args:
        raw: User-supplied text, e.g. ``'fashion street\\nrunway\\nsummer outfits'``.

    Returns:
        Ordered list of unique, non-empty keyword strings.
    """
    seen: set[str] = set()
    keywords: list[str] = []
    for line in raw.splitlines():
        # Also split by comma to support "kw1, kw2" style input
        for part in line.split(","):
            kw = part.strip()
            if kw and kw.lower() not in seen:
                seen.add(kw.lower())
                keywords.append(kw)
    return keywords
