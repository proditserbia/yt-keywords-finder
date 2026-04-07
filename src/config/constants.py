"""
Application-wide constants and default configuration values.

These values serve as defaults and can be overridden via CLI arguments,
GUI input fields, or a future config file.
"""

APP_NAME = "YT Keywords Finder"
VERSION = "1.0.0"

# ── Search defaults ────────────────────────────────────────────────────────────
DEFAULT_MAX_RESULTS: int = 50       # maximum valid URLs to collect per keyword
DEFAULT_MIN_DURATION: int = 0       # minimum video duration in minutes (0 = no filter)

# ── Output defaults ────────────────────────────────────────────────────────────
DEFAULT_OUTPUT_DIR: str = "./results"
LOG_FILENAME: str = "yt_finder.log"
SUMMARY_CSV_FILENAME: str = "all_keywords_summary.csv"
ALL_KEYWORDS_TXT_FILENAME: str = "all_keywords.txt"

# ── Download defaults ──────────────────────────────────────────────────────────
DEFAULT_DOWNLOAD_DIR: str = "./downloads"
# JSON sidecar that tracks already-downloaded video IDs per keyword folder.
DOWNLOAD_HISTORY_FILENAME: str = ".download_history.json"

# ── yt-dlp tuning ─────────────────────────────────────────────────────────────
# How many results to request from YouTube per search page.
# We multiply the requested count to compensate for filtered-out short videos.
SEARCH_OVERFETCH_MULTIPLIER: int = 3
# Hard cap on how many results we fetch from YouTube to avoid very long runs.
SEARCH_MAX_FETCH: int = 500

# ── Filename sanitization ──────────────────────────────────────────────────────
MAX_FILENAME_LENGTH: int = 100
