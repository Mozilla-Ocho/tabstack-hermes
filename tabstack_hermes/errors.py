"""Error normalisation for the Hermes tool contract.

Hermes handlers must **return** an error payload, never raise: an exception out
of a handler aborts the tool dispatch instead of giving the model something it
can react to. So every failure ends up here and comes back as
``{"error": ..., "status": ...}`` JSON, which is the same information the
LangChain package raises as ``TabstackToolError``.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["MISSING_KEY_ERROR", "error_payload", "error_json", "ok_json"]

MISSING_KEY_ERROR = (
    "TABSTACK_API_KEY is not set. Get a key at https://console.tabstack.ai, then "
    "set it with `hermes env set TABSTACK_API_KEY <key>` or export it in your shell."
)


def _status_of(err: BaseException) -> int | None:
    """Return the HTTP status of an SDK error, or None when it has none."""
    try:
        from tabstack import APIStatusError
    except Exception:  # noqa: BLE001 - SDK not importable, treat as statusless
        return None
    if isinstance(err, APIStatusError):
        return err.status_code
    return None


def error_payload(err: BaseException, *, prefix: str = "") -> dict[str, Any]:
    """Map any exception to the ``{"error": ...}`` payload shape."""
    message = str(err) or err.__class__.__name__
    if prefix:
        message = f"{prefix}: {message}"
    payload: dict[str, Any] = {"error": message}
    status = _status_of(err)
    if status is not None:
        payload["status"] = status
    return payload


def error_json(err: BaseException, *, prefix: str = "") -> str:
    """``error_payload`` serialised for return straight out of a handler."""
    return json.dumps(error_payload(err, prefix=prefix), ensure_ascii=False)


def ok_json(value: Any) -> str:
    """Serialise a successful result.

    Strings pass through untouched so ``extract_page_content`` hands the model raw
    markdown rather than a JSON-quoted blob.
    """
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)
