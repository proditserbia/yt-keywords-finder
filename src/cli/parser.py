"""
CLI argument parser and entry-point for headless operation.

Usage examples::

    python app.py --mode cli --keywords "fashion street,runway" \\
                  --max-results 100 --min-duration 5 --output ./results

    python app.py --mode cli --keywords-file keywords.txt \\
                  --max-results 50 --min-duration 3 --output ./results
"""

import argparse
import logging
import sys
from pathlib import Path

from src.config.constants import (
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_MAX_RESULTS,
    DEFAULT_MIN_DURATION,
    DEFAULT_OUTPUT_DIR,
)
from src.core.processor import process_keywords, setup_logging
from src.filters.validators import parse_keywords

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Create and return the CLI argument parser.

    Returns:
        Configured :class:`argparse.ArgumentParser` instance.
    """
    parser = argparse.ArgumentParser(
        prog="yt-keywords-finder",
        description=(
            "Search YouTube by keyword and save matching video URLs to text files. "
            "Optionally download the matching videos with --download."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Search only – collect up to 10 results per keyword from the last year
  python app.py --mode cli --keywords "fashion street,runway" \\
                --max-results 10 --min-duration 5 --output ./results

  # Search + download videos longer than 60 minutes published in the last year
  python app.py --mode cli --keywords "documentary nature" \\
                --max-results 5 --min-duration 60 \\
                --published-within-days 365 \\
                --download --download-dir ./videos

  python app.py --mode cli --keywords-file keywords.txt \\
                --max-results 50  --min-duration 3  --output ./results
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["cli", "gui"],
        default="gui",
        help="Run in headless CLI mode or launch the Tkinter GUI (default: gui).",
    )

    # ── Keyword input (mutually exclusive) ──────────────────────────────────
    kw_group = parser.add_mutually_exclusive_group()
    kw_group.add_argument(
        "--keywords",
        metavar="KEYWORD_LIST",
        help='Comma- or newline-separated list of keywords (e.g. "fashion,runway").',
    )
    kw_group.add_argument(
        "--keywords-file",
        metavar="FILE",
        help="Path to a plain-text file with one keyword per line.",
    )

    # ── Search parameters ────────────────────────────────────────────────────
    parser.add_argument(
        "--max-results",
        type=int,
        default=DEFAULT_MAX_RESULTS,
        metavar="N",
        help=f"Maximum valid URLs to collect per keyword (default: {DEFAULT_MAX_RESULTS}).",
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=DEFAULT_MIN_DURATION,
        metavar="MINUTES",
        help=f"Minimum video duration in minutes (default: {DEFAULT_MIN_DURATION} = no filter).",
    )
    parser.add_argument(
        "--published-within-days",
        type=int,
        default=None,
        metavar="DAYS",
        help=(
            "Only include videos published within the last N days "
            "(e.g. 365 for one year, 90 for last 3 months). "
            "Default: no date filter."
        ),
    )

    # ── Output options ───────────────────────────────────────────────────────
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_DIR,
        metavar="DIR",
        help=f"Directory where result files are written (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Disable CSV summary output.",
    )
    parser.add_argument(
        "--no-combined-txt",
        action="store_true",
        help="Disable writing all_keywords.txt combined file.",
    )

    # ── Download options ─────────────────────────────────────────────────────
    parser.add_argument(
        "--download",
        action="store_true",
        help=(
            "Download each matching video after the search/filter phase. "
            "Videos are saved to sub-folders of --download-dir named after each keyword."
        ),
    )
    parser.add_argument(
        "--download-dir",
        default=DEFAULT_DOWNLOAD_DIR,
        metavar="DIR",
        help=(
            f"Root directory for downloaded videos (default: {DEFAULT_DOWNLOAD_DIR}). "
            "A sub-folder is created per keyword."
        ),
    )

    # ── Misc ─────────────────────────────────────────────────────────────────
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging to the console.",
    )

    return parser


def load_keywords_from_file(filepath: str) -> list[str]:
    """Read keywords from a plain-text file (one per line).

    Args:
        filepath: Path to the keywords file.

    Returns:
        Parsed list of keyword strings.

    Raises:
        SystemExit: If the file cannot be read.
    """
    path = Path(filepath)
    if not path.exists():
        print(f"Error: keywords file not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error reading keywords file: {exc}", file=sys.stderr)
        sys.exit(1)
    return parse_keywords(text)


def run_cli(args: argparse.Namespace) -> None:
    """Execute the CLI workflow using parsed *args*.

    Args:
        args: Parsed namespace from :func:`build_parser`.
    """
    setup_logging(args.output, verbose=args.verbose)

    # ── Resolve keywords ─────────────────────────────────────────────────────
    if args.keywords_file:
        keywords = load_keywords_from_file(args.keywords_file)
    elif args.keywords:
        keywords = parse_keywords(args.keywords)
    else:
        print(
            "Error: supply keywords via --keywords or --keywords-file.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not keywords:
        print("Error: no valid keywords found.", file=sys.stderr)
        sys.exit(1)

    # ── Validate numeric arguments ───────────────────────────────────────────
    if args.max_results <= 0:
        print("Error: --max-results must be a positive integer.", file=sys.stderr)
        sys.exit(1)
    if args.min_duration < 0:
        print("Error: --min-duration cannot be negative.", file=sys.stderr)
        sys.exit(1)

    process_keywords(
        keywords=keywords,
        max_results=args.max_results,
        min_duration_minutes=args.min_duration,
        output_dir=args.output,
        create_csv=not args.no_csv,
        create_combined_txt=not args.no_combined_txt,
        download_videos=args.download,
        download_dir=args.download_dir,
        published_within_days=args.published_within_days,
    )
