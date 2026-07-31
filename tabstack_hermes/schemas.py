"""Tool schemas and descriptions.

Hermes takes raw OpenAI function schemas (``{"name", "description",
"parameters"}``), so these are plain dicts rather than the Pydantic models the
``langchain-tabstack`` package uses. Names, descriptions, and field descriptions
are copied verbatim from that package (and from the TypeScript
``@tabstack/integrations-core``) so a Tabstack tool behaves the same whichever
framework calls it.
"""

from __future__ import annotations

from typing import Any

__all__ = ["TOOLSET", "TOOL_NAMES", "TOOL_DESCRIPTIONS", "TOOL_EMOJI", "SCHEMAS"]

TOOLSET = "tabstack"

TOOL_NAMES = (
    "extract_structured_data",
    "extract_page_content",
    "research_question",
    "generate_structured_data",
    "automate_browser_task",
)

TOOL_DESCRIPTIONS: dict[str, str] = {
    "extract_structured_data": (
        "Extract structured JSON data from a URL. Use when you need specific fields from a web "
        "page. 'json_schema_json' must be a JSON-encoded JSON Schema object with concrete "
        "properties and descriptions for each field to extract. See the schema-design guide for "
        "patterns that produce reliable results. Returns the extracted data as JSON."
    ),
    "extract_page_content": (
        "Fetch a URL and return its content as clean markdown. Use when you need to read a page's "
        "full content for summarization or when you don't know what specific fields to extract. "
        "Returns clean markdown text."
    ),
    "research_question": (
        "Research a question using multiple web sources. Use when you need a synthesized answer "
        "from multiple sources, not just data from a single known page. Returns an answer with "
        "cited sources."
    ),
    "generate_structured_data": (
        "Fetch a URL, then transform and restructure its content with AI into structured JSON. "
        "Use when you need derived or reshaped data (summaries, categorizations, computed "
        "fields), not just verbatim extraction. 'instructions' tells the AI how to transform the "
        "content; 'json_schema_json' must be a JSON-encoded JSON Schema object describing the "
        "output shape. Returns the generated data as JSON."
    ),
    "automate_browser_task": (
        "Run an AI browser automation task described in natural language. Use for multi-step web "
        "workflows: navigating, filling forms, gathering, and extracting across pages. Provide a "
        "clear 'task' and optionally a starting 'url', 'guardrails' to constrain the agent, "
        "'data' as context for form filling, a 'country' code for geotargeted browsing, and caps "
        "via 'max_iterations' and 'max_validation_attempts'. Runs non-interactively and returns "
        "the final answer plus any extracted data and the pages visited."
    ),
}

# Shown next to the tool name in `hermes tools` and in the CLI tool trace.
TOOL_EMOJI: dict[str, str] = {
    "extract_structured_data": "🧬",
    "extract_page_content": "📄",
    "research_question": "🔬",
    "generate_structured_data": "✨",
    "automate_browser_task": "🕹️",
}

_EFFORT = {
    "type": "string",
    "enum": ["min", "standard", "max"],
    "description": (
        'Optional fetch effort: "min" (fastest), "standard" (default, balanced), '
        '"max" (full browser rendering for JS-heavy pages).'
    ),
}
_NOCACHE = {
    "type": "boolean",
    "description": "Optional: bypass cache and force fresh retrieval",
}
_COUNTRY = {
    "type": "string",
    "description": 'Optional ISO 3166-1 alpha-2 country code for geotargeting (e.g. "US")',
}


def _schema(name: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "description": TOOL_DESCRIPTIONS[name],
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


SCHEMAS: dict[str, dict[str, Any]] = {
    "extract_structured_data": _schema(
        "extract_structured_data",
        {
            "url": {
                "type": "string",
                "description": "URL to fetch and extract structured data from",
            },
            "json_schema_json": {
                "type": "string",
                "description": (
                    "A JSON-encoded JSON Schema object with concrete properties and descriptions "
                    "for each field to extract."
                ),
            },
            "effort": _EFFORT,
            "nocache": _NOCACHE,
            "country": _COUNTRY,
        },
        ["url", "json_schema_json"],
    ),
    "extract_page_content": _schema(
        "extract_page_content",
        {
            "url": {
                "type": "string",
                "description": "URL to fetch and convert to clean markdown",
            },
            "effort": _EFFORT,
            "nocache": _NOCACHE,
            "country": _COUNTRY,
        },
        ["url"],
    ),
    "research_question": _schema(
        "research_question",
        {
            "query": {
                "type": "string",
                "description": "The research question to answer using multiple web sources",
            },
            "mode": {
                "type": "string",
                "enum": ["fast", "balanced"],
                "description": (
                    'Optional research mode: "fast" (quick) or "balanced" (default, more thorough)'
                ),
            },
            "nocache": _NOCACHE,
        },
        ["query"],
    ),
    "generate_structured_data": _schema(
        "generate_structured_data",
        {
            "url": {
                "type": "string",
                "description": "URL whose content should be fetched and transformed",
            },
            "instructions": {
                "type": "string",
                "description": (
                    "Natural-language instructions describing how to transform the page content"
                ),
            },
            "json_schema_json": {
                "type": "string",
                "description": (
                    "A JSON-encoded JSON Schema object describing the shape of the generated "
                    "output, with concrete properties and descriptions for each field."
                ),
            },
            "effort": _EFFORT,
            "nocache": _NOCACHE,
            "country": _COUNTRY,
        },
        ["url", "instructions", "json_schema_json"],
    ),
    "automate_browser_task": _schema(
        "automate_browser_task",
        {
            "task": {
                "type": "string",
                "description": "The browser automation task to perform, in natural language",
            },
            "url": {
                "type": "string",
                "description": "Optional starting URL for the task",
            },
            "guardrails": {
                "type": "string",
                "description": ("Optional safety constraints on what the agent is allowed to do"),
            },
            "data": {
                "type": "object",
                "description": ("Optional JSON context data for form filling or complex tasks"),
                "additionalProperties": True,
            },
            "country": {
                "type": "string",
                "description": (
                    'Optional ISO 3166-1 alpha-2 country code for geotargeted browsing (e.g. "US")'
                ),
            },
            "max_iterations": {
                "type": "integer",
                "description": "Optional cap on the number of agent iterations",
            },
            "max_validation_attempts": {
                "type": "integer",
                "description": "Optional cap on the number of result validation attempts",
            },
        },
        ["task"],
    ),
}
