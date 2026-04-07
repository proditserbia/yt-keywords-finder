#!/usr/bin/env python3
"""
tools/fetch_cookies.py – generate an anonymous YouTube cookies.txt on a
headless / CLI-only Linux server (no browser required).

This script makes a plain HTTPS request to youtube.com and saves the
Set-Cookie headers in Netscape format that yt-dlp understands via its
``--cookies`` / ``cookiefile`` option.

The cookies obtained are *anonymous visitor cookies* (no Google account).
They are sufficient to satisfy YouTube's CONSENT gate and supply a fresh
``VISITOR_INFO1_LIVE`` value, which helps with some IP-based restrictions.

For full bypass of data-centre IP blocks you may still need either:
  1. Logged-in Google cookies (export from a browser on another machine and
     scp the file to this server), or
  2. The --extractor-args workaround (tv_embedded client, see README).

Usage::

    python tools/fetch_cookies.py                        # saves cookies.txt
    python tools/fetch_cookies.py --output ~/my.txt      # custom path
    python tools/fetch_cookies.py --verbose              # show received cookies

Dependencies: Python standard library only (urllib, http.cookiejar).
"""

from __future__ import annotations

import argparse
import http.cookiejar
import logging
import sys
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

YOUTUBE_URL = "https://www.youtube.com/"
DEFAULT_OUTPUT = "cookies.txt"

# A realistic browser User-Agent so YouTube returns its full cookie set.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Cookies YouTube sets that are useful to capture.
INTERESTING_COOKIES = {
    "VISITOR_INFO1_LIVE",
    "VISITOR_PRIVACY_METADATA",
    "YSC",
    "CONSENT",
    "SOCS",
    "__Secure-YEC",
}


def _build_opener(jar: http.cookiejar.CookieJar) -> urllib.request.OpenerDirector:
    """Return an opener with cookie support and a browser-like User-Agent."""
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", USER_AGENT),
        ("Accept-Language", "en-US,en;q=0.9"),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
    ]
    return opener


def fetch_youtube_cookies(verbose: bool = False) -> http.cookiejar.MozillaCookieJar:
    """Fetch YouTube and capture the visitor cookies it sets.

    Args:
        verbose: When True, log each received cookie to stderr.

    Returns:
        A :class:`http.cookiejar.MozillaCookieJar` populated with the cookies
        received from youtube.com.

    Raises:
        SystemExit: On network errors.
    """
    jar: http.cookiejar.MozillaCookieJar = http.cookiejar.MozillaCookieJar()
    opener = _build_opener(jar)

    logger.info("Fetching %s …", YOUTUBE_URL)
    try:
        with opener.open(YOUTUBE_URL, timeout=15) as resp:
            _ = resp.read(4096)  # read enough to trigger cookie parsing
    except OSError as exc:
        print(f"Error: could not reach {YOUTUBE_URL}: {exc}", file=sys.stderr)
        sys.exit(1)

    if verbose:
        for cookie in jar:
            logger.debug("  %-40s = %s", cookie.name, cookie.value)

    return jar


def save_netscape(jar: http.cookiejar.MozillaCookieJar, output_path: Path) -> None:
    """Save *jar* in Netscape/Mozilla format to *output_path*.

    Args:
        jar: Populated cookie jar.
        output_path: Destination file path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    jar.save(str(output_path), ignore_discard=True, ignore_expires=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="fetch_cookies",
        description=(
            "Fetch anonymous YouTube visitor cookies and save them as "
            "cookies.txt (Netscape format) for use with yt-dlp / "
            "yt-keywords-finder --cookies-file."
        ),
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        metavar="FILE",
        help=f"Path to write the Netscape cookies file (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show each cookie received from YouTube.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )

    jar = fetch_youtube_cookies(verbose=args.verbose)

    found = [c.name for c in jar if c.name in INTERESTING_COOKIES]
    if not found:
        print(
            "Warning: no known visitor cookies were set by YouTube. "
            "The saved file may be empty or unhelpful.",
            file=sys.stderr,
        )

    output_path = Path(args.output)
    save_netscape(jar, output_path)

    total = sum(1 for _ in jar)
    print(f"Saved {total} cookie(s) to {output_path}")
    if found:
        print(f"Captured: {', '.join(found)}")

    print()
    print("Next step – use with yt-keywords-finder:")
    print(
        f"  python app.py --mode cli --keywords \"your keyword\" "
        f"--cookies-file {output_path}"
    )
    print()
    print(
        "Note: these are anonymous visitor cookies (no Google login). "
        "If YouTube still blocks requests from this server's IP, also try:"
    )
    print(
        '  --extractor-args "youtube:player_client=tv_embedded"'
    )
    print(
        "  or export logged-in cookies from a browser on another machine "
        "and scp them here."
    )

    # Warn if cookies are likely to expire soon (MozillaCookieJar sets
    # expires=0 for session cookies, which means they won't survive a reboot).
    session_cookies = [c.name for c in jar if not c.expires]
    if session_cookies:
        print()
        print(
            f"Note: {len(session_cookies)} session cookie(s) have no expiry "
            "date and will be treated as expired by some yt-dlp versions. "
            "Re-run this script periodically to refresh them."
        )


if __name__ == "__main__":
    main()
