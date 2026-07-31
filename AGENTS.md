# AGENTS.md

Operational guide for AI agents working in this repository. Humans: see `README.md`.

## What this repo is

The Tabstack plugin for [Hermes Agent](https://github.com/nousresearch/hermes-agent) (Nous Research).
It registers five Tabstack tools in a `tabstack` toolset and a `tabstack` web extract backend, both
through Hermes' plugin API. Hermes is Python, so this is a Python package, separate from the
TypeScript integrations monorepo.

```
plugin.yaml            manifest, read by Hermes when the repo is cloned into ~/.hermes/plugins/
__init__.py            shim for that same clone path: re-exports register from tabstack_hermes
tabstack_hermes/
  __init__.py          register(ctx): the only host entry point
  client.py            lazy, thread-safe AsyncTabstack singleton + key resolution
  errors.py            exception -> {"error": ..., "status": ...} payloads
  schemas.py           OpenAI function schemas, names, descriptions, emoji
  tools.py             the five handlers + extract_urls (no Hermes imports)
  provider.py          TabstackWebSearchProvider (extract only)
tests/                 pytest, no network
```

## Why it is structured this way

- **`tools.py` imports nothing from Hermes.** All tool logic is exercisable without the host
  installed, which is what keeps the test suite fast and hermetic. Host coupling is confined to
  `__init__.py` (registration) and `provider.py` (which must subclass the host ABC).
- **`provider.py` is a thin shell.** The extraction body lives in `tools.extract_urls`, so provider
  behaviour is tested without `hermes-agent`; only the class glue skips when the host is absent.
- **Two install paths, one code path.** The root `__init__.py` + `plugin.yaml` serve
  `hermes plugins install owner/repo` (Hermes imports the `__init__.py` next to `plugin.yaml`, with
  the plugin directory on the module's `__path__`, so the relative import resolves). The wheel ships
  only `tabstack_hermes` and is found through the `hermes_agent.plugins` entry point. Intra-package
  imports must stay relative so both paths work.

## Hard rules

- **Handlers return, never raise.** An exception out of a handler aborts the Hermes tool dispatch.
  Every failure goes through `errors.error_json` and comes back as `{"error": ...}` so the model can
  react. This is the opposite of the `langchain-tabstack` package, which raises `TabstackToolError`.
- **Handlers return JSON strings**, not dicts. `errors.ok_json` handles that, and passes strings
  through untouched so `extract_page_content` returns raw markdown.
- **The SDK does all network work.** Never reimplement HTTP, auth, or retries. Every call goes
  through the client in `client.py`.
- **Nothing imports the Tabstack SDK at module import time.** The import happens on first client use,
  so a Hermes session that never calls Tabstack pays no cold-start cost.
- **`is_available` / `check_fn` never make network calls.** Hermes calls them at registration time and
  on every `hermes tools` repaint.
- **Never pass `override=True` to `register_tool`.** Overriding a built-in tool needs operator opt-in
  (`plugins.entries.tabstack.allow_tool_override`) and none of these tools shadow a built-in.
- **Keep tool names, descriptions, and inputs identical to `langchain-tabstack` and
  `@tabstack/integrations-core`.** Cross-framework parity is the point; a rename here is a rename
  everywhere.
- No em dashes anywhere (code, comments, docs). Use commas, colons, or separate sentences.

## Commands

```bash
uv venv --python 3.11
uv pip install -e ".[test,dev]"
pytest                          # 44 tests, no network
ruff check .
ruff format --check .           # CI runs this, so format before pushing
```

Install `hermes-agent` into the dev environment to run the tests that need the host: the four
provider-glue tests in `tests/test_provider.py` and all of `tests/test_host_integration.py`, which
drives Hermes' real plugin loader. Without it they skip (`pytest.importorskip`), so a green local run
with no host installed proves less than it looks like.

`tests/test_host_integration.py` also needs this package installed (`pip install -e .`): the loader
discovers plugins through the `hermes_agent.plugins` entry point, and a bare source tree has nothing
to discover. It skips with a message saying so.

## CI

- `test.yml`: pytest on 3.11, 3.12, 3.13 (the `test` job, the merge and release gate), plus a `host`
  job that installs `hermes-agent` and reruns the suite. The `host` job is `continue-on-error: true`
  on purpose: the host pins its dependency set exactly, so an upstream release can break that install
  for reasons unrelated to this plugin. Treat it as signal, not a gate.
- `lint.yml`: `ruff check` and `ruff format --check`.
- `publish.yml`: runs on a created GitHub Release, calls lint and test, then publishes to TestPyPI,
  verifies the install and the entry point, and publishes to PyPI via trusted publishing (no token).

## Environment gotchas

- **Python floor is 3.11**, following the host (`hermes-agent` requires `>=3.11,<3.14`). macOS system
  Python is 3.9, so create the venv with an explicit 3.11 interpreter.
- **The entry-point value is a module, not a function.** Hermes' loader calls `ep.load()` and then
  looks up `register` on the result, so `tabstack = "tabstack_hermes"` works and
  `tabstack = "tabstack_hermes:register"` loads as "no register() function". The upstream docs show
  the `:register` form; it does not work against the loader in `hermes_cli/plugins.py`.
- **Plugins are opt-in.** After install the user still needs `hermes plugins enable tabstack`. A
  standalone plugin that is not in `plugins.enabled` is discovered and skipped.
- **`HERMES_HOME`** points Hermes at a different home directory, which is how to smoke test a load
  without touching the developer's real `~/.hermes`.
- `HERMES_PLUGINS_DEBUG=1` makes the loader log discovery, registration, and load failures to stderr.

## Verifying a change against the real host

```bash
mkdir -p /tmp/hhome && printf 'plugins:\n  enabled:\n    - tabstack\nweb:\n  extract_backend: "tabstack"\n' > /tmp/hhome/config.yaml
printf 'TABSTACK_API_KEY=sk-test-not-real\n' > /tmp/hhome/.env
HERMES_HOME=/tmp/hhome python -c "
from hermes_cli.plugins import _ensure_plugins_discovered; _ensure_plugins_discovered()
from tools.registry import registry
print(sorted(registry.get_tool_names_for_toolset('tabstack')))
from agent.web_search_registry import get_active_extract_provider
print(get_active_extract_provider())
"
```

Stub `tabstack_hermes.tools.get_async_client` before calling `registry.dispatch(...)` or
`tools.web_tools.web_extract_tool(...)` to drive a full round trip without hitting the API.

## Adding a tool (touch points, in order)

1. `schemas.py`: add the name to `TOOL_NAMES`, plus its description, emoji, and JSON Schema.
2. `tools.py`: add the async handler and register it in `HANDLERS`.
3. `plugin.yaml`: add the name to `provides_tools`.
4. `tests/test_tools.py`: happy path, an error payload path, and argument forwarding.
5. `tests/test_host_integration.py`: add the name to the expected toolset list.
6. Mirror the tool into `langchain-tabstack` and `@tabstack/integrations-core` so the three stay in
   lockstep.

`register()` iterates `TOOL_NAMES`, so no change is needed there.

## Host API surface used

Confirmed against hermes-agent 0.19.0:

- `ctx.register_tool(name, toolset, schema, handler, check_fn, requires_env, is_async, description,
  emoji)` -> `tools.registry.register`.
- `ctx.register_web_search_provider(provider)` -> `agent.web_search_registry.register_provider`,
  which rejects anything that is not an `agent.web_search_provider.WebSearchProvider` instance.
- `web_extract` calls `provider.extract(urls, format=...)` and expects a list of
  `{url, title, content, raw_content, metadata}` dicts in input order, with `error` per URL on
  failure. `web_search` is not implemented here on purpose: Tabstack has no ranked search endpoint.

## Pre-publish

- Confirm the `tabstack>=2.6.1` floor matches the intended SDK line.
- `hermes-agent` must stay out of `dependencies`: it is the host, and pulling in its exact-pinned
  dependency set would wreck any environment that only wants this plugin.
- Bump `version` in **both** `pyproject.toml` and `plugin.yaml`, plus `__version__` in
  `tabstack_hermes/__init__.py`. The manifest version is what `hermes plugins list` shows for a
  git-cloned install.
