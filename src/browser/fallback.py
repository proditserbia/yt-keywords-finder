"""
Optional headless-browser fallback architecture.

This module defines the :class:`BrowserFallback` abstract base class and a
no-op :class:`NullFallback` implementation.  The intent is to provide a clean
extension point for future work (e.g., Playwright-based cookie refresh) without
making Playwright or Chromium a hard runtime dependency.

The main application uses :class:`NullFallback` by default.  To plug in a real
implementation:

1. Create a subclass of :class:`BrowserFallback` (e.g., in a separate optional
   package ``yt_browser_helper``).
2. Pass an instance to :func:`~src.core.processor.process_keywords` via the
   ``browser_fallback`` parameter.
3. The rest of the app is unchanged.

Nothing in this module imports Playwright, Chromium, or any other headless
browser library, so the app works even when those are not installed.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class BrowserFallback(ABC):
    """Abstract interface for headless-browser assisted operations.

    Concrete subclasses can implement cookie refreshing or browser-assisted
    metadata retrieval.  The app only calls :meth:`refresh_cookies`; adding
    further methods here is left for future iterations.
    """

    @abstractmethod
    def refresh_cookies(self, output_path: str) -> bool:
        """Attempt to refresh/export cookies to *output_path*.

        Args:
            output_path: Path where the refreshed ``cookies.txt`` should be
                written (Netscape format, compatible with yt-dlp's
                ``cookiefile`` option).

        Returns:
            ``True`` if cookies were successfully written, ``False`` otherwise.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` if this fallback backend is installed and usable."""


class NullFallback(BrowserFallback):
    """No-op fallback used when no headless browser backend is configured.

    All methods return safe do-nothing values so the rest of the application
    does not need to guard against ``None``.
    """

    def refresh_cookies(self, output_path: str) -> bool:
        logger.debug(
            "NullFallback.refresh_cookies called – no headless browser configured."
        )
        return False

    def is_available(self) -> bool:
        return False


def get_fallback(backend: Optional[str] = None) -> BrowserFallback:
    """Return a :class:`BrowserFallback` instance for the requested *backend*.

    Currently only ``None`` / ``"null"`` are recognised, returning a
    :class:`NullFallback`.  Future backends (e.g. ``"playwright"``) can be
    added here without changing call sites.

    Args:
        backend: Name of the desired backend, or ``None`` for the default
            no-op fallback.

    Returns:
        A :class:`BrowserFallback` instance (never ``None``).
    """
    if backend is None or backend.lower() in ("null", "none", ""):
        return NullFallback()
    logger.warning(
        "Unknown browser fallback backend %r – using NullFallback.", backend
    )
    return NullFallback()
