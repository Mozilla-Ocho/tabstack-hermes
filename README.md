# tabstack-hermes

[![PyPI](https://img.shields.io/pypi/v/tabstack-hermes.svg)](https://pypi.org/project/tabstack-hermes/)
[![Python versions](https://img.shields.io/pypi/pyversions/tabstack-hermes.svg)](https://pypi.org/project/tabstack-hermes/)
[![Tests](https://github.com/Mozilla-Ocho/tabstack-hermes/actions/workflows/test.yml/badge.svg)](https://github.com/Mozilla-Ocho/tabstack-hermes/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

Tabstack web intelligence for [Hermes Agent](https://hermes-agent.nousresearch.com). Five native
tools in a `tabstack` toolset, plus a `tabstack` backend for Hermes' own `web_extract` tool, all
backed by the official [Tabstack SDK](https://pypi.org/project/tabstack/).

## Why Tabstack

Hermes ships with web search and extraction backends already. Tabstack adds the parts they do not
cover:

- **Schema-enforced extraction.** You define the JSON shape, you get that shape back. No
  prompt-engineering the JSON out of page text.
- **No browser to run.** JS-heavy pages render server side. Nothing to install, nothing to keep
  patched on the box Hermes lives on.
- **Research with citations.** One call returns a synthesised answer plus the sources it used.
- **Browser automation.** Multi-step, natural-language web tasks that navigate, fill, and extract
  across pages.

## Install

Requires Python 3.11 or newer (same floor as `hermes-agent`) and a Tabstack API key from
[console.tabstack.ai](https://console.tabstack.ai).

```bash
pip install tabstack-hermes
hermes plugins enable tabstack
hermes env set TABSTACK_API_KEY <your-key>
```

Plugins are opt-in, so `hermes plugins enable tabstack` is required: the pip package puts the plugin
on Hermes' discovery path, the enable step lets it load.

Prefer to install from git instead of PyPI:

```bash
hermes plugins install Mozilla-Ocho/tabstack-hermes/tabstack_hermes --enable
```

The `/tabstack_hermes` suffix is the subdirectory holding the plugin: `plugin.yaml` sits next to the
code so one directory serves both install paths. Hermes renames the installed directory to the
manifest name, so it lands at `~/.hermes/plugins/tabstack/` either way.

Confirm it loaded:

```bash
hermes plugins list      # tabstack, enabled, 5 tools
hermes tools             # the tabstack toolset
```

## The tools

| Tool | What it does |
| --- | --- |
| `extract_structured_data` | Pull specific fields from a URL into a JSON shape you define. |
| `extract_page_content` | Fetch a page as clean markdown. |
| `research_question` | Synthesised answer with cited sources across multiple pages. |
| `generate_structured_data` | Fetch a page, then AI-transform it into derived or reshaped JSON. |
| `automate_browser_task` | Run a multi-step, natural-language browser task. |

All five land in the `tabstack` toolset, so they enable and disable as a unit in `hermes tools`.

Names, descriptions, and inputs match the [`langchain-tabstack`](https://pypi.org/project/langchain-tabstack/)
package and the TypeScript adapters, so a Tabstack tool behaves the same whichever framework calls
it. Tools return a JSON string; `extract_page_content` returns markdown directly.

### Optional inputs

Passed only when the model provides them, so omitting them keeps Tabstack's defaults.

- `extract_structured_data`, `extract_page_content`, `generate_structured_data`:
  - `effort`: `"min"` | `"standard"` | `"max"`. Use `"max"` for JS-heavy pages (full server-side
    browser rendering).
  - `nocache`: `true` to bypass the cache.
  - `country`: ISO 3166-1 alpha-2 code (for example `"US"`) for geotargeted fetches.
- `research_question`: `mode` (`"fast"` | `"balanced"`), `nocache`.
- `automate_browser_task`: `data` (context for form filling), `country`, `max_iterations`,
  `max_validation_attempts`.

## Tabstack as the web extract backend

The plugin also registers a `tabstack` web provider, so Hermes' built-in `web_extract` tool can fetch
through Tabstack without the model learning a new tool:

```yaml
# ~/.hermes/config.yaml
web:
  extract_backend: "tabstack"
```

Extract only. Tabstack has no ranked search endpoint, so `supports_search` is False and `web_search`
keeps using whichever backend you already have (brave-free, ddgs, exa, tavily, firecrawl, and so on).
For synthesis across sources, use the `research_question` tool rather than a search backend.

Behaviour worth knowing:

- URLs come back in the order they went in, because `web_extract` re-interleaves them with the ones
  it rejected as unsafe.
- A batch fans out 5 URLs at a time, 60s ceiling per URL. One failing URL returns an `error` entry
  for that URL and does not fail the batch.
- `format="html"` is ignored: Tabstack returns markdown.

## Configuration

| Variable | Purpose |
| --- | --- |
| `TABSTACK_API_KEY` | Required. Get one at [console.tabstack.ai](https://console.tabstack.ai). |
| `TABSTACK_BASE_URL` | Optional. Point the SDK at a different API base URL. |

Keys are read through Hermes' config layer first (`~/.hermes/.env` via `hermes env set`), then the
process environment, so credentials work in gateway sessions, delegated children, and subprocess
agent runs where the variable was never exported.

Without a key the plugin still loads and the tools still appear in `hermes tools`, but their
`check_fn` keeps them out of dispatch until a key is set. The SDK is imported and the client built on
the first tool call, so a session that never calls Tabstack pays no cold-start cost.

## Error handling

Handlers never raise. A failure returns JSON the model can act on, with the HTTP status when the API
supplied one:

```json
{"error": "Extract failed for https://example.com", "status": 429}
```

## Alternative: MCP

Tabstack's CLI ships a stdio MCP server, which is a config-only path with no plugin install:

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  tabstack:
    command: "tabstack"
    args: ["mcp"]
```

That exposes the raw API surface as `mcp_tabstack_*` tools. This plugin is the better default: the
tool names match Tabstack's other framework integrations, the tools are one toolset the user can
toggle, there is no subprocess per session, and `web_extract` can route through Tabstack.

## Development

```bash
uv venv --python 3.11 && uv pip install -e ".[test,dev]"
pytest                    # 44 tests, no network
ruff check . && ruff format --check .
```

`hermes-agent` is not a dependency of this package: it is the host process. Install it in the dev
environment (`uv pip install hermes-agent`) to exercise the tests that need it, which is the web
provider glue plus an end-to-end load through Hermes' own plugin loader, tool registry, and web
provider registry. They skip without it.

Releases are cut from a GitHub Release tagged `vX.Y.Z`: the tag's version is written into
`pyproject.toml`, `plugin.yaml`, and `__version__` at build time, and the package is published to
PyPI through trusted publishing after lint and tests pass.

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the contributor guide and [AGENTS.md](./AGENTS.md) for the
architecture, conventions, and the host API surface this plugin depends on.

## Feedback

Report a problem or request a feature in
[tabstack-feedback](https://github.com/Mozilla-Ocho/tabstack-feedback/issues/new/choose). Include
the plugin version, the tool name, and the `error` (and `status`, if present) the tool returned. Never paste API
keys or personal data into an issue.

## Links

- [Tabstack docs](https://docs.tabstack.ai)
- [Tabstack SDK (`tabstack`)](https://pypi.org/project/tabstack/)
- [Hermes plugin docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins)
- [Get an API key](https://console.tabstack.ai)
