"""Benjamin Core - Gemini only via google-genai. No OpenAI, no Claude."""
import os

from google import genai
from google.genai import types

FAST_MODEL = "gemini-3-flash-preview"
SEARCH_MODEL = "gemini-3-flash-preview"

# Single client instance
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


def generate_fast(contents: str) -> str:
    """P1: Plain generate_content, no tools."""
    client = get_client()
    response = client.models.generate_content(
        model=FAST_MODEL,
        contents=contents,
    )
    return response.text or ""


def generate_web(contents: str) -> str:
    """P2: generate_content with google_search tool."""
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
