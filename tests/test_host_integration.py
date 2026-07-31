"""End-to-end load against the real Hermes plugin loader.

Everything else in the suite tests this plugin's own code. This module tests the
contract with the host: that Hermes discovers the entry point, calls
``register``, lands five tools in the ``tabstack`` toolset, accepts the web
provider, and selects it for ``web_extract`` when configured.

Skipped unless ``hermes-agent`` is importable **and** this package is installed
(the loader finds the plugin through its ``hermes_agent.plugins`` entry point, so
running from a source tree with no install has nothing to discover).
"""

from __future__ import annotations

import importlib.metadata as md
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("hermes_cli.plugins", reason="hermes-agent not installed")

ENTRY_POINT_GROUP = "hermes_agent.plugins"

if not any(ep.name == "tabstack" for ep in md.entry_points().select(group=ENTRY_POINT_GROUP)):
    pytest.skip(
        "tabstack-hermes is not installed, so Hermes has no entry point to discover "
        "(run `pip install -e .`)",
        allow_module_level=True,
    )

CONFIG = """\
plugins:
  enabled:
    - tabstack
web:
  extract_backend: "tabstack"
"""


@pytest.fixture(scope="module")
def loaded_plugin(tmp_path_factory: pytest.TempPathFactory):
    """Run Hermes' plugin discovery against a throwaway HERMES_HOME.

    Discovery is process-global and idempotent, so this happens once per module
    and the environment is patched before the first call. A module-scoped
    monkeypatch keeps it from leaking into the rest of the suite.
    """
    home: Path = tmp_path_factory.mktemp("hermes-home")
    (home / "config.yaml").write_text(CONFIG, encoding="utf-8")
    (home / ".env").write_text("TABSTACK_API_KEY=sk-test-not-real\n", encoding="utf-8")

    patch = pytest.MonkeyPatch()
    patch.setenv("HERMES_HOME", str(home))
    patch.setenv("TABSTACK_API_KEY", "sk-test-not-real")

    from hermes_cli.plugins import _ensure_plugins_discovered, get_plugin_manager

    _ensure_plugins_discovered()
    plugin = get_plugin_manager()._plugins.get("tabstack")

    yield plugin

    patch.undo()


def test_hermes_loads_the_plugin_without_error(loaded_plugin) -> None:
    assert loaded_plugin is not None, "Hermes did not discover the tabstack plugin"
    assert loaded_plugin.error is None
    assert loaded_plugin.enabled is True
    assert loaded_plugin.manifest.source == "entrypoint"


def test_the_five_tools_land_in_the_tabstack_toolset(loaded_plugin) -> None:
    from tools.registry import registry

    assert sorted(registry.get_tool_names_for_toolset("tabstack")) == [
        "automate_browser_task",
        "extract_page_content",
        "extract_structured_data",
        "generate_structured_data",
        "research_question",
    ]
    for name in loaded_plugin.tools_registered:
        entry = registry.get_entry(name)
        assert entry.toolset == "tabstack"
        assert entry.is_async is True


def test_the_web_provider_is_accepted_and_selected(loaded_plugin) -> None:
    """`web.extract_backend: tabstack` must resolve to this provider, and only for extract."""
    from agent.web_search_registry import get_active_extract_provider, get_provider

    provider = get_provider("tabstack")
    assert provider is not None
    assert provider.supports_extract() is True
    assert provider.supports_search() is False
    assert get_active_extract_provider() is provider


async def test_a_tool_dispatches_through_the_registry(loaded_plugin, monkeypatch) -> None:
    """Full round trip: Hermes dispatch -> handler -> (stubbed) SDK -> markdown back."""
    from tools.registry import registry

    import tabstack_hermes.tools as plugin_tools

    class Extract:
        async def markdown(self, **kwargs):
            assert kwargs == {"url": "https://example.com", "effort": "max"}
            return SimpleNamespace(content="# hello", url=kwargs["url"], metadata=None)

    monkeypatch.setattr(
        plugin_tools, "get_async_client", lambda: SimpleNamespace(extract=Extract())
    )

    result = registry.dispatch(
        "extract_page_content", {"url": "https://example.com", "effort": "max"}
    )
    if hasattr(result, "__await__"):
        result = await result

    assert result == "# hello"
