"""Benjamin Core - Gemini only via google-genai. No OpenAI, no Claude."""
import os
import asyncio

from google import genai
from google.genai import types

FAST_MODEL = "gemini-3-flash-preview"
SEARCH_MODEL = "gemini-3-flash-preview"

_client = None


def get_client():
    """Create client once, reuse."""
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not set in .env")
        _client = genai.Client(api_key=key)
    return _client


def _inject_memory(contents: str, memory_context: str | None) -> str:
    if not memory_context:
        return contents
    return f"# Memory Context\n{memory_context}\n\n{contents}"


def _generate_fast_sync(contents: str) -> str:
    client = get_client()
    response = client.models.generate_content(
        model=FAST_MODEL,
        contents=contents,
    )
    return response.text or ""


def _generate_web_sync(contents: str) -> str:
    client = get_client()
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
    response = client.models.generate_content(
        model=SEARCH_MODEL,
        contents=contents,
        config=config,
    )
    return response.text or ""


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
    **kwargs,
) -> str:
    """
    Async: generate_content with google_search tool.
    Accepts extra kwargs for signature unification.
    """
    contents = _inject_memory(contents, memory_context)
    return await asyncio.to_thread(_generate_web_sync, contents)