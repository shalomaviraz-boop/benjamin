"""Benjamin Core - Gemini only via google-genai. No OpenAI, no Claude."""
import os
import asyncio

from google import genai
from google.genai import types
from memory.memory_store import format_memory_for_prompt

FAST_MODEL = "gemini-3-flash-preview"
SEARCH_MODEL = "gemini-3-flash-preview"


_client = None

WEB_MODE_PREFIXES = {
    "news": (
        "CRITICAL: This is a latest-news query. Use Google Search and return only current, recent, date-specific information. "
        "Do not rely on stale knowledge. Include explicit dates for each major item. Ignore old background unless directly needed. "
        "Keep the tone sharp, direct, and human. Do not append raw URLs or source dumps unless explicitly asked."
    ),
    "market": (
        "CRITICAL: This is a market/current-status query. Use Google Search and return only current, date-specific information. "
        "Do not rely on stale knowledge. If data timing is unclear, say so explicitly. "
        "Keep the tone sharp and practical. No raw source links unless explicitly asked."
    ),
    "research": (
        "Use Google Search when needed and prioritize up-to-date, source-backed information. "
        "If certainty is limited, say so explicitly. "
        "Answer like an elite operator: concise, direct, practical. No raw source links unless explicitly asked."
    ),
}


def get_client():
    """Create client once, reuse."""
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not set in .env")
        _client = genai.Client(api_key=key)
    return _client


def _inject_memory(contents: str, memory_context) -> str:
    """
    Inject structured memory into the prompt.
    memory_context may be a dict (preferred) or a string.
    """
    if not memory_context:
        return contents

    # If it's already a string, keep backward compatibility.
    if isinstance(memory_context, str):
        mem_block = f"# Memory Context\n{memory_context}"
        return f"{mem_block}\n\n{contents}"

    if not isinstance(memory_context, dict):
        mem_block = f"# Memory Context\n{str(memory_context)}"
        return f"{mem_block}\n\n{contents}"

    mem_block = format_memory_for_prompt(
        memory_context,
        detailed=True,
        include_conversation=True,
    )
    governor = memory_context.get("governor") or {}
    if isinstance(governor, dict) and governor:
        gov_lines = ["## Governor Guidance"]
        for key in (
            "alignment_score",
            "risk_pattern",
            "intervention_level",
            "recommended_action",
            "opening_line",
            "sharp_question",
        ):
            value = governor.get(key)
            if value in (None, "", [], {}):
                continue
            gov_lines.append(f"- {key}: {value}")
        mem_block = (mem_block + "\n" + "\n".join(gov_lines)).strip()
    return f"{mem_block}\n\n{contents}"


def _generate_fast_sync(contents: str) -> str:
    client = get_client()
    response = client.models.generate_content(
        model=FAST_MODEL,
        contents=contents,
    )
    return response.text or ""



def _extract_grounding_sources(response) -> list[str]:
    sources: list[str] = []

    try:
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            grounding = getattr(candidate, "grounding_metadata", None)
            if not grounding:
                continue

            chunks = getattr(grounding, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if not web:
                    continue
                uri = getattr(web, "uri", None)
                if uri and uri not in sources:
                    sources.append(uri)
    except Exception:
        return sources

    return sources


def _generate_web_sync(contents: str, web_mode: str = "research") -> str:
    client = get_client()
    mode = (web_mode or "research").strip().lower()
    prefix = WEB_MODE_PREFIXES.get(mode, WEB_MODE_PREFIXES["research"])
    final_contents = f"{prefix}\n\n{contents}"

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
    response = client.models.generate_content(
        model=SEARCH_MODEL,
        contents=final_contents,
        config=config,
    )

    text = response.text or ""
    _extract_grounding_sources(response)
    return text


async def generate_fast(
    contents: str,
    memory_context: str | None = None,
    **kwargs,
) -> str:
    """
    Async: Plain generate_content, no tools.
    Accepts extra kwargs for signature unification.
    """
    contents = _inject_memory(contents, memory_context)
    return await asyncio.to_thread(_generate_fast_sync, contents)


async def generate_web(
    contents: str,
    memory_context: str | None = None,
    web_mode: str = "research",
    **kwargs,
) -> str:
    """
    Async: generate_content with google_search tool.
    Accepts extra kwargs for signature unification.
    """
    contents = _inject_memory(contents, memory_context)
    return await asyncio.to_thread(_generate_web_sync, contents, web_mode)
