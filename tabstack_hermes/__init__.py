"""Tabstack plugin for Hermes Agent.

Registers five Tabstack tools in the ``tabstack`` toolset, plus a ``tabstack`` web
extract backend for Hermes' built-in ``web_extract`` tool.

The plugin loader calls :func:`register` once, with a ``PluginContext``. Nothing
here touches the network or imports the Tabstack SDK: the client is built on the
first tool call, so a session that never uses Tabstack pays nothing and an
install with no API key still loads (the tools appear in ``hermes tools``, and
``check_fn`` keeps them out of dispatch until a key is set).
"""

from __future__ import annotations

import logging
from typing import Any

from .client import (
    API_KEY_ENV,
    get_api_key,
    get_async_client,
    is_configured,
    reset_async_client,
)
from .errors import error_payload
from .schemas import SCHEMAS, TOOL_DESCRIPTIONS, TOOL_EMOJI, TOOL_NAMES, TOOLSET
from .tools import HANDLERS, extract_urls

__version__ = "0.1.0"

logger = logging.getLogger(__name__)

__all__ = [
    "__version__",
    "API_KEY_ENV",
    "HANDLERS",
    "SCHEMAS",
    "TOOLSET",
    "TOOL_DESCRIPTIONS",
    "TOOL_NAMES",
    "error_payload",
    "extract_urls",
    "get_api_key",
    "get_async_client",
    "is_configured",
    "register",
    "reset_async_client",
]


def _register_web_provider(ctx: Any) -> None:
    """Register the extract backend, tolerating a host that cannot provide one.

    Importing ``provider`` pulls in ``agent.web_search_provider`` from the host. If
    that import fails (older Hermes, stripped install, upstream refactor) the five
    tools must still register, so the failure is logged and swallowed rather than
    taking the whole plugin down.
    """
    try:
        from .provider import TabstackWebSearchProvider

        ctx.register_web_search_provider(TabstackWebSearchProvider())
    except Exception as exc:  # noqa: BLE001 - tools matter more than the backend
        logger.warning(
            "Tabstack web extract backend not registered (%s). The tabstack tools are unaffected.",
            exc,
        )


def register(ctx: Any) -> None:
    """Register every Tabstack tool and the web extract backend."""
    for name in TOOL_NAMES:
        ctx.register_tool(
            name=name,
            toolset=TOOLSET,
            schema=SCHEMAS[name],
            description=TOOL_DESCRIPTIONS[name],
            handler=HANDLERS[name],
            check_fn=is_configured,
            requires_env=[API_KEY_ENV],
            is_async=True,
            emoji=TOOL_EMOJI[name],
        )
    _register_web_provider(ctx)
