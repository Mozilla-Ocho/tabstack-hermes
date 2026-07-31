"""Tabstack as a Hermes web extract backend.

Registering a ``WebSearchProvider`` puts Tabstack behind Hermes' own
``web_extract`` tool, so existing prompts, skills, and tool budgets keep working
and only the fetch layer changes:

    web:
      extract_backend: "tabstack"

Extract only. ``supports_search`` stays False because Tabstack has no ranked
search endpoint, and mapping ``web_search`` onto ``agent.research`` would return a
synthesised report where the host contract wants a list of
``{title, url, description, position}`` results. Hermes handles that honestly: a
search call falls through to whichever backend does support search. Use the
``research_question`` tool for synthesis.

This module imports the host ABC at import time, which is what the plugin loader
requires (``register_web_search_provider`` rejects anything that is not a real
``WebSearchProvider`` subclass). The extraction logic itself lives in
``tools.extract_urls`` so it stays testable without Hermes installed.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.web_search_provider import WebSearchProvider

from .client import API_KEY_ENV, is_configured
from .tools import extract_urls

logger = logging.getLogger(__name__)

__all__ = ["TabstackWebSearchProvider"]


def _interrupted() -> bool:
    """True when the user has interrupted the turn. False when unknowable."""
    try:
        from tools.interrupt import is_interrupted

        return bool(is_interrupted())
    except Exception:  # noqa: BLE001 - host helper is optional
        return False


class TabstackWebSearchProvider(WebSearchProvider):
    """Extract-only backend: clean markdown per URL, no browser to run locally.

    ``extract`` is async because it performs network I/O per URL and Tabstack's
    endpoint is one URL per call, so a batch fans out concurrently. The host
    dispatcher detects the coroutine and awaits it.
    """

    @property
    def name(self) -> str:
        return "tabstack"

    @property
    def display_name(self) -> str:
        return "Tabstack"

    def is_available(self) -> bool:
        """True when ``TABSTACK_API_KEY`` is set. No network call: this runs at
        registration time and on every ``hermes tools`` repaint."""
        return is_configured()

    def supports_search(self) -> bool:
        return False

    def supports_extract(self) -> bool:
        return True

    async def extract(self, urls: list[str], **kwargs: Any) -> list[dict[str, Any]]:
        """Extract content for each URL, preserving input order."""
        if _interrupted():
            return [
                {"url": url, "title": "", "content": "", "error": "Interrupted"} for url in urls
            ]
        logger.info("Tabstack extract: %d URL(s)", len(urls))
        return await extract_urls(urls, **kwargs)

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": "Tabstack",
            "badge": "paid",
            "tag": "Hosted extraction with server-side rendering for JS-heavy pages.",
            "env_vars": [
                {
                    "key": API_KEY_ENV,
                    "prompt": "Tabstack API key",
                    "url": "https://console.tabstack.ai",
                },
            ],
        }
