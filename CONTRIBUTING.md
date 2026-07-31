# Contributing

Thanks for helping out. `AGENTS.md` is the full operational guide (architecture, hard rules, host API
surface, release steps); this is the short version for getting set up and sending a change.

## Setup

Python 3.11 or newer, matching the host (`hermes-agent` requires `>=3.11,<3.14`). macOS system Python
is 3.9, so pick the interpreter explicitly:

```bash
uv venv --python 3.11
uv pip install -e ".[test,dev]"
```

Copy `.env.example` to `.env` if you want a local key, or set it through Hermes with
`hermes env set TABSTACK_API_KEY <your-key>`.

## Checks

```bash
pytest                    # no network, no API key needed
ruff check .
ruff format --check .     # CI enforces this
```

The test suite passes without `hermes-agent` installed, but a chunk of it skips: the web provider glue
and the whole end-to-end load through Hermes' plugin loader. Install the host to run them for real:

```bash
uv pip install hermes-agent
pytest -q                 # 44 tests, nothing skipped
```

A green run with no host installed proves less than it looks like, so install the host before claiming
a change to `provider.py` or `__init__.py` works.

## Things that will get a change sent back

- **A handler that raises.** Hermes aborts the tool dispatch on an exception, which leaves the model
  with nothing to react to. Every failure goes through `errors.error_json` and returns
  `{"error": ...}`.
- **A handler that returns a dict.** Handlers return JSON strings. `errors.ok_json` handles it.
- **An import of the Tabstack SDK at module scope.** The client is built on first use so a Hermes
  session that never calls Tabstack pays no cold-start cost.
- **A Hermes import in `tools.py`.** Host coupling belongs in `__init__.py` and `provider.py` only,
  which is what keeps the suite runnable without the host.
- **A network call in `is_available` or a `check_fn`.** Hermes calls those at registration time and on
  every `hermes tools` repaint.
- **A renamed tool, description, or input.** These are kept identical to the
  [`langchain-tabstack`](https://pypi.org/project/langchain-tabstack/) package and the TypeScript
  adapters. A rename here is a rename in all of them, in the same change set.
- **Em dashes.** Not used anywhere in this repo, code or docs. Commas, colons, or separate sentences.

## Adding a tool

Touch points in order: `schemas.py`, `tools.py`, `plugin.yaml`, `tests/test_tools.py`,
`tests/test_host_integration.py`, then mirror it into the LangChain and TypeScript packages. Full
detail in `AGENTS.md`.

## Pull requests

- One concern per PR, with a note on what you verified and how (including whether the host was
  installed).
- Update `README.md` when user-facing behaviour changes, and `AGENTS.md` when a convention or a
  host-contract detail changes.
- CI runs lint plus tests on 3.11, 3.12, and 3.13. The `host` job is informational: it installs
  `hermes-agent`, whose dependency set is pinned exactly, so an upstream release can break that
  install for reasons unrelated to this plugin.
