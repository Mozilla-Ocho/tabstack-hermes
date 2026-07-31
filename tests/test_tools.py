"""Handler contract tests.

Two invariants matter most and are asserted everywhere below:

1. A handler returns a JSON string, never a dict and never a raised exception.
2. A failure comes back as ``{"error": ...}`` so the model can react to it.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from conftest import FakeStream, automate_complete, event, markdown_result, research_complete

from tabstack_hermes import tools
from tabstack_hermes.errors import MISSING_KEY_ERROR
from tabstack_hermes.schemas import SCHEMAS, TOOL_DESCRIPTIONS, TOOL_NAMES

SCHEMA_JSON = json.dumps({"type": "object", "properties": {"title": {"type": "string"}}})


# --- extract_structured_data -------------------------------------------------


async def test_extract_structured_data_returns_json(fake_client) -> None:
    client = fake_client({"title": "Hello"})

    raw = await tools.extract_structured_data(
        {"url": "https://example.com", "json_schema_json": SCHEMA_JSON}
    )

    assert json.loads(raw) == {"title": "Hello"}
    name, kwargs = client.calls[0]
    assert name == "extract.json"
    assert kwargs == {
        "url": "https://example.com",
        "json_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
    }


async def test_fetch_options_are_forwarded_only_when_given(fake_client) -> None:
    client = fake_client({"ok": True})

    await tools.extract_structured_data(
        {
            "url": "https://example.com",
            "json_schema_json": SCHEMA_JSON,
            "effort": "max",
            "nocache": True,
            "country": "GB",
        }
    )

    _, kwargs = client.calls[0]
    assert kwargs["effort"] == "max"
    assert kwargs["nocache"] is True
    assert kwargs["geo_target"] == {"country": "GB"}


async def test_malformed_schema_json_is_an_error_payload(fake_client) -> None:
    fake_client({"unused": True})

    raw = await tools.extract_structured_data(
        {"url": "https://example.com", "json_schema_json": "{not json"}
    )

    assert "json_schema_json" in json.loads(raw)["error"]


async def test_schema_json_must_decode_to_an_object(fake_client) -> None:
    fake_client({"unused": True})

    raw = await tools.extract_structured_data(
        {"url": "https://example.com", "json_schema_json": "[1, 2, 3]"}
    )

    assert "must decode to a JSON object" in json.loads(raw)["error"]


async def test_missing_url_is_an_error_payload(fake_client) -> None:
    fake_client({"unused": True})

    raw = await tools.extract_structured_data({"json_schema_json": SCHEMA_JSON})

    assert "'url' is required" in json.loads(raw)["error"]


async def test_sdk_failure_becomes_an_error_payload(fake_client) -> None:
    fake_client(RuntimeError("upstream exploded"))

    raw = await tools.extract_structured_data(
        {"url": "https://example.com", "json_schema_json": SCHEMA_JSON}
    )

    assert json.loads(raw) == {"error": "upstream exploded"}


async def test_missing_api_key_explains_how_to_set_it(no_api_key) -> None:
    raw = await tools.extract_structured_data(
        {"url": "https://example.com", "json_schema_json": SCHEMA_JSON}
    )

    assert json.loads(raw)["error"] == MISSING_KEY_ERROR


# --- extract_page_content ----------------------------------------------------


async def test_extract_page_content_returns_raw_markdown(fake_client) -> None:
    fake_client(markdown_result("# Title\n\nBody"))

    raw = await tools.extract_page_content({"url": "https://example.com"})

    assert raw == "# Title\n\nBody"


# --- research_question -------------------------------------------------------


async def test_research_question_returns_answer_and_sources(fake_client) -> None:
    client = fake_client(
        FakeStream([research_complete("The answer", [("Source A", "https://a.example")])])
    )

    raw = await tools.research_question({"query": "why"})

    assert json.loads(raw) == {
        "answer": "The answer",
        "sources": [{"title": "Source A", "url": "https://a.example"}],
    }
    assert client.calls[0][1] == {"query": "why", "mode": "balanced"}


async def test_research_mode_and_nocache_forwarded(fake_client) -> None:
    client = fake_client(FakeStream([research_complete("x", [])]))

    await tools.research_question({"query": "why", "mode": "fast", "nocache": True})

    assert client.calls[0][1] == {"query": "why", "mode": "fast", "nocache": True}


async def test_research_error_event_becomes_an_error_payload(fake_client) -> None:
    fake_client(FakeStream([event("error", SimpleNamespace(message="rate limited"))]))

    raw = await tools.research_question({"query": "why"})

    assert json.loads(raw)["error"] == "Research failed: rate limited"


async def test_research_stream_without_complete_event(fake_client) -> None:
    fake_client(FakeStream([]))

    raw = await tools.research_question({"query": "why"})

    assert json.loads(raw) == {"answer": "Research did not complete", "sources": []}


# --- generate_structured_data ------------------------------------------------


async def test_generate_structured_data_forwards_instructions(fake_client) -> None:
    client = fake_client({"summaries": []})

    raw = await tools.generate_structured_data(
        {
            "url": "https://example.com",
            "instructions": "summarise each story",
            "json_schema_json": SCHEMA_JSON,
        }
    )

    assert json.loads(raw) == {"summaries": []}
    name, kwargs = client.calls[0]
    assert name == "generate.json"
    assert kwargs["instructions"] == "summarise each story"


async def test_generate_requires_instructions(fake_client) -> None:
    fake_client({"unused": True})

    raw = await tools.generate_structured_data(
        {"url": "https://example.com", "json_schema_json": SCHEMA_JSON}
    )

    assert "'instructions' is required" in json.loads(raw)["error"]


# --- automate_browser_task ---------------------------------------------------


async def test_automate_aggregates_stream_events(fake_client) -> None:
    stream = FakeStream(
        [
            event("browser:navigated", SimpleNamespace(url="https://a.example", title="A")),
            event("agent:extracted", SimpleNamespace(extracted_data="42 stars")),
            automate_complete("done"),
        ]
    )
    fake_client(stream)

    result = json.loads(await tools.automate_browser_task({"task": "count stars"}))

    assert result == {
        "answer": "done",
        "success": True,
        "iterations": 3,
        "actions": 7,
        "duration_ms": 1234,
        "extracted": ["42 stars"],
        "pages_visited": [{"url": "https://a.example", "title": "A"}],
    }


async def test_automate_optional_arguments_are_forwarded(fake_client) -> None:
    client = fake_client(FakeStream([automate_complete("done")]))

    await tools.automate_browser_task(
        {
            "task": "count stars",
            "url": "https://github.com/trending",
            "guardrails": "browse only",
            "data": {"name": "Ada"},
            "country": "US",
            "max_iterations": 5,
            "max_validation_attempts": 2,
        }
    )

    _, kwargs = client.calls[0]
    assert kwargs == {
        "task": "count stars",
        "url": "https://github.com/trending",
        "guardrails": "browse only",
        "data": {"name": "Ada"},
        "geo_target": {"country": "US"},
        "max_iterations": 5,
        "max_validation_attempts": 2,
    }


async def test_automate_error_event_becomes_an_error_payload(fake_client) -> None:
    fake_client(
        FakeStream(
            [event("error", SimpleNamespace(error=SimpleNamespace(message="blocked by site")))]
        )
    )

    raw = await tools.automate_browser_task({"task": "count stars"})

    assert json.loads(raw)["error"] == "Automation failed: blocked by site"


async def test_automate_stream_without_complete_event(fake_client) -> None:
    fake_client(FakeStream([]))

    result = json.loads(await tools.automate_browser_task({"task": "count stars"}))

    assert result["success"] is False
    assert result["answer"] is None


# --- registration surface ----------------------------------------------------


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_every_tool_has_a_schema_description_and_handler(name: str) -> None:
    assert SCHEMAS[name]["name"] == name
    assert SCHEMAS[name]["description"] == TOOL_DESCRIPTIONS[name]
    assert SCHEMAS[name]["parameters"]["type"] == "object"
    assert name in tools.HANDLERS


def test_required_fields_match_the_langchain_package() -> None:
    required = {name: set(SCHEMAS[name]["parameters"]["required"]) for name in TOOL_NAMES}

    assert required == {
        "extract_structured_data": {"url", "json_schema_json"},
        "extract_page_content": {"url"},
        "research_question": {"query"},
        "generate_structured_data": {"url", "instructions", "json_schema_json"},
        "automate_browser_task": {"task"},
    }


async def test_handlers_tolerate_extra_host_kwargs(fake_client) -> None:
    """Hermes passes task_id (and may add more) through **kwargs."""
    fake_client(markdown_result("body"))

    raw = await tools.extract_page_content({"url": "https://example.com"}, task_id="abc123")

    assert raw == "body"
