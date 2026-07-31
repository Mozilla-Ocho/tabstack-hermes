"""Fakes for the Tabstack SDK surface the plugin touches.

No network, and no dependency on the ``tabstack`` package being installed: the
handlers resolve their client through ``tools.get_async_client``, so a fake
client swapped in there covers every call path.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from tabstack_hermes import tools as tools_module


class FakeStream:
    """Async-iterable stand-in for the SDK's SSE streams."""

    def __init__(self, events: list[Any]) -> None:
        self._events = events

    def __aiter__(self):
        async def gen():
            for event in self._events:
                yield event

        return gen()


def event(name: str, data: Any) -> SimpleNamespace:
    return SimpleNamespace(event=name, data=data)


def research_complete(report: str, sources: list[tuple[str, str]]) -> SimpleNamespace:
    cited = [SimpleNamespace(title=title, url=url) for title, url in sources]
    return event(
        "complete",
        SimpleNamespace(report=report, metadata=SimpleNamespace(cited_pages=cited)),
    )


def automate_complete(answer: str, *, success: bool = True) -> SimpleNamespace:
    return event(
        "complete",
        SimpleNamespace(
            final_answer=answer,
            success=success,
            error=None,
            stats=SimpleNamespace(iterations=3, actions=7, duration_ms=1234),
        ),
    )


class FakeExtract:
    def __init__(self, owner: "FakeClient") -> None:
        self._owner = owner

    async def json(self, **kwargs: Any) -> Any:
        return await self._owner.resolve("extract.json", kwargs)

    async def markdown(self, **kwargs: Any) -> Any:
        return await self._owner.resolve("extract.markdown", kwargs)


class FakeGenerate:
    def __init__(self, owner: "FakeClient") -> None:
        self._owner = owner

    async def json(self, **kwargs: Any) -> Any:
        return await self._owner.resolve("generate.json", kwargs)


class FakeAgent:
    def __init__(self, owner: "FakeClient") -> None:
        self._owner = owner

    async def research(self, **kwargs: Any) -> Any:
        return await self._owner.resolve("agent.research", kwargs)

    async def automate(self, **kwargs: Any) -> Any:
        return await self._owner.resolve("agent.automate", kwargs)


class FakeClient:
    """Returns queued results (or raises queued exceptions) in order.

    A queued callable is called and its result awaited when awaitable, which is
    how the hung-fetch test queues a coroutine that never returns.
    """

    def __init__(self, results: list[Any]) -> None:
        self.extract = FakeExtract(self)
        self.generate = FakeGenerate(self)
        self.agent = FakeAgent(self)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._results = list(results)

    async def resolve(self, method: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((method, kwargs))
        result = self._results.pop(0) if self._results else None
        if isinstance(result, BaseException):
            raise result
        if callable(result):
            result = result()
        if inspect.isawaitable(result):
            result = await result
        return result


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch):
    """Install a FakeClient with a configured API key. Returns a factory."""

    def install(*results: Any) -> FakeClient:
        client = FakeClient(list(results))
        monkeypatch.setattr(tools_module, "get_async_client", lambda: client)
        monkeypatch.setattr(tools_module, "is_configured", lambda: True)
        return client

    return install


@pytest.fixture
def no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_module, "is_configured", lambda: False)


def markdown_result(content: str, *, url: str = "https://example.com", title: str = "") -> Any:
    metadata = SimpleNamespace(title=title) if title else None
    return SimpleNamespace(content=content, url=url, metadata=metadata)
