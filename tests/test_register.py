"""Registration tests against a recording stand-in for Hermes' PluginContext."""

from __future__ import annotations

from typing import Any

import tabstack_hermes
from tabstack_hermes.schemas import TOOL_NAMES


class RecordingContext:
    """Mirrors the PluginContext surface this plugin uses."""

    def __init__(self, *, provider_error: Exception | None = None) -> None:
        self.tools: list[dict[str, Any]] = []
        self.providers: list[Any] = []
        self._provider_error = provider_error

    def register_tool(self, **kwargs: Any) -> None:
        self.tools.append(kwargs)

    def register_web_search_provider(self, provider: Any) -> None:
        if self._provider_error is not None:
            raise self._provider_error
        self.providers.append(provider)


def test_register_registers_every_tool_in_the_tabstack_toolset() -> None:
    ctx = RecordingContext()

    tabstack_hermes.register(ctx)

    assert [tool["name"] for tool in ctx.tools] == list(TOOL_NAMES)
    for tool in ctx.tools:
        assert tool["toolset"] == "tabstack"
        assert tool["is_async"] is True
        assert tool["requires_env"] == ["TABSTACK_API_KEY"]
        assert tool["check_fn"] is tabstack_hermes.is_configured
        assert callable(tool["handler"])
        assert tool["schema"]["name"] == tool["name"]
        assert tool["description"]
        assert tool["emoji"]


def test_register_does_not_override_built_in_tools() -> None:
    """No `override=True` anywhere: shadowing a built-in needs operator opt-in."""
    ctx = RecordingContext()

    tabstack_hermes.register(ctx)

    assert all("override" not in tool for tool in ctx.tools)


def test_a_failed_provider_registration_still_leaves_the_tools_registered() -> None:
    ctx = RecordingContext(provider_error=RuntimeError("no web registry in this host"))

    tabstack_hermes.register(ctx)

    assert len(ctx.tools) == len(TOOL_NAMES)
    assert ctx.providers == []
