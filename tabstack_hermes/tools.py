"""Tabstack tool handlers for Hermes.

Every handler is a coroutine registered with ``is_async=True``, takes the model's
validated arguments as a dict, and returns a JSON string. Nothing raises: the
Hermes contract is that a failing tool returns ``{"error": ...}`` so the model can
see what went wrong and adapt, and an escaping exception would abort the dispatch
instead.

This module imports nothing from Hermes, so it is exercisable (and testable) on
its own. The host-facing glue lives in ``__init__.py`` (tool registration) and
``provider.py`` (the web extract backend).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Coroutine

from .client import get_async_client, is_configured
from .errors import MISSING_KEY_ERROR, error_json, ok_json

__all__ = [
    "HANDLERS",
    "extract_structured_data",
    "extract_page_content",
    "research_question",
    "generate_structured_data",
    "automate_browser_task",
    "extract_urls",
]

# Per-URL ceiling for the web extract backend. Matches the bundled firecrawl
# provider so a hung fetch cannot stall a turn.
EXTRACT_TIMEOUT_SECONDS = 60.0
# How many URLs the extract backend fetches at once. web_extract hands over a
# whole batch, and Tabstack's extract endpoint is one URL per call.
EXTRACT_CONCURRENCY = 5


class _InputError(ValueError):
    """A tool argument was missing or malformed."""


def _client() -> Any:
    if not is_configured():
        raise _InputError(MISSING_KEY_ERROR)
    return get_async_client()


def _require_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _InputError(f"'{key}' is required and must be a non-empty string")
    return value.strip()


def _optional_str(args: dict[str, Any], key: str) -> str | None:
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _require_json_schema(args: dict[str, Any], key: str) -> dict[str, Any]:
    """Parse a JSON-encoded JSON Schema argument.

    The input is a *string* rather than a nested object on purpose: it matches the
    LangChain and TypeScript packages, and models reliably produce a JSON blob in
    a string field where a free-form nested object often comes back half-formed.
    """
    raw = _require_str(args, key)
    try:
        schema = json.loads(raw)
    except json.JSONDecodeError as err:
        raise _InputError(f"'{key}' must be a JSON-encoded JSON Schema object: {err}") from err
    if not isinstance(schema, dict):
        raise _InputError(f"'{key}' must decode to a JSON object, got {type(schema).__name__}")
    return schema


def _fetch_options(args: dict[str, Any]) -> dict[str, Any]:
    """Shared fetch options (effort, cache bypass, geotargeting).

    Omitted values are left out entirely so Tabstack's own defaults apply.
    """
    options: dict[str, Any] = {}
    effort = _optional_str(args, "effort")
    if effort is not None:
        options["effort"] = effort
    nocache = args.get("nocache")
    if isinstance(nocache, bool):
        options["nocache"] = nocache
    country = _optional_str(args, "country")
    if country is not None:
        options["geo_target"] = {"country": country}
    return options


def _research_kwargs(args: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "query": _require_str(args, "query"),
        "mode": _optional_str(args, "mode") or "balanced",
    }
    nocache = args.get("nocache")
    if isinstance(nocache, bool):
        kwargs["nocache"] = nocache
    return kwargs


def _automate_kwargs(args: dict[str, Any]) -> dict[str, Any]:
    # Interactive mode is intentionally left off: a one-shot tool cannot service
    # the human-in-the-loop form-data callback, and Hermes dispatches tools
    # without a way to pause for one.
    kwargs: dict[str, Any] = {"task": _require_str(args, "task")}
    url = _optional_str(args, "url")
    if url is not None:
        kwargs["url"] = url
    guardrails = _optional_str(args, "guardrails")
    if guardrails is not None:
        kwargs["guardrails"] = guardrails
    data = args.get("data")
    if isinstance(data, dict):
        kwargs["data"] = data
    country = _optional_str(args, "country")
    if country is not None:
        kwargs["geo_target"] = {"country": country}
    for key in ("max_iterations", "max_validation_attempts"):
        value = args.get(key)
        if isinstance(value, bool) or value is None:
            continue
        try:
            kwargs[key] = int(value)
        except (TypeError, ValueError) as err:
            raise _InputError(f"'{key}' must be an integer") from err
    return kwargs


def _research_complete(event: Any) -> dict[str, Any]:
    cited = event.data.metadata.cited_pages or []
    return {
        "answer": event.data.report,
        "sources": [{"title": page.title or "", "url": page.url} for page in cited],
    }


def _automate_complete(
    event: Any, extracted: list[str], pages_visited: list[dict[str, str]]
) -> dict[str, Any]:
    data = event.data
    if not data.success and data.error:
        raise RuntimeError(f"Automation failed: {data.error.message}")
    return {
        "answer": data.final_answer,
        "success": data.success,
        "iterations": data.stats.iterations,
        "actions": data.stats.actions,
        "duration_ms": data.stats.duration_ms,
        "extracted": extracted,
        "pages_visited": pages_visited,
    }


def _automate_incomplete(
    extracted: list[str], pages_visited: list[dict[str, str]]
) -> dict[str, Any]:
    return {
        "answer": None,
        "success": False,
        "iterations": 0,
        "actions": 0,
        "duration_ms": 0,
        "extracted": extracted,
        "pages_visited": pages_visited,
    }


# --- Handlers ----------------------------------------------------------------


async def extract_structured_data(args: dict[str, Any], **_kwargs: Any) -> str:
    """Extract structured data from a URL via ``extract.json``."""
    try:
        url = _require_str(args, "url")
        schema = _require_json_schema(args, "json_schema_json")
        data = await _client().extract.json(url=url, json_schema=schema, **_fetch_options(args))
        return ok_json(data)
    except Exception as err:  # noqa: BLE001 - handlers return, never raise
        return error_json(err)


async def extract_page_content(args: dict[str, Any], **_kwargs: Any) -> str:
    """Fetch a URL and return clean markdown via ``extract.markdown``."""
    try:
        url = _require_str(args, "url")
        result = await _client().extract.markdown(url=url, **_fetch_options(args))
        return ok_json(result.content)
    except Exception as err:  # noqa: BLE001
        return error_json(err)


async def research_question(args: dict[str, Any], **_kwargs: Any) -> str:
    """Research a question across multiple web sources via ``agent.research``."""
    try:
        stream = await _client().agent.research(**_research_kwargs(args))
        async for event in stream:
            if event.event == "error":
                message = getattr(event.data, "message", None) or "unknown error"
                raise RuntimeError(f"Research failed: {message}")
            if event.event == "complete":
                return ok_json(_research_complete(event))
        return ok_json({"answer": "Research did not complete", "sources": []})
    except Exception as err:  # noqa: BLE001
        return error_json(err)


async def generate_structured_data(args: dict[str, Any], **_kwargs: Any) -> str:
    """Fetch a URL and AI-transform its content via ``generate.json``."""
    try:
        url = _require_str(args, "url")
        instructions = _require_str(args, "instructions")
        schema = _require_json_schema(args, "json_schema_json")
        data = await _client().generate.json(
            url=url,
            json_schema=schema,
            instructions=instructions,
            **_fetch_options(args),
        )
        return ok_json(data)
    except Exception as err:  # noqa: BLE001
        return error_json(err)


async def automate_browser_task(args: dict[str, Any], **_kwargs: Any) -> str:
    """Run a browser automation task via ``agent.automate``.

    Consumes the event stream non-interactively and returns the final answer plus
    anything extracted and the pages visited along the way.
    """
    try:
        stream = await _client().agent.automate(**_automate_kwargs(args))
        extracted: list[str] = []
        pages_visited: list[dict[str, str]] = []
        async for event in stream:
            if event.event == "agent:extracted":
                extracted.append(event.data.extracted_data)
            elif event.event == "browser:navigated":
                pages_visited.append({"url": event.data.url, "title": event.data.title})
            elif event.event == "error":
                raise RuntimeError(f"Automation failed: {event.data.error.message}")
            elif event.event == "complete":
                return ok_json(_automate_complete(event, extracted, pages_visited))
        return ok_json(_automate_incomplete(extracted, pages_visited))
    except Exception as err:  # noqa: BLE001
        return error_json(err)


HANDLERS: dict[str, Callable[..., Coroutine[Any, Any, str]]] = {
    "extract_structured_data": extract_structured_data,
    "extract_page_content": extract_page_content,
    "research_question": research_question,
    "generate_structured_data": generate_structured_data,
    "automate_browser_task": automate_browser_task,
}


# --- Web extract backend body ------------------------------------------------


def _title_of(result: Any, url: str) -> str:
    """Best-effort page title from the markdown response metadata."""
    metadata = getattr(result, "metadata", None)
    title = getattr(metadata, "title", None) if metadata is not None else None
    if isinstance(title, str) and title.strip():
        return title.strip()
    return url


async def _extract_one(url: str, options: dict[str, Any]) -> dict[str, Any]:
    """Fetch one URL as markdown, shaped for Hermes' ``web_extract`` pipeline."""
    try:
        result = await asyncio.wait_for(
            _client().extract.markdown(url=url, metadata=True, **options),
            timeout=EXTRACT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return {
            "url": url,
            "title": "",
            "content": "",
            "error": f"Tabstack extract timed out after {int(EXTRACT_TIMEOUT_SECONDS)}s",
        }
    except Exception as err:  # noqa: BLE001 - per-URL failure, not batch failure
        return {"url": url, "title": "", "content": "", "error": str(err)}

    content = result.content or ""
    title = _title_of(result, url)
    return {
        "url": getattr(result, "url", url) or url,
        "title": title,
        "content": content,
        "raw_content": content,
        "metadata": {"sourceURL": url, "title": title},
    }


async def extract_urls(urls: list[str], **kwargs: Any) -> list[dict[str, Any]]:
    """Extract clean markdown for each URL, in the order given.

    This is the body behind ``TabstackWebSearchProvider.extract``. Result order
    matches the input list because ``web_extract`` re-interleaves these entries
    with the ones it rejected as unsafe before returning to the model. Failures
    are per-URL ``error`` entries, never exceptions, for the same reason.

    ``kwargs`` may carry forward-compat fields from the host (``format``,
    ``include_raw``, ``max_chars``); unknown keys are ignored. ``format="html"``
    is not supported (Tabstack returns markdown), so it is ignored rather than
    failing the batch.
    """
    options: dict[str, Any] = {}
    effort = kwargs.get("effort")
    if isinstance(effort, str) and effort.strip():
        options["effort"] = effort.strip()

    semaphore = asyncio.Semaphore(EXTRACT_CONCURRENCY)

    async def run(url: str) -> dict[str, Any]:
        async with semaphore:
            return await _extract_one(url, options)

    return list(await asyncio.gather(*(run(url) for url in urls)))
