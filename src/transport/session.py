"""
Transport / session configuration for yt-dlp operations.

:class:`SessionConfig` is the single place that holds cookies and proxy
settings.  Both :class:`~src.youtube.search_service.YouTubeSearchService` and
:class:`~src.youtube.downloader.VideoDownloader` accept an optional
``SessionConfig`` instance and merge it into their yt-dlp option dicts.

Design notes:
- Cookies and proxy are both *optional*.  The app works without either.
- ``as_ydl_opts()`` returns a plain dict that can be merged with any yt-dlp
  options dict via ``opts.update(session.as_ydl_opts())``.
- Adding a rotating-proxy layer later only requires changing this module
  (e.g., a ``next_proxy()`` method or a list of proxies) without touching
  the search or download modules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionConfig:
    """Holds cookies and proxy settings used by yt-dlp.

    Args:
        cookies_file: Path to a Netscape-format cookies.txt file.
            Passed to yt-dlp as ``cookiefile``.  ``None`` means no cookies.
        proxy: Proxy URL string, e.g. ``"http://host:port"``,
            ``"socks5://host:port"``.  Passed to yt-dlp as ``proxy``.
            ``None`` means no proxy (direct connection).
    """

    cookies_file: Optional[str] = field(default=None)
    proxy: Optional[str] = field(default=None)

    # ── Validation ────────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        if self.cookies_file is not None:
            p = Path(self.cookies_file)
            if not p.exists():
                logger.warning(
                    "Cookies file not found: %s – continuing without cookies.", p
                )
                self.cookies_file = None

    # ── yt-dlp integration ────────────────────────────────────────────────────

    def as_ydl_opts(self) -> dict:
        """Return a yt-dlp options dict fragment for cookies and proxy.

        The returned dict is intended to be merged into a larger yt-dlp
        options dict::

            opts = {"quiet": True, ...}
            opts.update(session.as_ydl_opts())

        Returns:
            Dict with zero, one, or both of ``cookiefile`` and ``proxy``
            set, depending on which fields are configured.
        """
        opts: dict = {}
        if self.cookies_file:
            opts["cookiefile"] = self.cookies_file
        if self.proxy:
            opts["proxy"] = self.proxy
        return opts

    # ── Human-readable description ────────────────────────────────────────────

    def describe(self) -> str:
        """Return a short human-readable summary of the active transport config.

        Used in log messages so operators can confirm which cookies/proxy are
        in effect at runtime.

        Returns:
            String such as ``"cookies=cookies.txt, proxy=socks5://..."``
            or ``"no cookies, no proxy"``.
        """
        parts: list[str] = []
        if self.cookies_file:
            parts.append(f"cookies={self.cookies_file}")
        else:
            parts.append("no cookies")
        if self.proxy:
            parts.append(f"proxy={self.proxy}")
        else:
            parts.append("no proxy")
        return ", ".join(parts)
