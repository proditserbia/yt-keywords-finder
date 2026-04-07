"""
Transport / session configuration for yt-dlp operations.

:class:`SessionConfig` is the single place that holds cookies, proxy, and
extractor-args settings.  Both
:class:`~src.youtube.search_service.YouTubeSearchService` and
:class:`~src.youtube.downloader.VideoDownloader` accept an optional
``SessionConfig`` instance and merge it into their yt-dlp option dicts.

Design notes:
- Cookies, proxy, and extractor_args are all *optional*.  The app works
  without any of them.
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


def _parse_extractor_args(args_str: str) -> dict:
    """Parse a yt-dlp extractor-args string into the dict form expected by
    :class:`yt_dlp.YoutubeDL`.

    The accepted format mirrors yt-dlp's ``--extractor-args`` CLI option::

        ie_key:param1=val1a,val1b;param2=val2

    Multiple extractor blocks can be separated by ``&&``::

        youtube:player_client=tv_embedded&&youtube:skip=webpage

    Args:
        args_str: Raw extractor-args string supplied by the user.

    Returns:
        Dict of the form ``{ie_key: {param: [values]}}`` ready to pass as
        yt-dlp's ``extractor_args`` option.  Empty dict on parse failure.
    """
    result: dict = {}
    for block in args_str.split("&&"):
        block = block.strip()
        if not block or ":" not in block:
            continue
        ie_key, _, params_str = block.partition(":")
        ie_key = ie_key.strip().lower()
        params: dict = result.setdefault(ie_key, {})
        for param in params_str.split(";"):
            param = param.strip()
            if not param or "=" not in param:
                continue
            key, _, raw_val = param.partition("=")
            key = key.strip()
            values = [v.strip() for v in raw_val.split(",") if v.strip()]
            if key and values:
                existing = params.get(key, [])
                # Merge values, preserving order and avoiding duplicates.
                for v in values:
                    if v not in existing:
                        existing.append(v)
                params[key] = existing
    return result


@dataclass
class SessionConfig:
    """Holds cookies, proxy, and extractor-args settings used by yt-dlp.

    Args:
        cookies_file: Path to a Netscape-format cookies.txt file.
            Passed to yt-dlp as ``cookiefile``.  ``None`` means no cookies.
        proxy: Proxy URL string, e.g. ``"http://host:port"``,
            ``"socks5://host:port"``.  Passed to yt-dlp as ``proxy``.
            ``None`` means no proxy (direct connection).
        extractor_args: yt-dlp extractor-args string, e.g.
            ``"youtube:player_client=tv_embedded"``.  Parsed into the dict
            form that yt-dlp's Python API expects.  Particularly useful on
            headless / data-centre servers where YouTube requires a PO token:
            ``tv_embedded`` and ``mweb`` clients often bypass that check.
            ``None`` means no extra extractor args.
    """

    cookies_file: Optional[str] = field(default=None)
    proxy: Optional[str] = field(default=None)
    extractor_args: Optional[str] = field(default=None)

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
        """Return a yt-dlp options dict fragment for cookies, proxy, and
        extractor args.

        The returned dict is intended to be merged into a larger yt-dlp
        options dict::

            opts = {"quiet": True, ...}
            opts.update(session.as_ydl_opts())

        Returns:
            Dict with any combination of ``cookiefile``, ``proxy``, and
            ``extractor_args`` set, depending on which fields are configured.
        """
        opts: dict = {}
        if self.cookies_file:
            opts["cookiefile"] = self.cookies_file
        if self.proxy:
            opts["proxy"] = self.proxy
        if self.extractor_args:
            parsed = _parse_extractor_args(self.extractor_args)
            if parsed:
                opts["extractor_args"] = parsed
            else:
                logger.warning(
                    "Could not parse extractor_args %r – ignoring.",
                    self.extractor_args,
                )
        return opts

    # ── Human-readable description ────────────────────────────────────────────

    def describe(self) -> str:
        """Return a short human-readable summary of the active transport config.

        Used in log messages so operators can confirm which cookies/proxy are
        in effect at runtime.

        Returns:
            String such as
            ``"cookies=cookies.txt, proxy=socks5://..., extractor_args=youtube:..."``
            or ``"no cookies, no proxy, no extractor_args"``.
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
        if self.extractor_args:
            parts.append(f"extractor_args={self.extractor_args}")
        else:
            parts.append("no extractor_args")
        return ", ".join(parts)
