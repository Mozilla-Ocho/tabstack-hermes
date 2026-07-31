"""Tabstack client construction for the Hermes plugin.

Every network call in this plugin goes through the async SDK client built here.
The handlers are registered with ``is_async=True``, so the async client is the
only one needed: Hermes' tool registry awaits the coroutine on its own loop and
never bounces through a thread pool.

Two Hermes-specific concerns shape this module:

- **Cold start.** The SDK import is deferred to first use, so a session that
  never calls a Tabstack tool does not pay for it (the bundled web providers do
  the same for their vendor SDKs).
- **Credential visibility.** Keys set through Hermes' config layer live in
  ``~/.hermes/.env`` and are not always exported into the process environment
  (gateway sessions, delegate children, subprocess agent runs). ``get_env`` asks
  ``hermes_cli.config`` first and falls back to ``os.environ`` when the host is
  not importable, which keeps this module usable in plain unit tests.
"""

from __future__ import annotations

import os
import threading
from typing import Any

API_KEY_ENV = "TABSTACK_API_KEY"
BASE_URL_ENV = "TABSTACK_BASE_URL"

__all__ = [
    "API_KEY_ENV",
    "BASE_URL_ENV",
    "get_env",
    "get_api_key",
    "is_configured",
    "get_async_client",
    "reset_async_client",
]

_client: Any = None
_client_lock = threading.Lock()


def get_env(name: str) -> str:
    """Read *name* through Hermes' config layer, falling back to the environment.

    Mirrors ``agent.web_search_provider.get_provider_env`` but tolerates the host
    being absent so the plugin can be imported and tested standalone. Returns the
    stripped value, or ``""`` when unset.
    """
    value: str | None = None
    try:
        from hermes_cli.config import get_env_value

        value = get_env_value(name)
    except Exception:  # noqa: BLE001 - host config layer is optional here
        value = None
    if value is None:
        value = os.getenv(name, "")
    return (value or "").strip()


def get_api_key() -> str:
    """Return the configured Tabstack API key, or ``""`` when unset."""
    return get_env(API_KEY_ENV)


def is_configured() -> bool:
    """Cheap availability check: is an API key present?

    Used as the ``check_fn`` for every registered tool and as the web provider's
    ``is_available``. Never makes a network call: Hermes calls this at tool
    registration time and on every ``hermes tools`` repaint.
    """
    return bool(get_api_key())


def get_async_client() -> Any:
    """Return the process-wide ``AsyncTabstack`` client, building it on first use.

    Double-checked locking: Hermes runs multi-threaded sessions (delegated tool
    calls, background workers, the self-improvement fork), so an unguarded lazy
    singleton would let two threads both construct a client and leak the loser's
    connection pool.
    """
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            from tabstack import AsyncTabstack  # deliberately lazy

            kwargs: dict[str, Any] = {"api_key": get_api_key() or None}
            base_url = get_env(BASE_URL_ENV)
            if base_url:
                kwargs["base_url"] = base_url
            _client = AsyncTabstack(**kwargs)
    return _client


def reset_async_client() -> None:
    """Drop the cached client so tests (and key changes) can rebuild it."""
    global _client
    with _client_lock:
        _client = None
