"""Web extract backend tests.

``extract_urls`` carries all the logic and needs no host, so it is tested
directly. The provider class subclasses the host ABC, so those tests skip when
hermes-agent is not importable in this environment.
"""

from __future__ import annotations

import asyncio

import pytest
from conftest import markdown_result

from tabstack_hermes import tools


async def test_extract_urls_shapes_results_for_web_extract(fake_client) -> None:
    fake_client(markdown_result("# A", url="https://a.example", title="Page A"))

    results = await tools.extract_urls(["https://a.example"])

    assert results == [
        {
            "url": "https://a.example",
            "title": "Page A",
            "content": "# A",
            "raw_content": "# A",
            "metadata": {"sourceURL": "https://a.example", "title": "Page A"},
        }
    ]


async def test_extract_urls_requests_metadata(fake_client) -> None:
    client = fake_client(markdown_result("body"))

    await tools.extract_urls(["https://a.example"])

    _, kwargs = client.calls[0]
    assert kwargs == {"url": "https://a.example", "metadata": True}


async def test_extract_urls_falls_back_to_the_url_as_title(fake_client) -> None:
    fake_client(markdown_result("body", url="https://a.example"))

    results = await tools.extract_urls(["https://a.example"])

    assert results[0]["title"] == "https://a.example"


async def test_extract_urls_preserves_input_order(fake_client) -> None:
    """web_extract re-interleaves these with URLs it rejected, so order is load-bearing."""
    fake_client(
        markdown_result("A", url="https://a.example"),
        markdown_result("B", url="https://b.example"),
        markdown_result("C", url="https://c.example"),
    )

    results = await tools.extract_urls(
        ["https://a.example", "https://b.example", "https://c.example"]
    )

    assert [r["content"] for r in results] == ["A", "B", "C"]


async def test_one_bad_url_does_not_fail_the_batch(fake_client) -> None:
    fake_client(
        markdown_result("A", url="https://a.example"),
        RuntimeError("404 Not Found"),
    )

    results = await tools.extract_urls(["https://a.example", "https://b.example"])

    assert results[0]["content"] == "A"
    assert results[1] == {
        "url": "https://b.example",
        "title": "",
        "content": "",
        "error": "404 Not Found",
    }


async def test_missing_api_key_reports_per_url(no_api_key) -> None:
    results = await tools.extract_urls(["https://a.example"])

    assert "TABSTACK_API_KEY is not set" in results[0]["error"]


async def test_a_hung_fetch_times_out(fake_client, monkeypatch: pytest.MonkeyPatch) -> None:
    async def never() -> None:
        await asyncio.sleep(10)

    monkeypatch.setattr(tools, "EXTRACT_TIMEOUT_SECONDS", 0.01)
    fake_client(never)

    results = await tools.extract_urls(["https://slow.example"])

    assert "timed out" in results[0]["error"]


async def test_effort_is_forwarded_and_unknown_kwargs_ignored(fake_client) -> None:
    client = fake_client(markdown_result("body"))

    await tools.extract_urls(["https://a.example"], effort="max", format="html", max_chars=10)

    _, kwargs = client.calls[0]
    assert kwargs["effort"] == "max"
    assert "format" not in kwargs
    assert "max_chars" not in kwargs


# --- host-coupled surface ----------------------------------------------------


def _provider_class():
    pytest.importorskip(
        "agent.web_search_provider",
        reason="hermes-agent not installed in this environment",
    )
    from tabstack_hermes.provider import TabstackWebSearchProvider

    return TabstackWebSearchProvider


def test_provider_advertises_extract_only() -> None:
    provider = _provider_class()()

    assert provider.name == "tabstack"
    assert provider.display_name == "Tabstack"
    assert provider.supports_extract() is True
    assert provider.supports_search() is False


def test_provider_setup_schema_prompts_for_the_api_key() -> None:
    schema = _provider_class()().get_setup_schema()

    assert schema["env_vars"][0]["key"] == "TABSTACK_API_KEY"
    assert schema["badge"] == "paid"


def test_provider_availability_follows_the_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    cls = _provider_class()
    monkeypatch.delenv("TABSTACK_API_KEY", raising=False)
    assert cls().is_available() is False

    monkeypatch.setenv("TABSTACK_API_KEY", "sk-test")
    assert cls().is_available() is True


async def test_provider_delegates_to_extract_urls(fake_client) -> None:
    fake_client(markdown_result("A", url="https://a.example", title="A"))

    results = await _provider_class()().extract(["https://a.example"])

    assert results[0]["content"] == "A"
